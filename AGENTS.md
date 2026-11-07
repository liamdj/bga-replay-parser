# BGA Replay Parser

## Overview

Scrapes and parses BoardGameArena (BGA) replays for three games: Terra Mystica, Tokaido and Wingspan. The BGA interaction layer (auth, page navigation, leaderboard) is game-agnostic; each game has its own parser/handlers/models.

This repo is a library + a handful of CLI entry points. It is **not** an end-user app — the original Tkinter GUI, FastAPI service, `main.py` CLI, and the Terraforming Mars parser from upstream have all been removed. See [README.md](README.md) for lineage. For TM parsing, use upstream [HStrand/bga-tm-scraper](https://github.com/HStrand/bga-tm-scraper).

## Config vs constants

Project constants (URLs, game IDs, raw-format routing, speed profiles, default data dirs) live in [`bga_replay_parser/constants.py`](bga_replay_parser/constants.py) — tracked, never edited per user.

User-specific values (credentials, Chrome path, speed-profile preference, request delay) live in `config.py`. The repo ships [`config.example.py`](config.example.py); copy it to `config.py` (gitignored) and fill in.

## Common tasks

Use the snippets below verbatim. Don't recreate the deleted GUI/scheduler/`main.py`/`web_service.py` — they were removed intentionally.

### Scrape one or many raw replays

```bash
# JSON-based games (Tokaido, Wingspan): cheaper, hits the BGA archive API directly
python scrape_raw_replay.py --file table_ids.json --raw-format json

# HTML-based games (Terra Mystica): loads the full replay page via Selenium
python scrape_raw_replay.py --file table_ids.json --raw-format html

# Multi-account rotation (works around BGA daily replay limit)
python scrape_raw_replay.py --file table_ids.json --rotate-accounts

# Current TM corpus filter (--ranked drops Friendly-mode games)
python scrape_raw_replay.py --file data/batch/terra_mystica/table_ids.json --raw-format html \
    --players 4 --map "Base Game" "Random" "Fjords" "Fire & Ice" "The Archipelago" \
    --min-elo 200 --min-top-elo 400 --ranked --rotate-accounts
```

HTML replays are stored zstd-compressed as `replay_<table_id>.html.zst` (~5 MB → ~0.15 MB each). `bga_replay_parser/replay_io.py` is the one place that reads and writes them (`read_replay_html`, `write_replay_html`, `find_replay`, `list_replays`); it also reads plain `.html`. From a shell: `zstdcat replay_123.html.zst | less`, `zstdgrep pattern replay_123.html.zst`.

`scrape_raw_replay.py` refuses to save an HTML page without a populated `g_gamelogs` (error `no_gamelogs`), and always drops unfinished tables: `normalend: False`, `concede: True`, or every player scoring 0/1 (BGA reports most abandoned games as a normal end, so the score signature is the reliable check).

Defaults for `--raw-format` per game come from `bga_replay_parser.constants.RAW_FORMAT_BY_GAME`. `--rotate-accounts` requires an `accounts.py` (see `accounts.example.py`). The `table_ids.json` input is the file emitted by `index_top_players.py`.

### Index a game's top-N Arena players

```bash
python index_top_players.py tokaido -n 100          # by short name
python index_top_players.py 1003 -n 100             # equivalent (numeric BGA game ID)
python index_top_players.py terra_mystica -n 200 --since 2025-01-01 --until 2025-12-31
python index_top_players.py wingspan -n 200 --players 2 3          # enrich 2p and 3p tables
python index_top_players.py wingspan --players 2 3 --tables-from data/batch/wingspan/raw   # enrich-only
```

Walks the leaderboard top-N, fetches each player's game history, enriches each table of a wanted player count with `tableinfos` data (`--players`, default `4`; other player counts are kept unenriched), writes a `progress_collect.json` resumable progress file plus the `table_ids.json` that `scrape_raw_replay.py` consumes.

### Batch-parse raw replays to CSV

```bash
# Terra Mystica (input: directory of replay_<table_id>.html.zst files; plain .html also read)
python parse_terra_mystica.py data/batch/terra_mystica/replays/ data/batch/terra_mystica/parsed/ \
    --metadata data/batch/terra_mystica/table_ids.json --exclude-friendly
# -> player_results.csv, moves.csv, round_summaries.csv, leech_offers.csv, auction_bids.csv, setup.csv

# Tokaido (input: directory of <table_id>.json files)
python parse_tokaido.py data/batch/tokaido/raw/
# -> player_results_{base,xroads}.csv, moves_{base,xroads}.csv

# Wingspan (input: directory of <table_id>.json files)
python parse_wingspan.py data/batch/wingspan/raw/
# -> player_results.csv, moves.csv, birds.csv, round_goals.csv, setup.csv
```

Output dir defaults to `<replay_dir>/parsed/` (TerMys) or `<replay_dir>/../parsed/` (Tokaido, Wingspan). Pass an explicit second arg to override.

TM flags: `--metadata` (table_ids.json; supplies ELO, `game_mode`, `starting_vp_setting`), `--exclude-friendly` (skip Friendly-mode games), `--workers N` (default all cores; `1` = sequential). `parse_wingspan.py` takes `--metadata` (ELO columns and setup.csv game options; blank without it) and `--workers` too. All three parsers write to `.tmp` files and swap them in only on a clean finish, so a crashed parse leaves the previous CSVs intact.

Finished data lives in `data/batch/terra_mystica/parsed/` and `data/batch/tokaido/parsed/` (`data/batch/tokaido/raw` is a symlink to `~/Desktop/old-bga-replays/data/tokaido/raw`). `*_snapshot.csv` files in the TM parsed dir are stale April copies.
The TM batch parser skips any replay that yields 0 rounds (a saved non-replay page). Three such pages found in the corpus are parked in `data/batch/terra_mystica/replays_invalid/` and removed from `progress_scrape.json`, so a later scrape re-fetches them.

### Parse one replay from Python

```python
# Terra Mystica
from bga_replay_parser.tm_parser import TerraMysticaParser
parser = TerraMysticaParser()
game = parser.parse_complete_game(html, table_id="12345")
parser.export_to_json(game, "out.json")

# Tokaido
from bga_replay_parser.tokaido_parser import TokaidoParser
parser = TokaidoParser()
game = parser.parse_json_file("data/batch/tokaido/raw/12345.json")

# Wingspan
from bga_replay_parser.wingspan_parser import WingspanParser
game = WingspanParser().parse_json_file("data/batch/wingspan/raw/12345.json")
game.warnings   # failed reconciliation checks, [] when clean
```

### Look at parsed data

Parsed CSVs + quickstart notebooks are published as a Hugging Face dataset:
<https://huggingface.co/datasets/liamdj/bga-replays>

## Project structure

```
bga_replay_parser/             # Library
  bga_session.py            # Auth: Selenium login + cookie transfer to requests.Session
  scraper.py                # BGAScraper: gamereview -> replay page (HTML), or archive logs API (JSON)
  leaderboard_scraper.py    # Top-N Arena/ELO players via BGA JSON API
  games_registry.py         # CSV dedup tracker (composite key: table_id + player_perspective); not used by current scripts
  players_registry.py       # CSV leaderboard cache; not used by current scripts
  constants.py              # Project constants (URLs, game IDs, speed profiles, data dirs)
  replay_io.py              # Read/write raw replay HTML (zstd-compressed .html.zst, or plain .html)
  tm_parser.py              # Terra Mystica parser: HTML -> TMGameData
  tm_models.py              # TMGameData, TMPlayerResult, TMRoundSummary, TMMove
  tm_constants.py           # Factions, tile names, excluded factions
  tm_handlers.py            # BGA event handlers (EVENT_HANDLERS dispatch table)
  tm_csv.py                 # TM batch loop + CSV flattening (used by parse_terra_mystica.py)
  tokaido_parser.py         # Tokaido parser: JSON gamelogs -> TokaidoGameData
  tokaido_models.py         # TokaidoGameData, TokaidoPlayerResult, TokaidoMove
  tokaido_constants.py      # Souvenir/position/object lookups
  tokaido_csv.py            # Tokaido batch loop + CSV flattening (used by parse_tokaido.py)
  wingspan_parser.py        # Wingspan parser: JSON gamelogs -> WingspanGameData
  wingspan_models.py        # WingspanGameData, WingspanPlayerResult, WingspanMove, WingspanBird, WingspanRoundGoal
  wingspan_constants.py     # Bird / bonus card / round goal / food id lookups
  wingspan_csv.py           # Wingspan batch loop + CSV flattening (used by parse_wingspan.py)

# Entry-point scripts
scrape_raw_replay.py        # Scrape one or many raw replays (game-agnostic)
index_top_players.py        # Index top-Arena players' games -> table_ids.json
parse_terra_mystica.py      # Batch-parse TerMys replay HTMLs -> CSVs
parse_tokaido.py            # Batch-parse Tokaido replay JSONs -> CSVs
parse_wingspan.py           # Batch-parse Wingspan replay JSONs -> CSVs

# Config
config.py                   # User-specific (credentials, Chrome path) - gitignored
config.example.py           # Template
accounts.py                 # Optional extra accounts for --rotate-accounts - gitignored
accounts.example.py         # Template

# Docs
AGENTS.md                   # This file: repo-wide guide for coding agents (CLAUDE.md just imports it)
docs/README.md              # Index of game reference docs
docs/terra_mystica/         # parser.md, rules, factions, BGA replay format
docs/tokaido/               # parser.md, rules, Crossroads, travelers, BGA replay format
docs/wingspan/              # parser.md, rules, cards (birds.csv, bird_data.json), BGA replay format

# Published separately (not in this repo)
# - Parsed CSVs + quickstart notebooks: huggingface.co/datasets/liamdj/bga-replays
# - Raw + parsed local data (gitignored): data/
```

## How BGA scraping works

### Authentication (bga_session.py)

`BGASession` handles login via Selenium browser automation:
1. Launches Chrome via Selenium WebDriver (uses webdriver-manager by default).
2. Navigates to `https://en.boardgamearena.com/account`.
3. Two-step form: enters email -> clicks Next -> enters password -> clicks Login.
4. Uses multiple CSS/XPath selector fallbacks for form fields.
5. JavaScript fallback clicks when overlays block normal clicks.
6. Verifies auth by checking for logout link in page source.
7. Cookies are available on the Selenium driver; a `requests.Session` is also maintained for direct HTTP.

Credentials come from `config.py` (`BGA_EMAIL`, `BGA_PASSWORD`).

### Scraping pipeline (scraper.py)

`BGAScraper` wraps a logged-in `BGASession`. `scrape_raw_replay.py` drives it in one of two modes per table.

**HTML mode** (`--raw-format html`, Terra Mystica):
1. `extract_version_from_gamereview(table_id)` — Selenium loads `https://boardgamearena.com/gamereview?table={table_id}` and regex-extracts the version ID (format `NNNNNN-NNNN`) from replay links.
2. The script builds `https://boardgamearena.com/archive/replay/{version_id}/?table={table_id}&player={player_id}&comments={player_id}` (player_id comes from the `table_ids.json` metadata).
3. `scrape_replay(url)` — Selenium loads the replay, waits for the `g_gamelogs` JS variable or `div.replaylogs_move` elements, falls back to a direct `requests.Session` GET if content isn't found, and detects the daily replay limit, deleted replays, and auth failures. Returns the page HTML.

**JSON mode** (`--raw-format json`, Tokaido, Wingspan):
- `scrape_replay_logs_json(table_id)` — runs synchronous XHRs from the logged-in browser: `/gamereview/gamereview/requestTableArchive.html?table={table_id}` (warm-up), then `/archive/archive/logs.html?table={table_id}&translated=true`, which returns the gamelogs as JSON. No gamereview or replay page load. Suitable only when the parser doesn't need `gameui.completesetup` gamedatas.

Table metadata (players, ELO, game options) is not scraped here — `index_top_players.py` gets it from the `/gamestats/gamestats/getGames.html` and `/table/table/tableinfos.html` APIs.

Set `BGA_DEBUG=1` (or `BGA_DEBUG_ALWAYS=1`) to dump debug artifacts for failed replay loads.

### Leaderboard API (leaderboard_scraper.py)

Uses `requests.Session` (not Selenium) to hit a JSON API:
- URL: `/gamepanel/gamepanel/getRanking.html?game={game_id}&mode={arena|elo}&start={offset}`
- Paginates 10 players at a time.
- Returns `(player_id, player_name, country, arena_rank)` tuples.
- Game IDs in `bga_replay_parser.constants.GAME_IDS`.

### Speed control

`bga_replay_parser.constants.SPEED_PROFILES` defines FAST/NORMAL/SLOW. The user picks one via `config.SPEED_PROFILE`. The scraper reads:
- `page_load_delay`: wait after replay navigation (2–5s)
- `element_wait_timeout`: max WebDriverWait on gamereview/replay pages (5–12s)

### Game IDs and raw format

```python
# bga_replay_parser/constants.py
GAME_IDS           = {"terra_mystica": 1118, "tokaido": 1003, "wingspan": 1635}
RAW_FORMAT_BY_GAME = {"terra_mystica": "html", "tokaido": "json", "wingspan": "json"}
```

`scrape_raw_replay.py` picks raw format from `constants.RAW_FORMAT_BY_GAME` (or `--raw-format` to override). HTML mode loads the full replay page; JSON mode hits the BGA archive API directly and saves `<table_id>.json`. JSON is cheaper but only suitable when the parser doesn't need `gameui.completesetup` gamedatas.

## Game parsers

Each game's parser is documented next to its other docs. **Read the game's `parser.md` before changing that game's parser, models or CSV output, or analysing its parsed data** — it holds the output columns, BGA event quirks, skip rules and reconciliation checks that are not repeated here.

| Game | Parser doc | Raw replay format | Code |
|------|------------|-------------------|------|
| Terra Mystica | [docs/terra_mystica/parser.md](docs/terra_mystica/parser.md) | [bga_replay_format.md](docs/terra_mystica/bga_replay_format.md) | `bga_replay_parser/tm_*.py` |
| Tokaido | [docs/tokaido/parser.md](docs/tokaido/parser.md) | [bga_replay_format.md](docs/tokaido/bga_replay_format.md) | `bga_replay_parser/tokaido_*.py` |
| Wingspan | [docs/wingspan/parser.md](docs/wingspan/parser.md) | [bga_replay_format.md](docs/wingspan/bga_replay_format.md) | `bga_replay_parser/wingspan_*.py` |

Rules and card/faction reference for each game are indexed in [docs/README.md](docs/README.md). When a parser's behaviour or output changes, update its `parser.md` in the same change.

## Adapting to another game

**Game-agnostic (reusable as-is):**
- `BGASession` — auth flow
- `BGAScraper` table + gamereview + replay navigation pattern
- `GamesRegistry` / `PlayersRegistry` — CSV dedup tracking (not wired into the current scripts)
- `LeaderboardScraper` — just change `game_id`
- `index_top_players.py` — game-agnostic indexing via getGames + tableinfos APIs
- `bga_replay_parser/constants.py` — add an entry to `GAME_IDS` and `RAW_FORMAT_BY_GAME`
- `config.py` structure (credentials, Chrome path, speed-profile preference)
- Replay URL template (in `constants.REPLAY_URL_TEMPLATE`)
- Brace-balanced JSON extraction from HTML (g_gamelogs, completesetup)

**Game-specific (must be written):**
- Parser + event handlers
- Dataclasses (game state model)
- Mapping of the game's tableinfos options (map, expansions, variants) to metadata columns
- A batch CLI script (model on `parse_terra_mystica.py`, `parse_tokaido.py` or `parse_wingspan.py`)

BGA game IDs are visible in leaderboard URLs or the game's page on BGA.

## Dependencies

`requests`, `beautifulsoup4`, `selenium`, `webdriver-manager`, `zstandard`. (No `pandas` runtime dep; the quickstart notebooks that need it live in the HF dataset repo.)
