"""
Batch parse Tokaido replays to CSV. Thin CLI wrapper around
`bga_replay_parser.tokaido_csv.batch_parse`.

Usage:
    python parse_tokaido.py <replay_dir> [output_dir]

`output_dir` defaults to `<replay_dir>/../parsed/`.
"""

import argparse
import logging
import os

from bga_replay_parser.tokaido_csv import batch_parse


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("replay_dir", help="directory of <table_id>.json files")
    p.add_argument("output_dir", nargs="?", default=None,
                   help="output directory (default: <replay_dir>/../parsed/)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    output_dir = os.path.abspath(args.output_dir or os.path.join(args.replay_dir, "..", "parsed"))
    batch_parse(args.replay_dir, output_dir)


if __name__ == "__main__":
    main()
