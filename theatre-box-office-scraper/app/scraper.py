import re
import time

from playwright.sync_api import Page, sync_playwright

from app.config import (
    BASE_URL,
    HEADLESS,
    LAUNCH_ARGS,
    MAX_EVENTS,
    PAGE_LOAD_TIMEOUT,
    REQUEST_DELAY,
)
from app.parser import parse_event_page

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

EXTRA_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.bilietai.lt/",
}


def _new_stealth_page(browser) -> Page:
    context = browser.new_context(
        user_agent=USER_AGENT,
        locale="en-US",
        viewport={"width": 1280, "height": 800},
        extra_http_headers=EXTRA_HEADERS,
    )
    page = context.new_page()
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return page


def _collect_event_links(page: Page) -> list[str]:
    """
    Extract event detail page links from the listing page.
    Uses heuristics to find valid event URLs and avoid duplicates.
    """
    # Wait for at least one event card to appear (the grid is JS-rendered)
    try:
        page.wait_for_selector("a[href*='/eng/tickets/']", timeout=PAGE_LOAD_TIMEOUT)
    except Exception:
        print("  ⚠  Timed out waiting for event cards – page may be empty or blocked.")
        return []

    anchors = page.query_selector_all("a[href*='/eng/tickets/']")
    seen = set()
    links = []
    for a in anchors:
        href = a.get_attribute("href") or ""
        parts = [p for p in href.split("/") if p]
        if len(parts) < 4:
            continue
        last_slug = parts[-1]
        # Must end with -<digits> to avoid non-event links (e.g. pagination, filters)
        if not re.search(r"-\d{4,}$", last_slug):
            continue
        if href not in seen:
            seen.add(href)
            full = f"https://www.bilietai.lt{href}" if href.startswith("/") else href
            links.append(full)

    return links


def _load_more_events(page: Page) -> bool:
    """
    Try various common 'load more' button selectors and click if found.
    Returns True if a button was clicked, False otherwise.
    """
    load_more_selectors = [
        "button[class*='load-more']",
        "button[class*='show-more']",
        "a[class*='load-more']",
        ".pagination a[rel='next']",
        "button:has-text('More')",
        "button:has-text('Load more')",
    ]
    for sel in load_more_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                btn.click()
                page.wait_for_timeout(2000)
                return True
        except Exception:
            continue
    return False


def scrape_events() -> list[dict]:
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)
        page = _new_stealth_page(browser)

        print(f"→ Loading listing page: {BASE_URL}")
        try:
            page.goto(
                BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT
            )
        except Exception as e:
            print(f"  ⚠  Failed to load listing page: {e}")
            browser.close()
            return []

        page.wait_for_timeout(3000)

        # cllect links, optionally clicking 'load more' once or twice
        links = _collect_event_links(page)
        print(f"  Found {len(links)} event links on first load.")

        if not links:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            links = _collect_event_links(page)
            print(f"  After scroll: {len(links)} event links.")

        if _load_more_events(page):
            extra = _collect_event_links(page)
            all_links = list(
                dict.fromkeys(links + extra)
            )  # deduplicate, preserve order
            links = all_links
            print(f"  After 'load more': {len(links)} event links.")

        page.close()

        if MAX_EVENTS is not None:
            links = links[:MAX_EVENTS]
        print(f"  Scraping {len(links)} events…\n")

        for i, url in enumerate(links, 1):
            print(f"  [{i}/{len(links)}] {url}")
            event_data = parse_event_page(browser, url)
            if event_data:
                results.append(event_data)
            # Polite delay
            time.sleep(REQUEST_DELAY / 1000)

        browser.close()

    print(f"\n✓ Scraped {len(results)} events successfully.")
    return results
