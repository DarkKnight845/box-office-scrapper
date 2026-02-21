import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models import PerformanceTime, TheatreData
from app.utils import extract_city_country, parse_date, safe_text


def extract_json_ld(page) -> Dict[str, Any]:
    """Return the first Event-type JSON-LD block found, or {}."""
    try:
        scripts = page.locator("script[type='application/ld+json']").all()
        for s in scripts:
            try:
                data = json.loads(s.inner_text(timeout=2000))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") in (
                            "Event",
                            "MusicEvent",
                            "TheaterEvent",
                        ):
                            return item
                elif isinstance(data, dict) and data.get("@type") in (
                    "Event",
                    "MusicEvent",
                    "TheaterEvent",
                ):
                    return data
            except Exception:
                continue
    except Exception:
        pass
    return {}


def get_title(page, ld: dict) -> str:
    if ld.get("name"):
        return str(ld["name"]).strip()
    for sel in ["h1.event-title", "h1.title", ".event-name", "h1"]:
        t = safe_text(page, sel)
        if t:
            return t
    return "Unknown"


def get_venue_address(page, ld: dict):
    """Returns (venue_name, address, city, country)."""
    # JSON-LD location
    loc = ld.get("location", {})
    if isinstance(loc, dict):
        venue_name = loc.get("name", "")
        addr_obj = loc.get("address", {})
        if isinstance(addr_obj, dict):
            street = addr_obj.get("streetAddress", "")
            city = addr_obj.get("addressLocality", "")
            raw_country = addr_obj.get("addressCountry", "Lithuania")
            if isinstance(raw_country, dict):
                country = raw_country.get("name", "Lithuania")
            else:
                country = raw_country or "Lithuania"
            address = f"{street}, {city}".strip(", ")
            if venue_name:
                return venue_name, address or venue_name, city, country
        elif isinstance(addr_obj, str):
            city, country = extract_city_country(addr_obj)
            return venue_name, addr_obj, city, country

    venue_selectors = [
        ".location-name",
        ".venue-name",
        ".venue",
        "[class*='venue'] h2",
        "[class*='location'] strong",
        ".event-location .name",
        "[data-testid='venue-name']",
    ]
    addr_selectors = [
        ".location-address",
        ".venue-address",
        ".address",
        "[class*='address']",
        ".event-location .address",
    ]

    venue_name = ""
    for sel in venue_selectors:
        t = safe_text(page, sel)
        if t:
            venue_name = t
            break

    address = ""
    for sel in addr_selectors:
        t = safe_text(page, sel)
        if t:
            address = t
            break

    # as a last resort, look for map / directions link text
    if not address:
        try:
            map_links = page.locator(
                "a[href*='maps.google'], a[href*='goo.gl/maps']"
            ).all()
            if map_links:
                address = map_links[0].inner_text(timeout=2000).strip()
        except Exception:
            pass

    city, country = extract_city_country(address or venue_name)
    return venue_name or "Unknown", address or venue_name, city, country


def get_dates(page, ld: dict):
    """Returns (open_date, close_date)."""
    start = parse_date(str(ld.get("startDate", "")))
    end = parse_date(str(ld.get("endDate", "")))
    if start:
        return start, end

    raw_start = safe_text(page, ".event-date-start, .start-date, [class*='start-date']")
    raw_end = safe_text(page, ".event-date-end,   .end-date,   [class*='end-date']")

    if not raw_start:
        combined = safe_text(page, ".event-dates, .dates, [class*='event-date']")
        if " – " in combined:
            parts = combined.split(" – ", 1)
            raw_start, raw_end = parts[0], parts[1]
        elif " - " in combined:
            parts = combined.split(" - ", 1)
            raw_start, raw_end = parts[0], parts[1]
        else:
            raw_start = combined

    return parse_date(raw_start), parse_date(raw_end)


def get_upcoming_performances(page, ld: dict) -> Optional[List[PerformanceTime]]:
    perfs = []

    # JSON-LD subEvents
    for sub in ld.get("subEvent", []):
        d = parse_date(str(sub.get("startDate", "")))
        if d:
            perfs.append(
                PerformanceTime(date=d.strftime("%Y-%m-%d"), time=d.strftime("%H:%M"))
            )

    if perfs:
        return perfs

    # bilietai date-picker buttons – each selectable date is a <button> or <li>
    date_selectors = [
        ".calendar-day.available",
        ".schedule-item",
        ".date-list li",
        "[class*='calendar'] [class*='day']:not([class*='disabled'])",
        "[class*='schedule'] [class*='item']",
        "[class*='event-time']",
        ".times-list .time-item",
    ]
    for sel in date_selectors:
        try:
            items = page.locator(sel).all()
            if not items:
                continue
            for item in items[:20]:  # cap at 20
                raw = item.inner_text(timeout=1500).strip()
                dt_match = re.search(r"(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})", raw)
                if dt_match:
                    perfs.append(
                        PerformanceTime(date=dt_match.group(1), time=dt_match.group(2))
                    )
                    continue
                date_attr = (
                    item.get_attribute("data-date")
                    or item.get_attribute("datetime")
                    or ""
                )
                if date_attr:
                    d = parse_date(date_attr)
                    if d:
                        perfs.append(
                            PerformanceTime(
                                date=d.strftime("%Y-%m-%d"), time=d.strftime("%H:%M")
                            )
                        )
            if perfs:
                return perfs
        except Exception:
            continue

    return perfs if perfs else None


def get_pricing(page) -> tuple:
    """
    Returns (currency, seat_pricing_dict).
    """
    currency = None
    seat_pricing: Dict[str, list] = {}

    # Detect currency from price text
    price_text = safe_text(page, "[class*='price'], .ticket-price, .price-value")
    if "€" in price_text or "EUR" in price_text.upper():
        currency = "EUR"
    elif "£" in price_text:
        currency = "GBP"
    elif "$" in price_text:
        currency = "USD"

    price_row_selectors = [
        "table.prices tr",
        ".price-table tr",
        ".sector-prices .sector",
        "[class*='price-row']",
        "[class*='ticket-type']",
        ".price-list li",
        ".prices-list .item",
    ]

    rows = []
    for sel in price_row_selectors:
        try:
            found = page.locator(sel).all()
            if found:
                rows = found
                break
        except Exception:
            continue

    if rows:
        event_date = safe_text(page, ".event-date, [class*='event-date']") or "TBD"
        pricing_list = []
        for row in rows[:50]:
            try:
                text = row.inner_text(timeout=1500).strip()
                price_match = re.search(r"(\d+[\.,]\d{2})", text)
                if price_match:
                    price = price_match.group(1).replace(",", ".")
                    seat_label = (
                        text[: text.find(price_match.group(0))]
                        .strip()
                        .rstrip("-–:")
                        .strip()
                    )
                    if not currency:
                        if "€" in text:
                            currency = "EUR"
                    pricing_list.append(
                        {"seat": seat_label or "General", "ticket_price": price}
                    )
            except Exception:
                continue
        if pricing_list:
            seat_pricing[event_date] = pricing_list

    return currency or "EUR", seat_pricing if seat_pricing else None


def parse_event_page(browser, url: str) -> Optional[dict]:
    page = browser.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2500)

        ld = extract_json_ld(page)

        title = get_title(page, ld)
        venue, address, city, country = get_venue_address(page, ld)
        open_date, close_date = get_dates(page, ld)
        upcoming = get_upcoming_performances(page, ld)
        currency, seat_pricing = get_pricing(page)

        ld_type = ld.get("@type", "")
        url_lower = url.lower()
        if (
            "teatras" in url_lower
            or "theatre" in url_lower
            or ld_type == "TheaterEvent"
        ):
            category = "theatre"
        elif "koncert" in url_lower or ld_type == "MusicEvent":
            category = "concert"
        elif "sportas" in url_lower or "sport" in url_lower:
            category = "sport"
        elif "festivaliai" in url_lower or "festival" in url_lower:
            category = "festival"
        else:
            category = ld_type.lower() if ld_type else "event"

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
            upcoming_performances=upcoming,
            capacity=None,
            currency=currency,
            seat_pricing=seat_pricing,
            scrape_datetime=datetime.utcnow(),
        )

        page.close()
        return data.dict()

    except Exception as e:
        print(f"  ⚠  Error parsing {url}: {e}")
        try:
            page.close()
        except Exception:
            pass
        return None
