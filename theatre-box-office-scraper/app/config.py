BASE_URL = "https://www.bilietai.lt/eng/tickets/koncertai"
HEADLESS = True
PAGE_LOAD_TIMEOUT = 15000
NAVIGATION_TIMEOUT = 20000
MAX_EVENTS = 50
REQUEST_DELAY = 1500

# playwright launch args to reduce bot-detection fingerprint
LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
]
