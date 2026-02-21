from app.exporter import export_to_csv
from app.scraper import scrape_events

OUTPUT_PATH = "data/output.csv"


def main():
    print("=" * 60)
    print("  Theatre Box Office Scraper – bilietai.lt")
    print("=" * 60)

    data = scrape_events()

    if not data:
        print("\n⚠  Scraper returned 0 events.")
        print("   Possible causes:")
        print("   • The site blocked the request (403 / CAPTCHA).")
        print(
            "   • CSS selectors changed – inspect the live page and update app/scraper.py."
        )
        print("   • Network issue or timeout.")
        print("   Tip: set HEADLESS=False in app/config.py to watch the browser.")
    else:
        print(f"\n  Sample record:\n  {data[0]}\n")

    export_to_csv(data, path=OUTPUT_PATH)
    print("\nDone.")


if __name__ == "__main__":
    main()
