# Local user configuration. Copy to config.py and fill in. config.py is gitignored.
# Project-level constants (URLs, game IDs, speed profiles) live in
# bga_replay_parser/constants.py and don't need to be edited.

# --- BGA credentials (required) ---
BGA_EMAIL    = "your_email@example.com"
BGA_PASSWORD = "your_password"

# --- Chrome / Selenium ---
CHROME_PATH       = "/usr/bin/google-chrome"  # adjust for your OS
CHROMEDRIVER_PATH = None                      # None = webdriver-manager auto-downloads

# --- Scraping pace ---
SPEED_PROFILE = "NORMAL"  # one of "FAST", "NORMAL", "SLOW"; see bga_replay_parser.constants.SPEED_PROFILES
REQUEST_DELAY = 5         # seconds between requests; raise if BGA throttles
