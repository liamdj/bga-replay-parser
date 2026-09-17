"""
Terra Mystica CSV export.

Flattens TMGameData into five CSV-friendly views and runs the batch loop over a
directory of replay HTML files. The root script `parse_terra_mystica.py` is a
thin wrapper around `batch_parse`.

Outputs (in `output_dir`):
    player_results.csv  — one row per player per game
    moves.csv           — one row per action
    round_summaries.csv — one row per player per round
    auction_bids.csv    — one row per player per faction bid (auction games; a player's
                          last bid on each faction)
    setup.csv           — one row per game
"""

import csv
import glob
import json
import logging
import multiprocessing as mp
import os
from dataclasses import fields

from .tm_parser import TerraMysticaParser

logger = logging.getLogger(__name__)


def flatten_player(g, pr):
    row = {"table_id": g.table_id, "num_players": g.num_players,
           "board": g.board, "is_winner": pr.player_id == g.winner_player_id}
    for f in fields(pr):
        val = getattr(pr, f.name)
        if f.name in ("favor_tiles", "town_tiles", "bonus_cards"):
            row[f.name] = ";".join(val) if val else ""
        elif f.name == "elo_data":
            elo = val or {}
            if hasattr(elo, "__dict__"):
                elo = elo.__dict__
            row["elo_before"]   = elo.get("elo_before")
            row["elo_after"]    = elo.get("elo_after")
            row["arena_before"] = elo.get("arena_before")
            row["arena_after"]  = elo.get("arena_after")
        else:
            row[f.name] = val
    return row


def flatten_move(table_id, m):
    row = {"table_id": table_id}
    for f in fields(m):
        if f.name != "state_after":
            row[f.name] = getattr(m, f.name)
    return row


def flatten_round(table_id, rs):
    row = {"table_id": table_id}
    for f in fields(rs):
        val = getattr(rs, f.name)
        if f.name == "power_actions":
            row[f.name] = ";".join(val) if val else ""
        else:
            row[f.name] = val
    return row


def flatten_bid(table_id, b):
    row = {"table_id": table_id}
    for f in fields(b):
        row[f.name] = getattr(b, f.name)
    return row


def flatten_setup(g):
    players = sorted(g.players.values(), key=lambda p: p.seat_order)

    def _elo(p, key):
        if p.elo_data is None:
            return ""
        val = getattr(p.elo_data, key, None)
        return "" if val is None else val

    return {
        "table_id":            g.table_id,
        "num_players":         g.num_players,
        "game_mode":           g.game_mode,
        "board":               g.board,
        "total_rounds":        g.total_rounds,
        "with_auction":        g.with_auction,
        "landscape_active":    g.landscape_active,
        "custom_map":          g.custom_map,
        "variable_turn_order": g.variable_turn_order,
        "fire_ice_scoring":    g.fire_ice_scoring,
        "auction_type":        g.auction_type,
        "starting_vp_setting": g.starting_vp_setting,
        "game_version":        g.game_version,
        "scoring_tiles":       ";".join(g.scoring_tiles),
        "bonus_cards":         ";".join(g.bonus_cards),
        "winner_player_id":    g.winner_player_id,
        "winner_player_name":  g.winner_player_name,
        "player_ids":          ";".join(p.player_id for p in players),
        "player_names":        ";".join(p.player_name for p in players),
        "factions":            ";".join(p.faction for p in players),
        "terrains":            ";".join(p.terrain for p in players),
        "elo_before":          ";".join(str(_elo(p, "elo_before")) for p in players),
        "elo_after":           ";".join(str(_elo(p, "elo_after"))  for p in players),
        "starting_vp":         ";".join(str(p.starting_vp) for p in players),
        "final_vp":            ";".join(str(p.final_vp)    for p in players),
    }


def load_table_metadata(metadata_path, table_ids=None):
    """Load progress_collect.json or table_ids.json into {table_id: {players: {pid: {...}}}}.

    `table_ids`: optional set of table IDs to keep. If provided, tables outside
    the set are skipped (avoids building a 100K-entry dict for a small batch).
    """
    if not metadata_path or not os.path.isfile(metadata_path) or os.path.getsize(metadata_path) == 0:
        return {}
    with open(metadata_path) as f:
        data = json.load(f)
    lookup = {}
    tables = data.get("tables", data)
    del data  # free the full JSON

    def _add_table(tid, t):
        tid = str(tid)
        if table_ids is not None and tid not in table_ids:
            return
        players = {}
        for p in t.get("players", []):
            pid = str(p.get("id", ""))
            players[pid] = {
                "name":         p.get("name", pid),
                "elo_before":   p.get("elo_before"),
                "elo_after":    p.get("elo_after"),
                "arena_before": p.get("arena_before"),
                "arena_after":  p.get("arena_after"),
            }
        opts = t.get("options", {}) or {}
        lookup[tid] = {
            "players": players,
            "game_mode": opts.get("Game mode", ""),
            "starting_vp_setting": opts.get("Starting VP", ""),
        }

    if isinstance(tables, dict):
        for tid, t in tables.items():
            _add_table(tid, t)
    elif isinstance(tables, list):
        for t in tables:
            _add_table(t.get("table_id", ""), t)
    return lookup


def _auto_detect_metadata(replay_dir):
    """Look for progress_collect.json or table_ids.json next to replay_dir."""
    parent = os.path.dirname(replay_dir.rstrip("/"))
    for fname in ("progress_collect.json", "table_ids.json"):
        auto = os.path.join(parent, fname)
        if os.path.exists(auto):
            return auto
    return None


# --- parallel worker plumbing --------------------------------------------
# Each worker process holds one parser + a copy of the (trimmed) metadata,
# set once via the Pool initializer. Workers do the heavy parse+flatten and
# return picklable row dicts; the main process owns the CSV writers.

_WORKER_PARSER = None
_WORKER_METADATA = None
_WORKER_EXCLUDE_MODES = frozenset()


def _worker_init(metadata, exclude_modes):
    global _WORKER_PARSER, _WORKER_METADATA, _WORKER_EXCLUDE_MODES
    _WORKER_PARSER = TerraMysticaParser()
    _WORKER_METADATA = metadata or {}
    _WORKER_EXCLUDE_MODES = frozenset(exclude_modes or ())


def _worker_parse(path):
    """Parse one replay in a worker. Returns a status dict of flattened rows."""
    fname = os.path.basename(path)
    table_id = fname.replace("replay_", "").replace(".html", "")
    meta = _WORKER_METADATA.get(table_id)

    # Game-mode filter (metadata-based) — skip before reading the HTML.
    if _WORKER_EXCLUDE_MODES and meta and meta.get("game_mode") in _WORKER_EXCLUDE_MODES:
        return {"status": "skipped"}

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            html = f.read()
    except OSError as e:
        return {"status": "error", "fname": fname, "err": f"read: {e}"}

    if _WORKER_PARSER.should_skip_replay(html):
        return {"status": "skipped"}

    try:
        game = _WORKER_PARSER.parse_complete_game(
            html, game_metadata=meta, table_id=table_id)
    except Exception as e:
        return {"status": "error", "fname": fname, "err": f"{type(e).__name__}: {e}"}
    if game.num_players == 0:
        return {"status": "empty"}

    return {
        "status": "parsed",
        "player": [flatten_player(game, pr) for pr in game.players.values()],
        "move":   [flatten_move(game.table_id, mv) for mv in game.moves],
        "round":  [flatten_round(game.table_id, rs) for rs in game.round_summaries],
        "bid":    [flatten_bid(game.table_id, b) for b in game.auction_bids],
        "setup":  flatten_setup(game),
    }


def batch_parse(replay_dir, output_dir, metadata_path=None, workers=None,
                exclude_modes=None):
    """Parse every `replay_*.html` in `replay_dir` and stream rows to CSVs in `output_dir`.

    If `metadata_path` is None, looks for progress_collect.json / table_ids.json
    in the parent of `replay_dir`. Skipped replays (excluded factions, landscapes)
    don't produce rows.

    `exclude_modes`: set of "Game mode" strings to skip (e.g. {"Friendly mode"}).
    Requires metadata with per-table game_mode; games without metadata are kept.

    Parsing is parallelized across `workers` processes (default: os.cpu_count()).
    Pass `workers=1` for the sequential path (easier to debug). Row order in the
    output is not deterministic across workers, but every row carries its
    table_id so downstream joins are unaffected.
    """
    if metadata_path is None:
        metadata_path = _auto_detect_metadata(replay_dir)
    if workers is None:
        workers = max(1, (os.cpu_count() or 2))
    exclude_modes = frozenset(exclude_modes or ())

    paths = sorted(glob.glob(os.path.join(replay_dir, "*.html")))
    logger.info(f"Found {len(paths)} replay files in {replay_dir}")

    replay_table_ids = {
        os.path.basename(p).replace("replay_", "").replace(".html", "")
        for p in paths
    }
    table_metadata = load_table_metadata(metadata_path, table_ids=replay_table_ids)
    if table_metadata:
        logger.info(f"Loaded metadata for {len(table_metadata)} tables from {metadata_path}")
    os.makedirs(output_dir, exist_ok=True)

    # Write to temp files first, then atomically swap into place only on a
    # clean finish. A mid-parse crash leaves the previous CSVs untouched
    # instead of clobbering them with a truncated/partial rewrite.
    final_paths = {
        "player": os.path.join(output_dir, "player_results.csv"),
        "move":   os.path.join(output_dir, "moves.csv"),
        "round":  os.path.join(output_dir, "round_summaries.csv"),
        "bid":    os.path.join(output_dir, "auction_bids.csv"),
        "setup":  os.path.join(output_dir, "setup.csv"),
    }
    tmp_paths = {k: p + ".tmp" for k, p in final_paths.items()}
    files = {k: open(tmp_paths[k], "w", newline="", encoding="utf-8") for k in final_paths}

    writers = {k: None for k in final_paths}
    counts = {k: 0 for k in final_paths}
    parsed = skipped = errors = 0

    def _write(kind, row):
        if writers[kind] is None:
            writers[kind] = csv.DictWriter(files[kind], fieldnames=list(row.keys()))
            writers[kind].writeheader()
        writers[kind].writerow(row)
        counts[kind] += 1

    def handle(res):
        nonlocal parsed, skipped, errors
        st = res["status"]
        if st == "skipped" or st == "empty":
            if st == "skipped":
                skipped += 1
            return
        if st == "error":
            errors += 1
            logger.warning(f"{res.get('fname','?')}: {res.get('err','')}")
            return
        for row in res["player"]:
            _write("player", row)
        for row in res["move"]:
            _write("move", row)
        for row in res["round"]:
            _write("round", row)
        for row in res["bid"]:
            _write("bid", row)
        _write("setup", res["setup"])
        parsed += 1

    success = False
    try:
        if workers == 1:
            _worker_init(table_metadata, exclude_modes)
            for path in paths:
                handle(_worker_parse(path))
        else:
            logger.info(f"Parsing with {workers} worker processes")
            with mp.Pool(processes=workers,
                         initializer=_worker_init,
                         initargs=(table_metadata, exclude_modes)) as pool:
                for res in pool.imap_unordered(_worker_parse, paths, chunksize=8):
                    handle(res)
        success = True
    finally:
        for f in files.values():
            f.close()
        if success:
            # Empty writers (no rows of that kind) still produced a valid empty
            # temp file; swap them all so output is consistent.
            for k in final_paths:
                os.replace(tmp_paths[k], final_paths[k])
        else:
            # Failed or interrupted — discard temps, keep the previous CSVs.
            for k in final_paths:
                try:
                    os.remove(tmp_paths[k])
                except OSError:
                    pass
            logger.error("Parse did not complete — kept previous CSVs, discarded temp files.")

    logger.info(f"Parsed: {parsed}, Skipped: {skipped}, Errors: {errors}")
    logger.info(f"Wrote {counts['setup']} setup rows, {counts['player']} player rows, "
                f"{counts['move']} move rows, {counts['round']} round rows, "
                f"{counts['bid']} auction-bid rows to {output_dir}")
