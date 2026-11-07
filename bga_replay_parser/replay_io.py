"""Read and write raw replay HTML files, plain or zstd-compressed.

Replay pages are ~5 MB of HTML each and compress ~30x, so the scraper stores
them as `replay_<table_id>.html.zst`. Readers accept both that and the older
plain `replay_<table_id>.html`.
"""

import glob
import os

import zstandard

ZST_SUFFIX = ".html.zst"
HTML_SUFFIX = ".html"
ZSTD_LEVEL = 9


def table_id_from_path(path):
    """`.../replay_123.html[.zst]` -> `"123"`."""
    name = os.path.basename(path)
    for suffix in (ZST_SUFFIX, HTML_SUFFIX):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name.replace("replay_", "")


def find_replay(replay_dir, table_id):
    """Path of the stored replay for `table_id` (compressed preferred), or None."""
    for suffix in (ZST_SUFFIX, HTML_SUFFIX):
        path = os.path.join(replay_dir, f"replay_{table_id}{suffix}")
        if os.path.exists(path):
            return path
    return None


def list_replays(replay_dir):
    """All replay files in `replay_dir`, one per table (compressed preferred)."""
    by_table = {}
    for suffix in (HTML_SUFFIX, ZST_SUFFIX):  # .zst last so it wins
        for path in glob.glob(os.path.join(replay_dir, f"*{suffix}")):
            by_table[table_id_from_path(path)] = path
    return sorted(by_table.values())


def read_replay_html(path):
    """Return the replay page as text."""
    if path.endswith(".zst"):
        with open(path, "rb") as f:
            raw = zstandard.ZstdDecompressor().decompress(f.read())
        return raw.decode("utf-8", errors="replace")
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def write_replay_html(replay_dir, table_id, html):
    """Save a replay page compressed; returns the path written."""
    path = os.path.join(replay_dir, f"replay_{table_id}{ZST_SUFFIX}")
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(zstandard.ZstdCompressor(level=ZSTD_LEVEL).compress(html.encode("utf-8")))
    os.replace(tmp, path)
    return path
