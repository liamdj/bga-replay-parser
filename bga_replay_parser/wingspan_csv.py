"""
Wingspan CSV export.

Flattens WingspanGameData into five CSV-friendly views and runs the batch loop
over a directory of replay JSON files. The root script `parse_wingspan.py` is a
thin wrapper around `batch_parse`.

Outputs (in `output_dir`):
    player_results.csv — one row per player per game
    moves.csv          — one row per action / power effect
    birds.csv          — one row per bird played
    round_goals.csv    — one row per player per round
    setup.csv          — one row per game
"""

import csv
import glob
import json
import logging
import multiprocessing as mp
import os
from dataclasses import fields

from .wingspan_parser import WingspanParser

logger = logging.getLogger(__name__)

KINDS = ("player", "move", "bird", "goal", "setup")
ELO_KEYS = ("elo_before", "elo_after", "arena_before", "arena_after")

# setup.csv column -> tableinfos option name (values kept as BGA's labels).
OPTION_COLUMNS = {
    "game_mode":            "Game mode",
    "game_speed":           "Game speed",
    "goal_board":           "Goal board",
    "powerful_birds":       "Powerful bird cards",
    "swift_start_birds":    "Swift Start Birds",
    "language_bonus_cards": "Language-dependent bonus cards",
}


def _flat(table_id, obj):
    row = {"table_id": table_id}
    for f in fields(obj):
        val = getattr(obj, f.name)
        row[f.name] = ";".join(val) if isinstance(val, list) else val
    return row


def flatten_player(g, pr, meta):
    row = {"table_id": g.table_id, "num_players": g.num_players}
    row.update(_flat(g.table_id, pr))
    elo = (meta or {}).get("players", {}).get(pr.player_id, {})
    for k in ELO_KEYS:
        row[k] = elo.get(k)
    return row


def flatten_setup(g, meta):
    players = sorted(g.players.values(), key=lambda p: p.seat_order)
    row = {
        "table_id":           g.table_id,
        "num_players":        g.num_players,
        "start_time":         g.start_time,
        "end_time":           g.end_time,
    }
    for col in OPTION_COLUMNS:
        row[col] = (meta or {}).get(col, "")
    for i in range(4):
        row[f"goal_{i + 1}"] = g.goals[i] if i < len(g.goals) else ""
    row.update({
        "first_player_id":    g.first_player_id,
        "winner_player_id":   g.winner_player_id,
        "winner_player_name": g.winner_player_name,
        "player_ids":         ";".join(p.player_id for p in players),
        "player_names":       ";".join(p.player_name for p in players),
        "final_scores":       ";".join(str(p.final_score) for p in players),
    })
    return row


def load_table_metadata(metadata_path, table_ids=None):
    """Load progress_collect.json or table_ids.json into {table_id: {players, <option columns>}}.

    `table_ids`: optional set of table IDs to keep.
    """
    if not metadata_path or not os.path.isfile(metadata_path) or os.path.getsize(metadata_path) == 0:
        return {}
    with open(metadata_path) as f:
        data = json.load(f)
    tables = data.get("tables", data)
    del data
    items = tables.items() if isinstance(tables, dict) else ((t.get("table_id", ""), t) for t in tables)
    lookup = {}
    for tid, t in items:
        tid = str(tid)
        if (table_ids is not None and tid not in table_ids) or not t.get("players"):
            continue
        opts = t.get("options") or {}
        lookup[tid] = {
            "players": {str(p.get("id", "")): {k: p.get(k) for k in ELO_KEYS} for p in t["players"]},
            **{col: opts.get(name) or "" for col, name in OPTION_COLUMNS.items()},
        }
    return lookup


def _auto_detect_metadata(replay_dir):
    """Look for progress_collect.json or table_ids.json next to replay_dir."""
    parent = os.path.dirname(os.path.abspath(replay_dir))
    for fname in ("progress_collect.json", "table_ids.json"):
        auto = os.path.join(parent, fname)
        if os.path.exists(auto):
            return auto
    return None


# --- parallel worker plumbing --------------------------------------------
# Each worker holds one parser + a copy of the (trimmed) metadata, set once
# via the Pool initializer, and returns plain row dicts for the parent to write.
_WORKER_PARSER = None
_WORKER_METADATA = {}


def _worker_init(metadata):
    global _WORKER_PARSER, _WORKER_METADATA
    _WORKER_PARSER = WingspanParser()
    _WORKER_METADATA = metadata or {}


def _worker_parse(path):
    fname = os.path.basename(path)
    table_id = WingspanParser._table_id_from_path(path)
    try:
        game = _WORKER_PARSER.parse_json_file(path, table_id=table_id)
    except Exception as e:
        return {"status": "error", "fname": fname, "err": f"{type(e).__name__}: {e}"}
    if game is None:
        return {"status": "skipped"}
    meta = _WORKER_METADATA.get(table_id)
    return {
        "status": "ok",
        "fname": fname,
        "warnings": game.warnings,
        "player": [flatten_player(game, pr, meta) for pr in game.players.values()],
        "move": [_flat(table_id, m) for m in game.moves],
        "bird": [_flat(table_id, b) for b in game.birds],
        "goal": [_flat(table_id, rg) for rg in game.round_goals],
        "setup": [flatten_setup(game, meta)],
    }


def batch_parse(replay_dir, output_dir, metadata_path=None, workers=None):
    """Parse every `<table_id>.json` in `replay_dir` and stream rows to CSVs in `output_dir`.

    If `metadata_path` is None, looks for progress_collect.json / table_ids.json
    in the parent of `replay_dir`; without metadata the ELO columns and the
    game-option columns of setup.csv are blank. Skipped replays (conceded, no result block) don't
    produce rows. Games that fail a reconciliation check are still written and
    logged as warnings.

    Parsing is parallelized across `workers` processes (default: os.cpu_count());
    pass `workers=1` for the sequential path. Row order is not deterministic
    across workers, but every row carries its table_id.
    """
    if metadata_path is None:
        metadata_path = _auto_detect_metadata(replay_dir)
    if workers is None:
        workers = max(1, (os.cpu_count() or 2))

    paths = sorted(p for p in glob.glob(os.path.join(replay_dir, "*.json"))
                   if not os.path.basename(p).startswith("invalid."))
    logger.info(f"Found {len(paths)} replay files in {replay_dir}")

    table_metadata = load_table_metadata(
        metadata_path, table_ids={WingspanParser._table_id_from_path(p) for p in paths})
    if table_metadata:
        logger.info(f"Loaded metadata for {len(table_metadata)} tables from {metadata_path}")
    os.makedirs(output_dir, exist_ok=True)

    # Write to temp files, then atomically swap into place only on a clean
    # finish — a mid-parse crash keeps the previous CSVs intact.
    names = {"player": "player_results", "move": "moves", "bird": "birds",
             "goal": "round_goals", "setup": "setup"}
    final_paths = {k: os.path.join(output_dir, f"{names[k]}.csv") for k in KINDS}
    tmp_paths = {k: p + ".tmp" for k, p in final_paths.items()}
    files = {k: open(tmp_paths[k], "w", newline="", encoding="utf-8") for k in KINDS}
    writers = {k: None for k in KINDS}
    counts = {k: 0 for k in KINDS}
    parsed = skipped = errors = warned = 0

    def handle(res):
        nonlocal parsed, skipped, errors, warned
        if res["status"] == "skipped":
            skipped += 1
            return
        if res["status"] == "error":
            errors += 1
            logger.warning(f"{res['fname']}: {res['err']}")
            return
        if res["warnings"]:
            warned += 1
            logger.warning(f"{res['fname']}: {'; '.join(res['warnings'])}")
        for kind in KINDS:
            for row in res[kind]:
                if writers[kind] is None:
                    writers[kind] = csv.DictWriter(files[kind], fieldnames=list(row.keys()))
                    writers[kind].writeheader()
                writers[kind].writerow(row)
                counts[kind] += 1
        parsed += 1

    success = False
    try:
        if workers == 1:
            _worker_init(table_metadata)
            for path in paths:
                handle(_worker_parse(path))
        else:
            logger.info(f"Parsing with {workers} worker processes")
            with mp.Pool(processes=workers, initializer=_worker_init,
                         initargs=(table_metadata,)) as pool:
                for res in pool.imap_unordered(_worker_parse, paths, chunksize=8):
                    handle(res)
        success = True
    finally:
        for f in files.values():
            f.close()
        if success:
            for k in KINDS:
                os.replace(tmp_paths[k], final_paths[k])
        else:
            for k in KINDS:
                try:
                    os.remove(tmp_paths[k])
                except OSError:
                    pass
            logger.error("Parse did not complete — kept previous CSVs, discarded temp files.")

    logger.info(f"Parsed: {parsed}, Skipped: {skipped}, Errors: {errors}, "
                f"Failed a reconciliation check: {warned}")
    logger.info(f"Wrote {counts['setup']} setup rows, {counts['player']} player rows, "
                f"{counts['move']} move rows, {counts['bird']} bird rows, "
                f"{counts['goal']} round-goal rows to {output_dir}")
