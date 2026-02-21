from datetime import datetime
from typing import Optional


def safe_text(page, selector: str, default: str = "") -> str:
    """Return inner_text of the first matching element, or default."""
    try:
        el = page.locator(selector).first
        if el.count() == 0:
            return default
        return el.inner_text(timeout=3000).strip()
    except Exception:
        return default


def parse_date(raw: str) -> Optional[datetime]:
    """Try several common date formats and return a datetime, or None."""
    if not raw:
        return None
    raw = raw.strip()
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def extract_city_country(address: str):
    """
    Bilietai venue strings often look like:
        'Twinsbet Arena, Vilnius'
    Split on the last comma to get city; country defaults to Lithuania.
    """
    parts = [p.strip() for p in address.rsplit(",", 1)]
    city = parts[-1] if len(parts) > 1 else ""
    return city, "Lithuania"
