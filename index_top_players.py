#!/usr/bin/env python3
"""
Collect table IDs and full metadata for any BGA game by fetching top leaderboard
players' game histories, then enriching each table with settings and ELO data
from the tableinfos API.

Usage:
    python index_top_players.py <game_id-or-name> [-n 100] [--since 2025-01-01] [--until 2025-12-31]

Game can be a numeric BGA game ID (e.g. 1003) or a short name from
constants.GAME_IDS (e.g. tokaido, terra_mystica).
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
from bga_replay_parser.bga_session import BGASession
from bga_replay_parser.leaderboard_scraper import LeaderboardScraper
from bga_replay_parser.scraper import BGAScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

GAMES_URL = "/gamestats/gamestats/getGames.html"
TABLEINFOS_URL = "/table/table/tableinfos.html"

# Proactively recycle the Chrome session to dodge memory leaks during long
# runs. Tune per unit: each player triggers many XHRs (paginated getGames),
# each table triggers one XHR (tableinfos).
BROWSER_RECYCLE_EVERY_PLAYERS = 50
BROWSER_RECYCLE_EVERY_TABLES = 500


def load_progress(progress_path):
    """Load progress file for crash-safe resume."""
    if os.path.exists(progress_path):
        with open(progress_path, "r") as f:
            progress = json.load(f)
    else:
        progress = {"processed_players": [], "tables": {}, "enriched_tables": []}
    progress.setdefault("supplementary_players", [])
    return progress


def save_progress(progress_path, progress):
    """Save progress file atomically via temp file + rename."""
    os.makedirs(os.path.dirname(progress_path), exist_ok=True)
    tmp_path = progress_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(progress, f, indent=2)
    os.replace(tmp_path, progress_path)


def fetch_players(session, game_id, num_players, mode="arena"):
    """Fetch top players from BGA leaderboard for a given game."""
    scraper = LeaderboardScraper(session)
    raw_players = scraper.get_players_by_rank(game_id, num_players, mode=mode)

    players = []
    for player_id, player_name, country, arena_rank in raw_players:
        players.append({
            "player_id": str(player_id),
            "name": player_name,
            "country": country,
            "arena_rank": arena_rank,
        })

    return players


def collect_table_ids(driver, player_id, game_id, since_date=None, until_date=None):
    """
    Collect table IDs for a player via the getGames API.
    Returns a dict of table_id -> num_players.
    """
    params = {
        "page": 1,
        "player": int(player_id),
        "game_id": game_id,
        "finished": 1,
        "updateStats": 0,
    }
    if since_date:
        params["start_date"] = int(since_date.timestamp())
    if until_date:
        params["end_date"] = int(until_date.timestamp())

    tables = {}
    retries = 0

    while True:
        time.sleep(1)  # safe endpoint (/gamestats)

        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{GAMES_URL}?{qs}"

        resp_text = driver.execute_script(f"""
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '{url}', false);
            xhr.setRequestHeader('X-Request-Token', bgaConfig.requestToken);
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send();
            return xhr.responseText;
        """)

        try:
            data = json.loads(resp_text)
            raw_tables = data["data"]["tables"]
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning(f"Invalid response for player {player_id} page {params['page']}: {resp_text[:200]}")
            retries += 1
            if retries > 2:
                break
            continue

        if not raw_tables:
            break

        for t in raw_tables:
            tables[t["table_id"]] = len(t.get("players", "").split(","))

        params["page"] += 1
        retries = 0

    return tables


def resolve_option_value(opt):
    """Resolve an option's numeric value to its display name."""
    val = opt.get("value")
    if val is None or val == "":
        return None
    values = opt.get("values", {})
    try:
        if isinstance(values, list):
            idx = int(val)
            if idx < len(values):
                return values[idx].get("name")
        elif isinstance(values, dict):
            entry = values.get(str(val))
            if isinstance(entry, dict):
                return entry.get("name")
    except (ValueError, TypeError):
        pass
    return None


def fetch_tableinfo(driver, table_id):
    """
    Fetch full table metadata from the tableinfos API.
    Returns a formatted dict with all game settings and player ELOs.
    """
    url = f"{TABLEINFOS_URL}?id={table_id}"

    resp_text = driver.execute_script(f"""
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '{url}', false);
        xhr.setRequestHeader('X-Request-Token', bgaConfig.requestToken);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.send();
        return xhr.responseText;
    """)

    try:
        data = json.loads(resp_text)
        if data.get("status") != 1:
            return None
        d = data["data"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None

    result = d.get("result", {})

    # Extract players with ELO from result
    players = []
    for p in result.get("player", []):
        elo_after = None
        elo_win = None
        elo_start = None
        try:
            elo_after = float(p["rank_after_game"])
            elo_win = float(p["point_win"])
            elo_start = round(elo_after - elo_win) - 1300  # BGA displays ELO - 1300
        except (KeyError, ValueError, TypeError):
            pass

        arena_after = None
        arena_win = None
        try:
            arena_after = float(p["arena_after_game"])
            arena_win = float(p["arena_points_win"])
        except (KeyError, ValueError, TypeError):
            pass

        players.append({
            "id": p.get("player_id"),
            "name": p.get("name"),
            "score": int(p["score"]) if p.get("score") else None,
            "rank": int(p["gamerank"]) if p.get("gamerank") else None,
            "elo_before": elo_start,
            "elo_after": round(elo_after) - 1300 if elo_after else None,
            "elo_change": round(elo_win, 1) if elo_win is not None else None,
            "arena_before": round(arena_after - arena_win, 4) if arena_after is not None and arena_win is not None else None,
            "arena_after": round(arena_after, 4) if arena_after is not None else None,
            "country": p.get("country", {}).get("name"),
        })

    # Extract game options
    options = {}
    for oid, opt in d.get("options", {}).items():
        name = opt.get("name", "")
        resolved = resolve_option_value(opt)
        if name:
            options[name] = resolved

    start_ts = int(d["gamestart"]) if d.get("gamestart") else None
    duration = int(result["time_duration"]) if result.get("time_duration") else None

    return {
        "table_id": table_id,
        "game_name": d.get("game_name", ""),
        "start": start_ts,
        "duration_s": duration,
        "num_players": len(players),
        "concede": result.get("concede") == "1",
        "normalend": result.get("endgame_reason") == "normal_end",
        "table_level": result.get("table_level"),
        "players": players,
        "options": options,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Collect table IDs and metadata from top BGA players for any game."
    )
    parser.add_argument(
        "game", type=str,
        help="BGA game ID (e.g. 1003) or short name from constants.GAME_IDS "
             "(e.g. tokaido, terra_mystica)."
    )
    parser.add_argument(
        "-n", type=int, default=100, help="Number of top players to fetch (default: 100)"
    )
    parser.add_argument(
        "-o", "--output", type=str, default=None,
        help="Output JSON path (default: data/batch/<game_id>/table_ids.json)",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Only include games on or after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until", type=str, default=None,
        help="Only include games on or before this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--supplementary-elo-threshold", type=int, default=None,
        help="After enrichment, also collect games for non-leaderboard players whose "
             "elo_before in any enriched game exceeded this threshold. "
             "Omit to disable the second pass.",
    )
    parser.add_argument(
        "--leaderboard", choices=["arena", "elo"], default="elo",
        help="Which leaderboard to pull top-N players from. 'elo' (default) is "
             "the all-time overall ELO leaderboard (denser, works for any game). "
             "'arena' is the current season Arena leaderboard (sparse for smaller "
             "games like Tokaido).",
    )
    args = parser.parse_args()

    since_date = datetime.strptime(args.since, "%Y-%m-%d") if args.since else None
    until_date = (
        datetime.strptime(args.until, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        if args.until
        else None
    )

    # Resolve the game: numeric id, or short name from constants.GAME_IDS.
    game_arg = args.game
    if game_arg.isdigit():
        game_id = int(game_arg)
        # Reverse-lookup the short name for output paths if present.
        slug = next((name for name, gid in constants.GAME_IDS.items() if gid == game_id), str(game_id))
    else:
        if game_arg not in constants.GAME_IDS:
            print(f"Unknown game name '{game_arg}'. Known: {sorted(constants.GAME_IDS)}")
            sys.exit(2)
        game_id = constants.GAME_IDS[game_arg]
        slug = game_arg
    output_path = args.output or f"data/batch/{slug}/table_ids.json"
    progress_path = os.path.join(os.path.dirname(output_path), "progress_collect.json")

    print(f"\nCollecting table IDs for game {game_id}, top {args.n} players")
    if since_date:
        print(f"Since: {args.since}")
    if until_date:
        print(f"Until: {args.until}")
    print(f"Output: {output_path}")

    # Load progress
    progress = load_progress(progress_path)
    processed_set = set(progress["processed_players"])
    supplementary_set = set(progress["supplementary_players"])
    tables_dict = progress["tables"]
    enriched_set = set(progress.get("enriched_tables", []))

    if processed_set:
        print(f"Resuming: {len(processed_set)} players processed, {len(supplementary_set)} supplementary, {len(tables_dict)} tables, {len(enriched_set)} enriched")

    # Login
    print(f"\n[1] Logging in...")
    scraper = BGAScraper(
        chromedriver_path=config.CHROMEDRIVER_PATH,
        chrome_path=config.CHROME_PATH,
        request_delay=config.REQUEST_DELAY,
        headless=True,
        email=config.BGA_EMAIL,
        password=config.BGA_PASSWORD,
    )
    scraper.speed_profile = config.SPEED_PROFILE
    scraper.speed_settings = constants.SPEED_PROFILES[config.SPEED_PROFILE]

    if not scraper.start_browser_and_login():
        print("Authentication failed.")
        sys.exit(1)

    def is_browser_dead():
        try:
            _ = scraper.driver.current_url
            return False
        except Exception:
            return True

    def restart_browser(token_player_id, max_attempts=10):
        """Restart the browser with retry-with-backoff. Returns True if recovered."""
        nonlocal scraper
        for attempt in range(1, max_attempts + 1):
            print(f"  ⚠️  Browser dead — restart attempt {attempt}/{max_attempts}...")
            try:
                scraper.close_browser()
            except Exception:
                pass
            scraper = BGAScraper(
                chromedriver_path=config.CHROMEDRIVER_PATH,
                chrome_path=config.CHROME_PATH,
                request_delay=config.REQUEST_DELAY,
                headless=True,
                email=config.BGA_EMAIL,
                password=config.BGA_PASSWORD,
            )
            scraper.speed_profile = config.SPEED_PROFILE
            scraper.speed_settings = constants.SPEED_PROFILES[config.SPEED_PROFILE]
            try:
                if scraper.start_browser_and_login():
                    scraper.driver.get(
                        f"https://boardgamearena.com/gamestats?player={token_player_id}&game_id={game_id}"
                    )
                    time.sleep(3)
                    print(f"  ✅ Recovered on attempt {attempt}")
                    return True
            except Exception as e:
                print(f"  ❌ Attempt {attempt} threw: {e}")
            backoff = min(60, 5 * attempt)
            print(f"  Waiting {backoff}s before next attempt...")
            time.sleep(backoff)
        print(f"  ❌ Could not recover browser after {max_attempts} attempts.")
        return False

    try:
        players = fetch_players(scraper.session, game_id, args.n, mode=args.leaderboard)
        print(f"  Found {len(players)} leaderboard players ({args.leaderboard})")

        token_player_id = players[0]['player_id']

        # Navigate to gamestats to get request token
        scraper.driver.get(
            f"https://boardgamearena.com/gamestats?player={token_player_id}&game_id={game_id}"
        )
        time.sleep(3)

        def process_players(player_list, pass_name, processed_tracker, progress_key):
            """Collect table IDs from a list of (pid, name) tuples. Updates progress in place."""
            remaining = [(pid, name) for pid, name in player_list if pid not in processed_tracker]
            if not remaining:
                return 0
            new_tables_total = 0
            i = 0
            crash_retry = 0
            since_recycle = 0
            while i < len(remaining):
                if since_recycle >= BROWSER_RECYCLE_EVERY_PLAYERS:
                    print(f"  ♻️  Recycling browser after {since_recycle} players...")
                    if not restart_browser(token_player_id):
                        print("  ❌ Cannot recover during recycle. Stopping.")
                        return new_tables_total
                    since_recycle = 0
                pid, name = remaining[i]
                print(f"  [{i + 1}/{len(remaining)}] {name} (ID: {pid})...", end=" ")
                player_tables = None
                try:
                    player_tables = collect_table_ids(
                        scraper.driver, pid, game_id,
                        since_date=since_date, until_date=until_date,
                    )
                except Exception as e:
                    logger.error(f"Error collecting games for player {pid}: {e}")
                    print(f"error: {e}")

                if is_browser_dead():
                    crash_retry += 1
                    if crash_retry > 2:
                        print(f"  ⚠️  Skipping {pid} after 3 browser crashes")
                        crash_retry = 0
                        processed_tracker.add(pid)
                        progress[progress_key] = list(processed_tracker)
                        save_progress(progress_path, progress)
                        i += 1
                        since_recycle += 1
                        continue
                    if not restart_browser(token_player_id):
                        print("  ❌ Cannot recover. Stopping.")
                        return new_tables_total
                    continue  # retry same player

                crash_retry = 0
                if player_tables is not None:
                    added = 0
                    for tid, num_players in player_tables.items():
                        if tid not in tables_dict:
                            tables_dict[tid] = {"num_players": num_players}
                            added += 1
                    new_tables_total += added
                    print(f"{len(player_tables)} games ({added} new), total: {len(tables_dict)}")

                processed_tracker.add(pid)
                progress[progress_key] = list(processed_tracker)
                progress["tables"] = tables_dict
                save_progress(progress_path, progress)
                i += 1
                since_recycle += 1
            return new_tables_total

        def enrich_4p_tables(pass_name):
            """Enrich all unenriched 4-player tables via tableinfos API."""
            unenriched = [tid for tid in tables_dict
                          if tid not in enriched_set
                          and tables_dict[tid].get("num_players", 4) == 4]
            skipped = sum(1 for tid in tables_dict
                          if tid not in enriched_set
                          and tables_dict[tid].get("num_players", 4) != 4)
            if not unenriched:
                return 0
            print(f"\n{pass_name} Enriching {len(unenriched)} 4-player tables with tableinfos API (skipping {skipped} non-4p)...")
            i = 0
            crash_retry = 0
            xhr_failures_in_a_row = 0
            since_recycle = 0
            while i < len(unenriched):
                if since_recycle >= BROWSER_RECYCLE_EVERY_TABLES:
                    print(f"  ♻️  Recycling browser after {since_recycle} tables...")
                    if not restart_browser(token_player_id):
                        print("  ❌ Cannot recover during recycle. Stopping enrichment.")
                        return i
                    since_recycle = 0
                tid = unenriched[i]
                print(f"  [{i + 1}/{len(unenriched)}] Table {tid}...", end=" ")
                info = None
                xhr_failed = False
                try:
                    time.sleep(6)  # /table endpoint, be cautious
                    info = fetch_tableinfo(scraper.driver, tid)
                except Exception as e:
                    logger.error(f"Error enriching table {tid}: {e}")
                    print(f"error: {e}")
                    xhr_failed = True

                if is_browser_dead():
                    crash_retry += 1
                    if crash_retry > 2:
                        print(f"  ⚠️  Skipping {tid} after 3 browser crashes")
                        crash_retry = 0
                        i += 1
                        since_recycle += 1
                        continue
                    if not restart_browser(token_player_id):
                        print("  ❌ Cannot recover. Stopping enrichment.")
                        return i
                    continue  # retry same table

                crash_retry = 0
                if info:
                    tables_dict[tid] = info
                    print("OK")
                    enriched_set.add(tid)
                    xhr_failures_in_a_row = 0
                elif xhr_failed:
                    # Transient — Selenium/XHR exception (likely BGA downtime).
                    # Do NOT add to enriched_set so this table gets retried on
                    # the next pass. If we see too many in a row, bail out so
                    # we don't burn through the queue marking nothing enriched.
                    print("transient")
                    xhr_failures_in_a_row += 1
                    if xhr_failures_in_a_row >= 50:
                        print(f"  ⚠️  {xhr_failures_in_a_row} XHR failures in a row — bailing out (BGA outage?).")
                        print(f"  Resume later; tables remain un-enriched and will be retried.")
                        return i
                else:
                    # BGA cleanly returned non-success (status != 1) — table is
                    # genuinely unavailable (deleted/private). Mark enriched so
                    # we don't retry forever.
                    print("unavailable")
                    enriched_set.add(tid)
                    xhr_failures_in_a_row = 0

                # Save every 10 tables
                if (i + 1) % 10 == 0:
                    progress["tables"] = tables_dict
                    progress["enriched_tables"] = list(enriched_set)
                    save_progress(progress_path, progress)

                i += 1
                since_recycle += 1

            progress["tables"] = tables_dict
            progress["enriched_tables"] = list(enriched_set)
            save_progress(progress_path, progress)
            return len(unenriched)

        def find_supplementary_players(elo_threshold, leaderboard_ids, already_processed):
            """Find non-leaderboard players with elo_before > threshold in any enriched game."""
            candidates = {}  # pid -> (name, highest_elo_seen)
            for t in tables_dict.values():
                if not t.get("table_id"):
                    continue
                for p in t.get("players", []):
                    pid = str(p.get("id") or "")
                    if not pid or pid in leaderboard_ids or pid in already_processed:
                        continue
                    elo = p.get("elo_before") or 0
                    if elo > elo_threshold:
                        prev = candidates.get(pid)
                        if prev is None or elo > prev[1]:
                            candidates[pid] = (p.get("name", ""), elo)
            # Sort by highest ELO descending
            return sorted(
                [(pid, name) for pid, (name, _elo) in candidates.items()],
                key=lambda x: -candidates[x[0]][1],
            )

        # Step 2: Collect table IDs from leaderboard players
        leaderboard_ids = {p["player_id"] for p in players}
        leaderboard_list = [(p["player_id"], p["name"]) for p in players]
        to_do = [p for p in leaderboard_list if p[0] not in processed_set]
        if to_do:
            print(f"\n[2] Collecting table IDs from {len(to_do)} leaderboard players...")
            process_players(leaderboard_list, "leaderboard", processed_set, "processed_players")
        else:
            print(f"\n[2] All {len(players)} leaderboard players already processed.")

        # Step 3: Enrich 4-player tables
        enriched_count = enrich_4p_tables("[3]")
        if enriched_count == 0:
            print(f"\n[3] All 4-player tables already enriched.")

        # Step 4: Second pass — find supplementary high-ELO players not on the leaderboard
        if args.supplementary_elo_threshold is not None:
            # Exclude both leaderboard and already-processed players (arena-leaderboard
            # carryover, etc.) so we don't redundantly re-collect their games.
            already_done = leaderboard_ids | processed_set | supplementary_set
            supplementary = find_supplementary_players(
                args.supplementary_elo_threshold, already_done, supplementary_set
            )
            if supplementary:
                print(f"\n[4] Found {len(supplementary)} non-leaderboard players with ELO > {args.supplementary_elo_threshold} in enriched games. Collecting their games...")
                process_players(supplementary, "supplementary", supplementary_set, "supplementary_players")

                # Step 5: Enrich any newly-added 4p tables
                enriched_count_2 = enrich_4p_tables("[5]")
                if enriched_count_2 == 0:
                    print(f"\n[5] No new tables from supplementary pass to enrich.")
            else:
                print(f"\n[4] No new high-ELO non-leaderboard players found.")

    finally:
        scraper.close_browser()

    # Step 4: Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    enriched_tables = [t for t in tables_dict.values() if t.get("table_id")]
    sorted_tables = sorted(enriched_tables, key=lambda t: t.get("start") or 0)
    output = {
        "game_id": game_id,
        "collected_at": datetime.now().isoformat(),
        "num_players_processed": len(processed_set),
        "total_tables": len(sorted_tables),
        "table_ids": [t["table_id"] for t in sorted_tables],
        "tables": sorted_tables,
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    # Compute remaining unenriched 4p tables to report honest status
    enriched_set_now = set(progress.get("enriched_tables", []))
    remaining_4p = sum(
        1 for tid, t in tables_dict.items()
        if tid not in enriched_set_now and t.get("num_players", 4) == 4
    )
    if remaining_4p == 0:
        print(f"\nDone! {len(sorted_tables)} tables saved to {output_path}")
    else:
        print(f"\nStopped early: {remaining_4p} 4p tables still unenriched.")
        print(f"   {len(sorted_tables)} tables saved to {output_path}")
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
