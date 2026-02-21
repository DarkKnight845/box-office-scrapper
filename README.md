# Theatre Box Office Scraper — bilietai.lt

Scrapes concert and theatre event data from [bilietai.lt](https://www.bilietai.lt/eng/tickets/koncertai) using **Playwright** (headless Chromium) and exports structured results to CSV.

---

## Output Fields

| Field | Type | Description |
|---|---|---|
| `title` | str | Performance name |
| `venue_url` | str | Direct URL to the event page |
| `category` | str | concert / theatre / festival / sport |
| `venue` | str | Venue / theatre name |
| `address` | str | Full address string |
| `city` | str | City extracted from address |
| `country` | str | Country (usually Lithuania) |
| `open_date` | datetime | First performance date |
| `close_date` | datetime | Last performance date |
| `booking_start_date` | datetime | When booking opens (if available) |
| `booking_end_date` | datetime | When booking closes |
| `upcoming_performances` | JSON list | `[{"date": "2026-03-13", "time": "20:00"}, …]` |
| `capacity` | int | Venue capacity (if available) |
| `currency` | str | Ticket currency code |
| `seat_pricing` | JSON dict | `{"2026-03-13 20:00": [{"seat": "Sector A", "ticket_price": "25.00"}]}` |
| `scrape_datetime` | datetime | UTC timestamp of extraction |

---

## Setup

### 1. Clone the repository

```bash
git clone origin https://github.com/DarkKnight845/box-office-scrapper.git
cd theatre-box-office-scraper
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright browsers

```bash
playwright install chromium
```

---

## Running the Scraper

```bash
python main.py
```

Output is saved to `data/output.csv`.

### Configuration (`app/config.py`)

| Setting | Default | Description |
|---|---|---|
| `BASE_URL` | bilietai.lt concerts | Starting listing URL |
| `HEADLESS` | `True` | Set `False` to watch the browser (useful for debugging) |
| `MAX_EVENTS` | `50` | Cap on events scraped per run; set `None` for all |
| `REQUEST_DELAY` | `1500` | Milliseconds to wait between event page requests |

---

## Troubleshooting — Empty Output

If `output.csv` is empty or has 0 rows:

1. **Set `HEADLESS = False`** in `app/config.py` and re-run. Watch what the browser loads.
2. **Check for 403 / bot block** — bilietai.lt occasionally serves CAPTCHA pages. The scraper uses a realistic user-agent and removes the `webdriver` flag, but some runs may still be blocked.
3. **Selector drift** — the site may have updated its HTML. Open the listing page in Chrome DevTools and verify that `a[href*='/eng/tickets/']` still matches event card links.

---

## Project Structure

```
theatre-box-office-scraper/
├── app/
│   ├── __init__.py
│   ├── config.py       # tunable constants
│   ├── models.py       # Pydantic data schema
│   ├── scraper.py      # Playwright 
│   ├── parser.py       # single event-page 
│   ├── exporter.py     # CSV writer
│   └── utils.py        # shared helpers 
├── data/
│   └── output.csv      # generated output
├── main.py
├── requirements.txt
└── README.md
```

---

## Example Output (CSV excerpt)

```
title,venue_url,category,venue,city,open_date,currency,seat_pricing
The Phantom of the Opera,https://www.bilietai.lt/eng/tickets/…,concert,Twinsbet Arena,Vilnius,2026-05-19T19:00:00,EUR,"{""2026-05-19 19:00"": [{""seat"": ""Sector A"", ""ticket_price"": ""45.00""}]}"
```
