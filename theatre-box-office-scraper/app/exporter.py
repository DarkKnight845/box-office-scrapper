import json
import os
from datetime import datetime

import pandas as pd


def _prepare_row(record: dict) -> dict:
    """Flatten/serialise complex fields for CSV storage."""
    row = {}
    for key, val in record.items():
        if isinstance(val, (list, dict)):
            row[key] = json.dumps(val, default=str, ensure_ascii=False)
        elif isinstance(val, datetime):
            row[key] = val.isoformat()
        else:
            row[key] = val
    return row


def export_to_csv(data: list, path: str = "data/output.csv") -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    if not data:
        print(f"⚠  No data to export – output file will be empty: {path}")
        columns = [
            "title",
            "venue_url",
            "category",
            "venue",
            "address",
            "city",
            "country",
            "open_date",
            "close_date",
            "booking_start_date",
            "booking_end_date",
            "upcoming_performances",
            "capacity",
            "currency",
            "seat_pricing",
            "scrape_datetime",
        ]
        pd.DataFrame(columns=columns).to_csv(path, index=False)
        return

    rows = [_prepare_row(record) for record in data]
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"✓ Data exported to {path}  ({len(df)} rows, {len(df.columns)} columns)")
