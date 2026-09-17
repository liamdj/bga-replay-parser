# BGA Replay Parser

## Overview

Scrapes and parses BoardGameArena (BGA) replays for two games: Terra Mystica and Tokaido. The BGA interaction layer (auth, page navigation, leaderboard) is game-agnostic; each game has its own parser/handlers/models.

This repo is a library + a handful of CLI entry points. It is **not** an end-user app — the original Tkinter GUI, FastAPI service, `main.py` CLI, and the Terraforming Mars parser from upstream have all been removed. See [README.md](README.md) for lineage. For TM parsing, use upstream [HStrand/bga-tm-scraper](https://github.com/HStrand/bga-tm-scraper).

## Config vs constants

Project constants (URLs, game IDs, raw-format routing, speed profiles, default data dirs) live in [`bga_replay_parser/constants.py`](bga_replay_parser/constants.py) — tracked, never edited per user.

User-specific values (credentials, Chrome path, speed-profile preference, request delay) live in `config.py`. The repo ships [`config.example.py`](config.example.py); copy it to `config.py` (gitignored) and fill in.

## Common tasks

Use the snippets below verbatim. Don't recreate the deleted GUI/scheduler/`main.py`/`web_service.py` — they were removed intentionally.

### Scrape one or many raw replays

```bash
# JSON-based games (Tokaido): cheaper, hits the BGA archive API directly
python scrape_raw_replay.py --file table_ids.json --raw-format json

# HTML-based games (Terra Mystica): loads the full replay page via Selenium
python scrape_raw_replay.py --file table_ids.json --raw-format html

# Multi-account rotation (works around BGA daily replay limit)
python scrape_raw_replay.py --file table_ids.json --rotate-accounts

# Current TM corpus filter (--ranked drops Friendly-mode games)
python scrape_raw_replay.py --file data/batch/terra_mystica/table_ids.json --raw-format html \
    --players 4 --map "Base Game" "Random" "Fjords" "Fire & Ice" \
    --min-elo 200 --min-top-elo 400 --ranked --rotate-accounts
```

`scrape_raw_replay.py` refuses to save an HTML page without a populated `g_gamelogs` (error `no_gamelogs`), and always drops unfinished tables: `normalend: False`, `concede: True`, or every player scoring 0/1 (BGA reports most abandoned games as a normal end, so the score signature is the reliable check).

Defaults for `--raw-format` per game come from `bga_replay_parser.constants.RAW_FORMAT_BY_GAME`. `--rotate-accounts` requires an `accounts.py` (see `accounts.example.py`). The `table_ids.json` input is the file emitted by `index_top_players.py`.

### Index a game's top-N Arena players

```bash
python index_top_players.py tokaido -n 100          # by short name
python index_top_players.py 1003 -n 100             # equivalent (numeric BGA game ID)
python index_top_players.py terra_mystica -n 200 --since 2025-01-01 --until 2025-12-31
```

Walks the leaderboard top-N, fetches each player's game history, enriches each 4-player table with `tableinfos` data (other player counts are kept unenriched), writes a `progress_collect.json` resumable progress file plus the `table_ids.json` that `scrape_raw_replay.py` consumes.

### Batch-parse raw replays to CSV

```bash
# Terra Mystica (input: directory of replay_<table_id>.html files)
python parse_terra_mystica.py data/batch/terra_mystica/replays/ data/batch/terra_mystica/parsed/ \
    --metadata data/batch/terra_mystica/table_ids.json --exclude-friendly
# -> player_results.csv, moves.csv, round_summaries.csv, auction_bids.csv, setup.csv

# Tokaido (input: directory of <table_id>.json files)
python parse_tokaido.py data/batch/tokaido/raw/
# -> player_results_{base,xroads}.csv, moves_{base,xroads}.csv
```

Output dir defaults to `<replay_dir>/parsed/` (TerMys) or `<replay_dir>/../parsed/` (Tokaido). Pass an explicit second arg to override.

TM flags: `--metadata` (table_ids.json; supplies ELO, `game_mode`, `starting_vp_setting`), `--exclude-friendly` (skip Friendly-mode games), `--workers N` (default all cores; `1` = sequential). Both parsers write to `.tmp` files and swap them in only on a clean finish, so a crashed parse leaves the previous CSVs intact.

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
  tm_parser.py              # Terra Mystica parser: HTML -> TMGameData
  tm_models.py              # TMGameData, TMPlayerResult, TMRoundSummary, TMMove
  tm_constants.py           # Factions, tile names, excluded factions
  tm_handlers.py            # BGA event handlers (EVENT_HANDLERS dispatch table)
  tm_csv.py                 # TM batch loop + CSV flattening (used by parse_terra_mystica.py)
  tokaido_parser.py         # Tokaido parser: JSON gamelogs -> TokaidoGameData
  tokaido_models.py         # TokaidoGameData, TokaidoPlayerResult, TokaidoMove
  tokaido_constants.py      # Souvenir/position/object lookups
  tokaido_csv.py            # Tokaido batch loop + CSV flattening (used by parse_tokaido.py)

# Entry-point scripts
scrape_raw_replay.py        # Scrape one or many raw replays (game-agnostic)
index_top_players.py        # Index top-Arena players' games -> table_ids.json
parse_terra_mystica.py      # Batch-parse TerMys replay HTMLs -> CSVs
parse_tokaido.py            # Batch-parse Tokaido replay JSONs -> CSVs

# Config
config.py                   # User-specific (credentials, Chrome path) - gitignored
config.example.py           # Template
accounts.py                 # Optional extra accounts for --rotate-accounts - gitignored
accounts.example.py         # Template

# Docs
docs/README.md              # Index of game reference docs
docs/terra_mystica/         # rules, factions, BGA replay format
docs/tokaido/               # rules, Crossroads, travelers, BGA replay format

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

**JSON mode** (`--raw-format json`, Tokaido):
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
GAME_IDS           = {"terra_mystica": 1118, "tokaido": 1003}
RAW_FORMAT_BY_GAME = {"terra_mystica": "html", "tokaido": "json"}
```

`scrape_raw_replay.py` picks raw format from `constants.RAW_FORMAT_BY_GAME` (or `--raw-format` to override). HTML mode loads the full replay page; JSON mode hits the BGA archive API directly and saves `<table_id>.json`. JSON is cheaper but only suitable when the parser doesn't need `gameui.completesetup` gamedatas.

## Terra Mystica Parser

`TerraMysticaParser` in `tm_parser.py` converts raw BGA replay HTML into `TMGameData`; `tm_csv.py` flattens that into five CSVs (player results, round summaries, moves, auction bids, setup). Uses `tm_models.py` for dataclasses, `tm_handlers.py` for event dispatch, `tm_constants.py` for faction/tile lookups.

### Data extraction

Two JSON sources are extracted from replay HTML:
1. **g_gamelogs** — game log packets (brace-balanced extraction from `g_gamelogs = {...}`).
2. **gamedatas** — static game setup from `gameui.completesetup(...)` call. Contains bonus_card_types, scoring_tile_types, favor_tile_types, town_tile_types (static defs) plus per-game assignments.

### Output views

**TMPlayerResult** — one row per player per game (~41 fields):
- Identity: player_id, player_name, faction, terrain, color, seat_order
- VP breakdown: starting_vp, final_vp, vp_round_scoring, vp_favor_tiles, vp_bonus_cards, vp_towns, vp_faction_ability, vp_power_leaching (≤0), vp_conversions (≤0, Alchemists), vp_track_advances, vp_cult_final, vp_network_final, vp_resources_final
- Structures: dwellings/trading_houses/temples/strongholds/sanctuaries_built, bridges_built, towns_formed
- Cult: cult_fire/water/earth/air (final positions, 0–10)
- Economy: total_coins/workers/priests/power_produced (income + cult bonuses across all rounds)
- Tracks: shipping_level, exchange_level, network_size
- Tiles: favor_tiles (list), town_tiles (list), bonus_cards (list of 6 in round order)

**TMRoundSummary** — one row per player per round (~34 fields):
- Round context: round_number, scoring_tile, bonus_card (held this round)
- Income phase: income_coins/workers/priests/power
- Cult bonuses (cleanup): cult_bonus_coins/workers/priests/power/spades
- Actions: num_actions, spades_used, dwellings_built, structures_upgraded, cult_advances, power_actions_used, towns_founded
- Power actions: power_actions (list of types like `["spade", "coins"]`)
- Power gained: power_gained_via_structures/cults/other
- End-of-round state: vp_at_round_end, coins/workers_at_round_end, power_bowl1/2/3, cult positions
- Pass: pass_order (1=first)

**TMMove** — one row per action (~33 fields, ~500 per game):
- Action types: select_faction, place_initial_dwelling, select_bonus_card, transform_terrain, build_dwelling, upgrade_structure, advance_cult, send_priest_to_cult, advance_shipping, advance_exchange, power_action, special_action, found_town, choose_favor_tile, choose_bonus_card, receive_income, receive_cult_bonus, round_scoring, final_scoring, pass, power_via_structures, other
- Context: hex_coord, structure_type, upgraded_from, terrain_from/to, cult_track, cult_from/to, tile_or_card
- Cost/gain: cost_workers/coins/priests/power, gain_vp/coins/workers/priests/power

**TMAuctionBid** (`auction_bids.csv`) — one row per (player, faction) bid in auction games: faction, bid_starting_vp, is_winning_bid. Fast auctions have exactly one bid per pair; slow (standard) auctions are collapsed to each player's last bid on each faction, so the table is sparse (only factions that player bid on). `TMGameData.auction_type` (`"fast"`/`"slow"`/`""`) is derived from bid sequences and is the reliable auction indicator; the `starting_vp_setting` game-option label is unreliable pre-2023.

**setup.csv** — one row per game: game-level `TMGameData` fields (board, options, scoring tiles, bonus cards, winner), plus `game_mode` and `starting_vp_setting` from table metadata. `with_auction` = bids present OR the gamedatas flag (the flag alone misses ~12k pre-2023 slow auctions). Use `auction_type != ""` to select auction games, never `starting_vp_setting`.

### Event handling

`EVENT_HANDLERS` in `tm_handlers.py` maps every BGA event type seen in replays (~56) to a handler; about half are explicit no-ops. Key quirks:
- `incomePhase` is its own event type (not `justAMessage`). Fires once with no player_id (round marker) then per-player with income HTML.
- `someIncome` during cleanup phase carries cult bonus resources (detected via `addendum="(Cult bonus)"`).
- `townBonus` VP is not tracked via `updateScore` — captured directly from townBonus event.
- `powerViaStructures` VP cost is silent — detected from newScore field.
- Round 6 has no Cleanup phase marker — goes straight to `~ Final scoring ~`.

### Excluded factions

`should_skip_replay()` skips games with: shapeshifters, riverwalkers, changelings, geologists, dragonlords, acolytes, firewalkers, kingdomofember. Also skips games with the landscapes expansion.

### VP reconciliation

Sum of VP components (starting_vp + all `vp_*` columns) equals `final_vp` exactly for 99.99% of player rows; the remainder are conceded-game artifacts. Three handler details make this hold: `powerActionBridge` buckets the Architects-stronghold VP from `score_inc` (the follow-up updateScore has score_delta=0), `advanceIncomeTrack` buckets Chash Dallah income-track VP the same way, and `factionBoardSwapped` initializes player state (fan-faction games have no `factionPositionSelected`; without init the starting-VP updateScore was dropped and mis-bucketed later). Alchemists have negative `vp_conversions` (VP→coins).

## Tokaido Parser

`TokaidoParser` in `tokaido_parser.py` reads BGA Tokaido replays into per-player and per-move CSV-friendly views. Uses `tokaido_models.py` for dataclasses and `tokaido_constants.py` for souvenir/position/object lookups. Event dispatch is inline.

### Raw input format

Tokaido raw replays are stored as JSON gamelogs (the format produced by the BGA `/archive/archive/logs.html` API): a flat list of packets, each with a `data: [...events]` array. Same packet schema as the inner `g_gamelogs.data.data` list extracted from HTML replays — the parser also accepts the dict-wrapped form for symmetry with TerMys.

### Output: 4 CSVs, base and Crossroads kept separate

Base game and Crossroads expansion differ enough that mixing them adds noise (19 Crossroads-only VP/count/flag columns would be 0 in every base row). Each game routes to one of two player files and one of two moves files:

- `player_results_base.csv` — one row per player per base game (42 columns)
- `player_results_xroads.csv` — one row per player per Crossroads game (61 columns: base + 19 Crossroads-only)
- `moves_base.csv` — one row per action in a base game (15 columns)
- `moves_xroads.csv` — one row per action in a Crossroads game (same columns; only `type` value space differs)

`game.has_crossroads` is set during parsing — true if any of `CherryTree`, `BathHouse`, `Calligraphy`, `CalligraphyScored`, `LegendaryObject`, `Amulet`, `AmuletUsed` move types appear.

**TokaidoPlayerResult**:
- Game: table_id, num_players, preparations (bool: Preparations expansion in play)
- Identity: player_id, player_name, player_color, traveler, starting_position, starting_coins (post-Preparations allocation when that expansion is on)
- Result: final_score, score_aux (BGA tiebreaker = achievements count), final_rank, is_winner
- VP breakdown (sums to final_score for all but ~9 of ~270K rows — see VP reconciliation): vp_panorama_mountain/sea/field, vp_temple, vp_temple_rank, vp_hot_spring, vp_encounter, vp_inn, vp_village, vp_achievement, vp_other (+ Crossroads-only: vp_calligraphy, vp_legendary_script/offering/sword, vp_bath_house, vp_cherry_tree, vp_legend_bonus)
- Donation routing: vp_temple includes Miko encounter VP and Devotion-amulet VP (both are temple donations); num_donations counts these too. Miko still increments num_encounters; Devotion still increments num_amulets_used. There is no `vp_amulet_used` column — Devotion is the only amulet that scores VP, and it goes to vp_temple.
- Action counts: num_actions, num_meals, num_encounters, num_villages_visited, num_donations, num_panorama_cards_mountain/sea/field, first_to_finish_mountain/sea/field (bools), num_souvenirs_food/clothing/art/trinket (+ Crossroads-only: num_amulets_purchased/used, num_calligraphies, num_legendary_script/offering/sword, has_calligraphy_foresight/contemplation/nostalgia/patience/perfection/fasting bools)
- Economy: coins_gained_total, coins_spent_total, coins_donated_total

The Crossroads-only field list lives at `bga_replay_parser.tokaido_models.XROADS_ONLY_PLAYER_FIELDS` (what the writer drops for the base CSV). Calligraphy `type_arg → name` mapping in `tokaido_constants.CALLIGRAPHY_TYPE_ARG_TO_NAME`.

**TokaidoMove** — one row per scoring/economy action (~200 per game):
- table_id, move_number, player_id, traveler, type, subtype, space
- coins_gained, coins_spent, coins_donated, points_gained
- souvenirs_food/clothing/art/trinket

### Move types (the `type` column)

`Traveled`, `Village`, `Temple`, `TempleRank`, `HotSpring`, `Panorama`, `Inn`, `RoadMeal`, `Encounter`, `Achievement`, `Farm`, `CherryTree`, `BathHouse`, `LegendaryObject`, `Calligraphy`, `CalligraphyScored`, `Amulet`, `AmuletUsed`, `Gaming`, `JirochoGaming`, `DaigoroSouvenir`, `LegendBonus`, `TravelerAbility`. The Crossroads-only types are also flagged at the game level via `has_crossroads`.

`RoadMeal` is the meal from The New Encounters' Itamae card (scored into `vp_inn`/`num_meals` but not an Inn stop). New Encounters paid cards (Itamae, Kitoushi, Takuhatsuso) are `Encounter` rows with `coins_spent=1`; Saru's VP goes to `vp_hot_spring`. See `docs/tokaido/bga_replay_format.md` → Encounters.

The parser uses `Panorama` with the color in `subtype` (not separate `Mountain`/`Sea`/`Field` types). `Achievement` rows for completed panoramas use `subtype="mountain_panorama"` etc.

### VP reconciliation

Sum of `vp_*` components equals `final_score` for all but ~9 of ~270K player rows (small unexplained positive gaps). The 21 games with sentinel `score_aux` (-4245 abandoned, -4242 zeroed result) used to account for another ~84 negative-residual rows; they are now skipped.

Until 2026-09 the parser missed The New Encounters cards (Saru, Takuhatsuso, Itamae's road meal), which left 1.7% of base rows and 11.4% of Crossroads rows short by typically 2–10 VP — concentrated in Preparations games only because those tables have The New Encounters on 55% of the time (vs 9% otherwise). CSVs parsed before that fix carry the gap.

Traveler abilities are handled correctly: the parser captures explicit traveler-ability log lines (`Hirotada: ...`, `Umegae: ...`, `Gotozaemon: ...`, `Nampo: ...`, `Mitsukuni: ...`) as their own `TravelerAbility` rows rather than inlining the bonus on the main action — modern BGA replays emit both, so inlining would double-count.

### Skip logic

`should_skip(packets)` returns a reason string for:
- Fewer than 3 players (2p Tokaido is unsupported).
- A negative `score_aux` in the replay's result block (normal games have `score_aux` ≥ 0 = achievement count): `-4245` = abandoned (remaining players scored 1, the leaver 0); `-4242` = finished game whose archived result is zeroed (all 0, all rank 1), so `final_score`/rank are unusable.

 Preparations games are parsed: the expansion only redistributes starting coins, which `travelerChosen.player_coins` already reflects; the `preparations` column flags them.

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
- A batch CLI script (model on `parse_terra_mystica.py` or `parse_tokaido.py`)

BGA game IDs are visible in leaderboard URLs or the game's page on BGA.

## Dependencies

`requests`, `beautifulsoup4`, `selenium`, `webdriver-manager`. (No `pandas` runtime dep; the quickstart notebooks that need it live in the HF dataset repo.)
