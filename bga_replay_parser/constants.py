"""
Project constants. These never need to vary per user.

Anything truly user-specific (credentials, OS-dependent Chrome paths,
speed-profile preference) lives in `config.py` instead — see
`config.example.py` for the template.
"""

# --- BGA URLs ---
TABLE_URL_TEMPLATE = "https://boardgamearena.com/table?table={table_id}"
REPLAY_URL_TEMPLATE = (
    "https://boardgamearena.com/archive/replay/{version_id}/"
    "?table={table_id}&player={player_id}&comments={player_id}"
)

# --- Games ---
# Numeric BGA game IDs by short name. Used by `index_top_players.py` and
# `scrape_raw_replay.py` for game routing.
GAME_IDS = {
    "terra_mystica": 1118,
    "tokaido":       1003,
}

# Default raw-replay format per game.
#   "html" — full replay page via Selenium. Required when the parser uses
#            `gameui.completesetup` gamedatas (Terra Mystica).
#   "json" — gamelogs only via the BGA archive API. Cheaper, no Selenium
#            replay page load. Suitable when the parser doesn't need
#            completesetup (Tokaido).
# Override per-run with `scrape_raw_replay.py --raw-format`.
RAW_FORMAT_BY_GAME = {
    "terra_mystica": "html",
    "tokaido":       "json",
}

# --- Speed profiles for BGAScraper ---
# Choose one via `config.SPEED_PROFILE`. The scraper looks up
# `SPEED_PROFILES[config.SPEED_PROFILE]` at construction time.
SPEED_PROFILES = {
    "FAST":   {"page_load_delay": 2, "click_delay": 0.3, "gamereview_delay": 1.5, "element_wait_timeout": 5},
    "NORMAL": {"page_load_delay": 3, "click_delay": 0.5, "gamereview_delay": 2.5, "element_wait_timeout": 8},
    "SLOW":   {"page_load_delay": 5, "click_delay": 1.0, "gamereview_delay": 4.0, "element_wait_timeout": 12},
}

# --- Default data dirs ---
# Most scripts take output paths as CLI args; these are only fallbacks for
# scraper.py / games_registry.py when no explicit path is given.
RAW_DATA_DIR      = "data/raw"
REGISTRY_DATA_DIR = "data/registry"
