import re
import time
from datetime import datetime
from typing import Optional

from playwright.sync_api import Page, Response, sync_playwright

from app.config import HEADLESS, LAUNCH_ARGS
from app.exporter import export_to_csv
from app.models import TheatreData
from app.parser import extract_json_ld, get_dates, get_title, get_venue_address

PAGE_LOAD_TIMEOUT = 45000
NAV_TIMEOUT = 45000


TARGET_EVENTS = [
    {
        "url": "https://www.bilietai.lt/eng/tickets/koncertai/the-phantom-of-the-opera-101987/",
        "label": "The Phantom of the Opera",
    },
    {
        "url": "https://www.bilietai.lt/eng/tickets/koncertai/ledo-sou-stichijos-2-pasadoblis-484896/",
        "label": "Ledo šou STICHIJOS 2",
    },
    {
        "url": "https://www.bilietai.lt/eng/tickets/teatras/ingmar-bergman-rudens-sonata-492033/",
        "label": "Ingmar Bergman - Rudens sonata",
    },
    {
        "url": "https://www.bilietai.lt/eng/tickets/koncertai/metu-muzikos-apdovanojimai-mama-2026-494840/",
        "label": "M.A.M.A. 2026",
    },
    {
        "url": "https://www.bilietai.lt/eng/tickets/teatras/sokio-spektaklis-du-i-prieki-viens-atgal-490773/",
        "label": "Šokio spektaklis DU Į PRIEKĮ",
    },
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _is_seat_data(payload) -> bool:
    """Detect if a JSON payload is seat inventory."""
    if isinstance(payload, list) and payload:
        sample = payload[0] if isinstance(payload[0], dict) else {}
    elif isinstance(payload, dict):
        for key in ("seats", "seatList", "tickets", "items", "data"):
            if key in payload and isinstance(payload[key], list):
                return _is_seat_data(payload[key])
        sample = payload
    else:
        return False
    seat_keys = {
        "seatId",
        "seat_id",
        "seatNumber",
        "seat",
        "row",
        "sector",
        "price",
        "priceValue",
        "ticketPrice",
        "status",
        "available",
    }
    return bool(seat_keys & set(sample.keys()))


def _extract_seats_from_json(payload) -> list[dict]:
    """Flatten JSON seat inventory into [{'seat': ..., 'ticket_price': ...}]."""
    if isinstance(payload, dict):
        for key in ("seats", "seatList", "tickets", "items", "data", "result"):
            if key in payload and isinstance(payload[key], list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        return []

    results = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", item.get("available", "1"))).lower()
        if status in ("0", "sold", "reserved", "false", "unavailable"):
            continue
        sector = (
            item.get("sector") or item.get("sectorName") or item.get("section") or ""
        )
        row = item.get("row") or item.get("rowNumber") or item.get("rowNum") or ""
        seat_num = (
            item.get("seat")
            or item.get("seatNumber")
            or item.get("seatNum")
            or item.get("seatId")
            or ""
        )
        parts = []
        if sector:
            parts.append(str(sector).strip())
        if row:
            parts.append(f"row {row}")
        if seat_num:
            parts.append(f"seat {seat_num}")
        seat_label = " ".join(parts) if parts else str(seat_num or "?")

        price_raw = (
            item.get("price")
            or item.get("priceValue")
            or item.get("ticketPrice")
            or item.get("amount")
            or 0
        )
        try:
            price = f"{float(str(price_raw).replace(',', '.')):.2f}"
        except (ValueError, TypeError):
            price = str(price_raw)
        results.append({"seat": seat_label, "ticket_price": price})
    return results


def _read_seats_from_dom(page: Page) -> list[dict]:
    seats = []
    # Approach A: SVG elements with data-attributes
    try:
        page.wait_for_selector(
            "[data-seat], [data-seat-id], [data-price], "
            "svg[class*='seat'], [class*='seatmap'] svg",
            timeout=6000,
        )
        elements = page.locator(
            "[data-seat], [data-seat-id], [data-price], "
            "g[class*='seat']:not([class*='disabled'])"
        ).all()
        for el in elements[:500]:
            seat_id = (
                el.get_attribute("data-seat")
                or el.get_attribute("data-seat-id")
                or el.get_attribute("data-id")
                or ""
            )
            price_raw = (
                el.get_attribute("data-price")
                or el.get_attribute("data-ticket-price")
                or ""
            )
            if seat_id or price_raw:
                try:
                    price = f"{float(price_raw):.2f}" if price_raw else "N/A"
                except ValueError:
                    price = price_raw
                seats.append({"seat": seat_id or "?", "ticket_price": price})
        if seats:
            return seats
    except Exception:
        pass

    # Approach B: price table rows
    try:
        rows = page.locator(
            "tr:has(td), [class*='price-row'], [class*='ticket-row'], "
            "[class*='seat-row'], .price-list li"
        ).all()
        for row in rows[:200]:
            text = row.inner_text(timeout=1000).strip()
            price_match = re.search(r"(\d+[.,]\d{2})", text)
            if price_match:
                price = price_match.group(1).replace(",", ".")
                label = (
                    text[: text.find(price_match.group(0))]
                    .strip()
                    .rstrip(":-–")
                    .strip()
                )
                seats.append({"seat": label or "General", "ticket_price": price})
        if seats:
            return seats
    except Exception:
        pass
    return seats


def _navigate_to_seat_selection(page: Page) -> bool:
    # click "Buy ticket"
    buy_selectors = [
        "a:has-text('Buy ticket')",
        "button:has-text('Buy ticket')",
        "a:has-text('Pirkti')",
        "button:has-text('Pirkti')",
        "[class*='buy-btn']",
        ".buy-ticket",
        "a[href*='order'], a[href*='buy'], a[href*='pirkti']",
    ]
    clicked = False
    for sel in buy_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                clicked = True
                print(f"    ✓ Clicked: {sel}")
                break
        except Exception:
            continue

    if not clicked:
        print("    ⚠ Buy button not found — will read current page")
        return False

    page.wait_for_timeout(3000)

    # pick first available date if a calendar appeared
    for sel in (
        "[class*='calendar'][class*='available']",
        "[class*='date-item']:not([class*='disabled'])",
        "[class*='event-date']:not([class*='disabled'])",
        "[data-date]",
    ):
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1500):
                el.click()
                print(f"    ✓ Date selected: {sel}")
                page.wait_for_timeout(2500)
                break
        except Exception:
            continue

    # click "Select seats" if prompted
    for sel in (
        "button:has-text('Select seats')",
        "a:has-text('Select seats')",
        "button:has-text('Pasirinkti vietas')",
        "[class*='seat-select']",
    ):
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1500):
                el.click()
                print(f"    ✓ Seat selection clicked: {sel}")
                page.wait_for_timeout(3000)
                break
        except Exception:
            continue

    # Verify seat map is visible
    for sel in (
        "svg",
        "[class*='seatmap']",
        "[class*='seat-map']",
        "[data-seat]",
        "canvas",
    ):
        try:
            if page.locator(sel).count() > 0:
                print(f"    ✓ Seat map visible: {sel}")
                return True
        except Exception:
            continue
    return False


def scrape_event_with_seats(browser, event: dict) -> Optional[dict]:
    url, label = event["url"], event["label"]
    print(f"\n{'=' * 55}\n  {label}\n  {url}")

    captured_seats: list[dict] = []

    page = browser.new_page()
    page.set_extra_http_headers(
        {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": USER_AGENT,
        }
    )
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page.set_default_navigation_timeout(NAV_TIMEOUT)
    page.set_default_timeout(NAV_TIMEOUT)

    def handle_response(response: Response):
        nonlocal captured_seats
        if captured_seats:
            return
        if "json" not in response.headers.get("content-type", ""):
            return
        u = response.url.lower()
        if any(
            s in u
            for s in (
                "google",
                "facebook",
                "analytics",
                "gtm",
                "hotjar",
                "sentry",
                ".css",
                ".js",
                ".png",
            )
        ):
            return
        try:
            body = response.json()
            if _is_seat_data(body):
                seats = _extract_seats_from_json(body)
                if seats:
                    captured_seats = seats
                    print(f"    ✓ XHR → {len(seats)} seats from {response.url[:70]}")
        except Exception:
            pass

    page.on("response", handle_response)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        page.wait_for_timeout(3000)

        ld = extract_json_ld(page)
        title = get_title(page, ld)
        venue, address, city, country = get_venue_address(page, ld)
        open_date, close_date = get_dates(page, ld)
        event_dt = open_date.strftime("%Y-%m-%d %H:%M") if open_date else "TBD"

        _navigate_to_seat_selection(page)
        page.wait_for_timeout(5000)  # let XHR settle

        if not captured_seats:
            print("    ↳ Trying DOM fallback…")
            captured_seats = _read_seats_from_dom(page)
            print(
                f"    {'✓' if captured_seats else '✗'} DOM fallback: {len(captured_seats)} seats"
            )

        seat_pricing = {event_dt: captured_seats} if captured_seats else None

        category = (
            "theatre"
            if "teatras" in url.lower()
            else "concert"
            if "koncert" in url.lower()
            else ld.get("@type", "event").lower()
        )

        data = TheatreData(
            title=title,
            venue_url=url,
            category=category,
            venue=venue,
            address=address,
            city=city,
            country=country,
            open_date=open_date,
            close_date=close_date,
            booking_start_date=None,
            booking_end_date=close_date,
            upcoming_performances=None,
            capacity=None,
            currency="EUR",
            seat_pricing=seat_pricing,
            scrape_datetime=datetime.utcnow(),
        )
        page.close()
        return data.dict()

    except Exception as e:
        print(f"    ✗ Error: {e}")
        try:
            page.close()
        except Exception:
            pass
        return None


def scrape_seated_events() -> list[dict]:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)
        for event in TARGET_EVENTS:
            result = scrape_event_with_seats(browser, event)
            if result:
                results.append(result)
            time.sleep(2)
        browser.close()
    return results


if __name__ == "__main__":
    print("=" * 55)
    print("  Seat-Level Ticket Scraper — bilietai.lt")
    print("=" * 55)
    data = scrape_seated_events()
    print(f"\n✓ Scraped {len(data)} events")
    for d in data:
        pricing = d.get("seat_pricing") or {}
        if pricing:
            for dt_key, seats in pricing.items():
                print(f"  {d['title'][:45]:45s}  [{dt_key}]  {len(seats)} seats")
        else:
            print(f"  {d['title']}: no seat data")
    export_to_csv(data, path="data/seated_output.csv")
    print("\nExported → data/seated_output.csv")
