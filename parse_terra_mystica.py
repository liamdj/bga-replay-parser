"""
Batch parse Terra Mystica replays to CSV. Thin CLI wrapper around
`bga_replay_parser.tm_csv.batch_parse`.

Usage:
    python parse_terra_mystica.py <replay_dir> [output_dir] [--metadata <table_ids.json>]

`output_dir` defaults to `<replay_dir>/parsed/`. `--metadata` defaults to
`progress_collect.json` or `table_ids.json` next to the replay dir, if present.
"""

import argparse
import logging
import os

from bga_replay_parser.tm_csv import batch_parse


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("replay_dir", help="directory of replay_<table_id>.html files")
    p.add_argument("output_dir", nargs="?", default=None,
                   help="output directory (default: <replay_dir>/parsed/)")
    p.add_argument("--metadata", default=None,
                   help="path to progress_collect.json or table_ids.json")
    p.add_argument("--workers", type=int, default=None,
                   help="parallel worker processes (default: os.cpu_count(); "
                        "use 1 for sequential/debug)")
    p.add_argument("--exclude-friendly", action="store_true",
                   help="skip Friendly-mode (unranked) games — keep only Normal/Arena")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    output_dir = args.output_dir or os.path.join(args.replay_dir, "parsed")
    exclude_modes = {"Friendly mode"} if args.exclude_friendly else None
    batch_parse(args.replay_dir, output_dir, metadata_path=args.metadata,
                workers=args.workers, exclude_modes=exclude_modes)


if __name__ == "__main__":
    main()
