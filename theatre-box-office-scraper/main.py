import sys

from app.exporter import export_to_csv
from app.scraper import scrape_events
from app.seat_scrapper import scrape_seated_events


def run_bulk():
    print("=" * 60)
    print("  Theatre Box Office Scraper – bilietai.lt  [bulk mode]")
    print("=" * 60)
    data = scrape_events()
    if not data:
        print("\n⚠  Scraper returned 0 events.")
        print("   Tip: set HEADLESS=False in app/config.py to debug.")
    else:
        print(f"\n  Sample: {data[0]['title']} @ {data[0]['venue']}")
    export_to_csv(data, path="data/output.csv")
    print("\nDone → data/output.csv")


def run_seats():
    print("=" * 60)
    print("  Theatre Box Office Scraper – bilietai.lt  [seat mode]")
    print("=" * 60)
    data = scrape_seated_events()
    print(f"\n✓ Scraped {len(data)} events")
    for d in data:
        pricing = d.get("seat_pricing") or {}
        for dt_key, seats in pricing.items():
            print(f"  {d['title'][:45]:45s}  [{dt_key}]  {len(seats)} seats")
    export_to_csv(data, path="data/seated_output.csv")
    print("\nDone → data/seated_output.csv")


if __name__ == "__main__":
    if "--seats" in sys.argv:
        run_seats()
    else:
        run_bulk()
