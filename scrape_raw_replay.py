#!/usr/bin/env python3
"""
Scrape raw replay data from BGA (game-agnostic). Two raw-format modes:

  --raw-format html (default)
      Selenium-loads the full replay page and saves replay_<table>.html.
      Required for games whose parser uses `gameui.completesetup` gamedatas
      (Terra Mystica).

  --raw-format json
      Hits the BGA archive API directly (no replay page load) and saves
      <table>.json — a flat list of gamelogs packets. Cheaper and faster.
      Suitable for games whose parser only needs the gamelogs (Tokaido).

Uses player IDs from metadata — only hits /gamereview + /archive/.
Supports multi-account rotation and filtering by game settings.

Usage:
    python scrape_raw_replay.py --file <table_ids.json> [--rotate-accounts] \
        [--raw-format html|json] [--players 4] [--arena] [--no-fire-ice] \
        [--map "Base Game"] [--min-elo 300] [--min-top-elo 400]
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

import config
from bga_replay_parser import constants
from bga_replay_parser.scraper import BGAScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

REALTIME_THRESHOLD_S = 12 * 3600


class AccountRotator:
    def __init__(self, accounts):
        self.accounts = accounts
        self.current_index = 0

    def current(self):
        return self.accounts[self.current_index]

    def next(self):
        self.current_index += 1
        if self.current_index >= len(self.accounts):
            return None
        return self.accounts[self.current_index]

    def remaining(self):
        return len(self.accounts) - self.current_index - 1


def create_scraper(email, password):
    scraper = BGAScraper(
        chromedriver_path=config.CHROMEDRIVER_PATH,
        chrome_path=config.CHROME_PATH,
        request_delay=config.REQUEST_DELAY,
        headless=True,
        email=email,
        password=password,
    )
    scraper.speed_profile = config.SPEED_PROFILE
    scraper.speed_settings = constants.SPEED_PROFILES[config.SPEED_PROFILE]
    return scraper


def load_progress(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"scraped_table_ids": [], "failed_table_ids": [], "last_updated": None}


def save_progress(path, progress):
    progress["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(progress, f, indent=2)
    os.replace(tmp_path, path)


def is_limit_reached(result):
    """True when the failure means this account can't fetch more replays.

    Covers daily-quota limits AND access revocations / new-account restrictions
    — anything that won't recover without rotating to a different account.
    """
    if not result:
        return False
    return (
        result.get("limit_reached")
        or result.get("daily_limit_reached")
        or result.get("error") in {"replay_limit_reached", "no_replay_access"}
    )


def filter_tables(tables, table_ids, args):
    """Filter table IDs by metadata. Tables without metadata are skipped."""
    if not tables:
        return table_ids

    tables_by_id = {t["table_id"]: t for t in tables if t.get("table_id")}
    filtered = []

    for tid in table_ids:
        t = tables_by_id.get(tid)
        if not t:
            continue

        if t.get("normalend") is False:
            continue

        if args.players is not None and t.get("num_players") != args.players:
            continue

        opts = t.get("options", {})

        if args.arena:
            if "Arena" not in (opts.get("Game mode") or ""):
                continue

        # Exclude Friendly (unranked) games — keep only Normal/Arena.
        if args.ranked:
            if (opts.get("Game mode") or "") == "Friendly mode":
                continue

        if args.map:
            if opts.get("Game board", "") not in args.map:
                continue

        # Standard settings — always enforced (Landscapes can be opted in)
        if not args.allow_landscapes:
            if opts.get("Landscapes expansion") not in (None, "Off"):
                continue
        if args.require_landscapes:
            if opts.get("Landscapes expansion") != "On":
                continue
        if opts.get("Turn order") not in (None, "Variable turn order"):
            continue
        if opts.get("Mini-expansions") not in (None, "On"):
            continue
        if opts.get("Fire and Ice - Final Scoring tiles") not in (None, "Off"):
            continue

        # Faction filters
        if args.base_factions:
            if opts.get("Fire and Ice - Factions") not in (None, "Off"):
                continue
            if opts.get("Fan Factions") not in (None, "Off"):
                continue
        if args.no_fire_ice:
            if opts.get("Fire and Ice - Factions") not in (None, "Off"):
                continue
            if opts.get("Fan Factions") == "On - with Fire & Ice":
                continue

        # Duration filters
        duration = t.get("duration_s")
        if duration is not None:
            if args.real_time and duration >= REALTIME_THRESHOLD_S:
                continue
            if args.turn_based and duration < REALTIME_THRESHOLD_S:
                continue

        # ELO filters
        elo_values = [p["elo_before"] for p in t.get("players", []) if p.get("elo_before") is not None]
        if elo_values:
            if args.min_elo is not None and min(elo_values) < args.min_elo:
                continue
            if args.min_top_elo is not None and max(elo_values) < args.min_top_elo:
                continue

        # Tokaido expansion filters (no-op for games whose options dict doesn't
        # have these keys — e.g. TM games — since opts.get returns None).
        if args.crossroads and opts.get("Crossroads") != "On":
            continue
        if args.gastronomy and opts.get("Gastronomy") != "On":
            continue
        if args.no_preparations and opts.get("Preparations") == "On":
            continue
        if args.no_new_encounters and opts.get("The New Encounters") == "On":
            continue
        if args.no_initiation and opts.get("Initiation") == "On":
            continue
        if args.no_return_trip and opts.get("Return trip") == "On":
            continue

        filtered.append(tid)

    return filtered


def _is_browser_dead(scraper):
    """Return True if the Selenium session has died (tab crashed, disconnected)."""
    try:
        _ = scraper.driver.current_url
        return False
    except Exception:
        return True


def scrape_one_table(scraper, table_id, player_id, out_dir, raw_format="html"):
    """Scrape one table's replay in the chosen raw format.

    raw_format == "html": navigates /gamereview + the replay page, saves
        replay_<table_id>.html.
    raw_format == "json": hits the BGA archive API directly, saves
        <table_id>.json (a flat list of gamelogs packets).
    """
    os.makedirs(out_dir, exist_ok=True)

    if raw_format == "json":
        result = scraper.scrape_replay_logs_json(table_id)
        if _is_browser_dead(scraper):
            return {"success": False, "error": "browser_crashed",
                    "limit_reached": False, "deleted": False, "browser_dead": True}
        if not result.get("success"):
            err = result.get("error") or "scrape_failed"
            return {"success": False, "error": err,
                    "limit_reached": bool(result.get("limit_reached")),
                    "deleted": bool(result.get("deleted"))}
        with open(os.path.join(out_dir, f"{table_id}.json"), "w", encoding="utf-8") as f:
            json.dump(result["logs"], f, ensure_ascii=False)
        return {"success": True, "error": None, "limit_reached": False, "deleted": False}

    # html (default)
    version_id = scraper.extract_version_from_gamereview(table_id)
    if not version_id:
        if _is_browser_dead(scraper):
            return {"success": False, "error": "browser_crashed", "limit_reached": False, "deleted": False, "browser_dead": True}
        return {"success": False, "error": "no_version_id", "limit_reached": False, "deleted": False}

    replay_url = (
        f"https://boardgamearena.com/archive/replay/{version_id}/"
        f"?table={table_id}&player={player_id}&comments={player_id}"
    )
    result = scraper.scrape_replay(replay_url, save_raw=False)

    if not result:
        if _is_browser_dead(scraper):
            return {"success": False, "error": "browser_crashed", "limit_reached": False, "deleted": False, "browser_dead": True}
        return {"success": False, "error": "scrape_failed", "limit_reached": False, "deleted": False}
    if is_limit_reached(result):
        return {"success": False, "error": "replay_limit_reached", "limit_reached": True, "deleted": False}
    if result.get("replay_deleted") or result.get("error") == "replay_deleted":
        return {"success": False, "error": "replay_deleted", "limit_reached": False, "deleted": True}

    replay_html = result.get("html_content", "")
    if not replay_html:
        return {"success": False, "error": "empty_content", "limit_reached": False, "deleted": False}

    with open(os.path.join(out_dir, f"replay_{table_id}.html"), "w", encoding="utf-8") as f:
        f.write(replay_html)

    return {"success": True, "error": None, "limit_reached": False, "deleted": False}


def main():
    parser = argparse.ArgumentParser(description="Scrape raw BGA replay HTML.")
    parser.add_argument("--file", type=str, required=True,
                        help="JSON file with table IDs and metadata (from index_top_players.py)")
    parser.add_argument("-o", "--output-dir", default=None, help="Output directory")
    parser.add_argument("--rotate-accounts", action="store_true",
                        help="Rotate through accounts in accounts.py when replay limit is hit")
    parser.add_argument(
        "--raw-format", choices=["html", "json"], default=None,
        help="Raw replay format. 'html' loads the full replay page (needed for "
             "TM/Terra Mystica). 'json' fetches just the gamelogs JSON via the "
             "BGA archive API (cheaper; works for Tokaido). Defaults to "
             "constants.RAW_FORMAT_BY_GAME[<game_id>] when present, else 'html'.",
    )

    filters = parser.add_argument_group("filters")
    filters.add_argument("--players", type=int, default=None,
                         help="Only scrape games with this many players")
    filters.add_argument("--arena", action="store_true",
                         help="Only scrape arena games")
    filters.add_argument("--ranked", action="store_true",
                         help="Exclude Friendly (unranked) games — keep Normal/Arena only")
    filters.add_argument("--map", type=str, nargs="+", default=None,
                         help='Only scrape games on these maps (e.g. "Base Game" "Random")')
    filters.add_argument("--base-factions", action="store_true",
                         help="Base factions only (no Fire & Ice or Fan factions)")
    filters.add_argument("--no-fire-ice", action="store_true",
                         help="No Fire & Ice factions (fan factions still allowed)")
    filters.add_argument("--allow-landscapes", action="store_true",
                         help="Allow Landscapes expansion (default: only Landscapes Off)")
    filters.add_argument("--require-landscapes", action="store_true",
                         help="Only scrape games with Landscapes On (implies --allow-landscapes)")
    filters.add_argument("--real-time", action="store_true",
                         help=f"Real-time games only (< {REALTIME_THRESHOLD_S // 3600}h)")
    filters.add_argument("--turn-based", action="store_true",
                         help=f"Turn-based games only (>= {REALTIME_THRESHOLD_S // 3600}h)")
    filters.add_argument("--min-elo", type=int, default=None,
                         help="Min starting ELO for all players")
    filters.add_argument("--min-top-elo", type=int, default=None,
                         help="Min starting ELO for the highest-rated player")
    # Tokaido option filters (no-op for games without these options).
    filters.add_argument("--crossroads", action="store_true",
                         help="Tokaido: only games with Crossroads expansion On")
    filters.add_argument("--gastronomy", action="store_true",
                         help="Tokaido: only games with Gastronomy expansion On")
    filters.add_argument("--no-preparations", action="store_true",
                         help="Tokaido: exclude games with Preparations expansion On")
    filters.add_argument("--no-new-encounters", action="store_true",
                         help="Tokaido: exclude games with The New Encounters expansion On")
    filters.add_argument("--no-initiation", action="store_true",
                         help="Tokaido: exclude games with Initiation On")
    filters.add_argument("--no-return-trip", action="store_true",
                         help="Tokaido: exclude games with Return Trip On")

    args = parser.parse_args()

    if args.real_time and args.turn_based:
        parser.error("Cannot use both --real-time and --turn-based")
    if args.require_landscapes:
        args.allow_landscapes = True

    # Load data — accept both formats:
    #   final table_ids.json (table_ids: list, tables: list of dicts, game_id present)
    #   partial progress_collect.json (tables: dict keyed by table_id, no game_id/table_ids)
    with open(args.file, "r") as f:
        data = json.load(f)

    raw_tables = data.get("tables")
    if isinstance(raw_tables, dict):
        # progress_collect.json format — normalize to list with table_id set
        tables = []
        for tid, t in raw_tables.items():
            if "options" not in t:
                continue  # un-enriched; skip
            entry = dict(t)
            entry["table_id"] = tid
            tables.append(entry)
        table_ids = [t["table_id"] for t in tables]
        all_input_count = len(table_ids)
    else:
        tables = raw_tables
        table_ids = data["table_ids"]
        all_input_count = len(data["table_ids"])

    game_id = data.get("game_id", "unknown")
    if game_id == "unknown":
        # Infer from path: progress_collect.json sits at data/batch/<slug>/...
        parent = os.path.basename(os.path.dirname(os.path.abspath(args.file)))
        if parent in constants.GAME_IDS:
            game_id = constants.GAME_IDS[parent]

    # Resolve game slug (short name) from constants.GAME_IDS — used for output dir
    # and raw-format lookup. Falls back to the numeric game_id if no slug exists.
    slug = next((name for name, gid in constants.GAME_IDS.items() if gid == game_id), None)

    # Resolve raw-format: --raw-format > constants.RAW_FORMAT_BY_GAME[<slug>] > "html"
    raw_format = args.raw_format or constants.RAW_FORMAT_BY_GAME.get(slug, "html")
    print(f"Raw format: {raw_format}")

    # Build player ID lookup
    player_id_lookup = {}
    if tables:
        for t in tables:
            tid = t.get("table_id")
            players = t.get("players", [])
            if tid and players:
                player_id_lookup[tid] = players[0]["id"]

    # Apply filters
    table_ids = filter_tables(tables, table_ids, args)

    # Output dir: replays/ for HTML, raw/ for JSON (matches Tokaido convention)
    default_subdir = "replays" if raw_format == "html" else "raw"
    out_dir = args.output_dir or f"data/batch/{slug or game_id}/{default_subdir}"
    progress_path = os.path.join(os.path.dirname(out_dir), "progress_scrape.json")
    progress = load_progress(progress_path)
    scraped_set = set(progress["scraped_table_ids"])
    failed_set = set(progress["failed_table_ids"])

    # Skip already-scraped — file naming differs by format
    if raw_format == "json":
        already_on_disk = {tid for tid in table_ids
                           if os.path.exists(os.path.join(out_dir, f"{tid}.json"))}
    else:
        already_on_disk = {tid for tid in table_ids
                           if os.path.exists(os.path.join(out_dir, f"replay_{tid}.html"))}
    remaining = [tid for tid in table_ids if tid not in scraped_set and tid not in failed_set and tid not in already_on_disk]

    # Print summary
    active_filters = []
    if args.players: active_filters.append(f"players={args.players}")
    if args.arena: active_filters.append("arena")
    if args.map: active_filters.append(f"map={args.map}")
    if args.base_factions: active_filters.append("base-factions")
    if args.no_fire_ice: active_filters.append("no-fire-ice")
    if args.require_landscapes: active_filters.append("require-landscapes")
    elif args.allow_landscapes: active_filters.append("allow-landscapes")
    if args.real_time: active_filters.append("real-time")
    if args.turn_based: active_filters.append("turn-based")
    if args.min_elo is not None: active_filters.append(f"min-elo={args.min_elo}")
    if args.min_top_elo is not None: active_filters.append(f"min-top-elo={args.min_top_elo}")

    if active_filters:
        print(f"\nFilters: {', '.join(active_filters)}")
        print(f"  {all_input_count} total -> {len(table_ids)} matching")

    print(f"\nBatch scrape: {len(remaining)} to scrape ({len(scraped_set) + len(already_on_disk)} already done, {len(failed_set)} failed)")

    if not remaining:
        print("Nothing to scrape.")
        return

    # Set up accounts
    if args.rotate_accounts:
        from accounts import ACCOUNTS
        rotator = AccountRotator(ACCOUNTS)
    else:
        rotator = AccountRotator([(config.BGA_EMAIL, config.BGA_PASSWORD)])

    def login_next_account():
        """Try to log in with the current account, skipping failed ones."""
        while True:
            email, password = rotator.current()
            print(f"  Logging in as {email}...", end=" ")
            scraper = create_scraper(email, password)
            if scraper.start_browser_and_login():
                print("OK")
                return scraper
            else:
                print("FAILED")
                scraper.close_browser()
                if rotator.next() is None:
                    return None

    scraper = login_next_account()
    if not scraper:
        print("All accounts failed to authenticate.")
        sys.exit(1)

    scraped_this_run = 0
    crash_retry_count = 0
    recent_no_version_ids = []  # rolling window of consecutive no_version_id table_ids
    SOFT_LIMIT_THRESHOLD = 30
    try:
        i = 0
        while i < len(remaining):
            table_id = remaining[i]
            player_id = player_id_lookup.get(table_id)

            # JSON mode hits the archive API directly and doesn't need a
            # player perspective; HTML mode constructs replay URLs that do.
            if not player_id and raw_format != "json":
                print(f"\n  [{i + 1}/{len(remaining)}] Table {table_id}... no player ID, skipping")
                i += 1
                continue

            print(f"\n  [{i + 1}/{len(remaining)}] Table {table_id}...", end=" ")

            try:
                result = scrape_one_table(scraper, table_id, player_id, out_dir, raw_format=raw_format)
            except Exception as e:
                logger.error(f"Exception scraping {table_id}: {e}")
                print(f"error: {e}")
                if _is_browser_dead(scraper):
                    result = {"success": False, "error": "browser_crashed", "limit_reached": False, "deleted": False, "browser_dead": True}
                else:
                    i += 1
                    continue

            if result.get("browser_dead"):
                crash_retry_count += 1
                if crash_retry_count > 2:
                    print("BROWSER CRASHED — giving up on this table")
                    failed_set.add(table_id)
                    progress["scraped_table_ids"] = list(scraped_set)
                    progress["failed_table_ids"] = list(failed_set)
                    save_progress(progress_path, progress)
                    crash_retry_count = 0
                    i += 1
                else:
                    print(f"BROWSER CRASHED — restarting (attempt {crash_retry_count})")
                try:
                    scraper.close_browser()
                except Exception:
                    pass
                scraper = login_next_account()
                if not scraper:
                    print(f"\nAll remaining accounts failed to authenticate.")
                    break
                continue  # retry same table (unless we gave up and advanced i)

            crash_retry_count = 0

            # Account-level restrictions: rotate to the next account and retry
            # the SAME table. Covers two cases:
            #   - limit_reached: account hit its daily replay quota (temporary)
            #   - no_replay_access: account is restricted ("must be registered
            #     >24h" / "replaying disabled") — permanent for that account;
            #     the watchdog moves it to accounts.bad.py later.
            # Critically, we do NOT mark the table failed here: the table is
            # fine, it's the account that's the problem. Marking it failed would
            # silently drop a recoverable table from the dataset.
            if result["limit_reached"] or result.get("error") == "no_replay_access":
                if result["limit_reached"]:
                    print("LIMIT REACHED")
                else:
                    print("NO REPLAY ACCESS — account restricted, rotating")
                scraper.close_browser()

                if rotator.next() is None:
                    print(f"\nAll {len(rotator.accounts)} accounts exhausted.")
                    break

                scraper = login_next_account()
                if not scraper:
                    print(f"\nAll remaining accounts failed to authenticate.")
                    break

                continue  # retry same table

            if result["success"]:
                print("OK")
                scraped_set.add(table_id)
                scraped_this_run += 1
                recent_no_version_ids = []
            else:
                print(f"failed: {result['error']}")
                failed_set.add(table_id)
                if result["error"] == "no_version_id":
                    recent_no_version_ids.append(table_id)
                else:
                    recent_no_version_ids = []

            progress["scraped_table_ids"] = list(scraped_set)
            progress["failed_table_ids"] = list(failed_set)
            save_progress(progress_path, progress)

            # Soft-limit detection: if we hit too many consecutive no_version_id
            # failures, the current account is likely replay-banned (or BGA is
            # throttling us). Roll back those false failures and rotate accounts.
            if len(recent_no_version_ids) >= SOFT_LIMIT_THRESHOLD:
                email, _ = rotator.current()
                print(f"\nSOFT LIMIT: {len(recent_no_version_ids)} consecutive no_version_id failures on {email}.")
                print(f"   Likely account replay-banned. Rolling back failures and rotating.")
                for tid_j in recent_no_version_ids:
                    failed_set.discard(tid_j)
                progress["failed_table_ids"] = list(failed_set)
                save_progress(progress_path, progress)
                print(f"   Removed {len(recent_no_version_ids)} entries from failed_set.")
                recent_no_version_ids = []

                try:
                    scraper.close_browser()
                except Exception:
                    pass
                if rotator.next() is None:
                    print(f"\nAll {len(rotator.accounts)} accounts exhausted.")
                    break
                scraper = login_next_account()
                if not scraper:
                    print(f"\nAll remaining accounts failed to authenticate.")
                    break
                continue  # retry same table on the new account

            i += 1

            if config.REQUEST_DELAY > 0:
                time.sleep(config.REQUEST_DELAY)
    finally:
        scraper.close_browser()

    total_remaining = len(remaining) - scraped_this_run - len(failed_set.intersection(remaining))
    print(f"\nSummary:")
    print(f"  Scraped this run: {scraped_this_run}")
    print(f"  Total scraped: {len(scraped_set) + len(already_on_disk)}")
    print(f"  Failed (deleted): {len(failed_set)}")
    print(f"  Remaining: {total_remaining}")
    print(f"  Accounts used: {rotator.current_index + 1}/{len(rotator.accounts)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
