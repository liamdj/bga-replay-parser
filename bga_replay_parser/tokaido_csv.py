"""
Tokaido CSV export.

Flattens TokaidoGameData into two CSV-friendly views and runs the batch loop
over a directory of replay JSON files. Base game and Crossroads expansion are
routed to separate output files since they differ enough that mixing them adds
noise. The root script `parse_tokaido.py` is a thin wrapper around `batch_parse`.

Outputs (in `output_dir`):
    player_results_base.csv    — one row per player per base game
    player_results_xroads.csv  — one row per player per Crossroads game
    moves_base.csv             — one row per action in base games
    moves_xroads.csv           — one row per action in Crossroads games

The base player_results file omits Crossroads-only columns
(vp_calligraphy, vp_legendary_*, vp_bath_house, vp_cherry_tree, vp_legend_bonus,
num_amulets_*, num_calligraphies, num_legendary_*, has_calligraphy_*) — see
`bga_replay_parser.tokaido_models.XROADS_ONLY_PLAYER_FIELDS` for the full list.
"""

import csv
import glob
import json
import logging
import os
from dataclasses import fields

from .tokaido_parser import TokaidoParser
from .tokaido_models import XROADS_ONLY_PLAYER_FIELDS

logger = logging.getLogger(__name__)


def flatten_player(g, pr, drop_xroads=False):
    row = {"table_id": g.table_id, "num_players": g.num_players,
           "preparations": g.preparations}
    for f in fields(pr):
        if drop_xroads and f.name in XROADS_ONLY_PLAYER_FIELDS:
            continue
        row[f.name] = getattr(pr, f.name)
    return row


def flatten_move(g, m):
    row = {"table_id": g.table_id}
    for f in fields(m):
        row[f.name] = getattr(m, f.name)
    return row


def batch_parse(replay_dir, output_dir):
    """Parse every `<table_id>.json` in `replay_dir` and stream rows to CSVs in `output_dir`.

    Skips files prefixed with `invalid.`. Games where the parser returns None
    (skip reasons like 2-player Tokaido or unsupported expansions) don't produce rows.
    """
    os.makedirs(output_dir, exist_ok=True)
    parser = TokaidoParser()
    paths = sorted(p for p in glob.glob(os.path.join(replay_dir, "*.json"))
                   if not os.path.basename(p).startswith("invalid."))
    logger.info(f"Found {len(paths)} replay files in {replay_dir}")

    # Write to temp files, then atomically swap into place only on a clean
    # finish — a mid-parse crash keeps the previous CSVs intact instead of
    # clobbering them with a truncated rewrite.
    final_paths = {
        "p_base":   os.path.join(output_dir, "player_results_base.csv"),
        "p_xroads": os.path.join(output_dir, "player_results_xroads.csv"),
        "m_base":   os.path.join(output_dir, "moves_base.csv"),
        "m_xroads": os.path.join(output_dir, "moves_xroads.csv"),
    }
    tmp_paths = {k: p + ".tmp" for k, p in final_paths.items()}
    files = {k: open(tmp_paths[k], "w", newline="", encoding="utf-8") for k in final_paths}
    writers = {k: None for k in files}
    counts = {"games_base": 0, "games_xroads": 0,
              "p_base": 0, "p_xroads": 0, "m_base": 0, "m_xroads": 0}

    def write(key, row):
        if writers[key] is None:
            writers[key] = csv.DictWriter(files[key], fieldnames=list(row.keys()))
            writers[key].writeheader()
        writers[key].writerow(row)
        counts[key] += 1

    parsed = skipped = errors = 0

    success = False
    try:
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                errors += 1
                logger.warning(f"{os.path.basename(path)}: read error: {e}")
                continue

            packets = TokaidoParser._normalize_to_packet_list(raw)
            if not packets:
                skipped += 1
                continue

            table_id = TokaidoParser._table_id_from_path(path)
            try:
                game = parser.parse_packets(packets, table_id=table_id)
            except Exception as e:
                errors += 1
                logger.warning(f"{os.path.basename(path)}: {type(e).__name__}: {e}")
                continue

            if game is None:
                skipped += 1
                continue

            p_key, m_key = ("p_xroads", "m_xroads") if game.has_crossroads else ("p_base", "m_base")
            counts["games_xroads" if game.has_crossroads else "games_base"] += 1

            for pr in game.players.values():
                write(p_key, flatten_player(game, pr, drop_xroads=not game.has_crossroads))
            for m in game.moves:
                write(m_key, flatten_move(game, m))

            parsed += 1
            del game
        success = True
    finally:
        for f in files.values():
            f.close()
        if success:
            for k in final_paths:
                os.replace(tmp_paths[k], final_paths[k])
        else:
            for k in final_paths:
                try:
                    os.remove(tmp_paths[k])
                except OSError:
                    pass
            logger.error("Parse did not complete — kept previous CSVs, discarded temp files.")

    logger.info(f"Parsed: {parsed}, Skipped: {skipped}, Errors: {errors}")
    logger.info(f"  base:    {counts['games_base']:6} games, {counts['p_base']:7} player rows, {counts['m_base']:8} move rows")
    logger.info(f"  xroads:  {counts['games_xroads']:6} games, {counts['p_xroads']:7} player rows, {counts['m_xroads']:8} move rows")
    logger.info(f"Output: {output_dir}")
