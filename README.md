# BGA Replay Parser

Tools for scraping and parsing BoardGameArena replays into pandas-ready CSVs. Currently supports two games:

| Game | Raw format | Parser | Batch script |
|---|---|---|---|
| Terra Mystica | HTML | [`bga_replay_parser/tm_parser.py`](bga_replay_parser/tm_parser.py) | [`parse_terra_mystica.py`](parse_terra_mystica.py) |
| Tokaido | JSON | [`bga_replay_parser/tokaido_parser.py`](bga_replay_parser/tokaido_parser.py) | [`parse_tokaido.py`](parse_tokaido.py) |

The BGA login and replay-scraping layer (`bga_session.py`, `scraper.py`, `leaderboard_scraper.py`) is adapted from [HStrand/bga-tm-scraper](https://github.com/HStrand/bga-tm-scraper), a Terraforming Mars scraper — thanks to Håkon Hapnes Strand and contributors. Here it is generalized across games; the Terra Mystica and Tokaido parsers, indexing script, and docs are new. For Terraforming Mars parsing, use the upstream repo.

## Quick start

```bash
pip install -r requirements.txt
cp config.example.py config.py        # then fill in BGA_EMAIL / BGA_PASSWORD
# optional, for --rotate-accounts: cp accounts.example.py accounts.py

# Index top-N Arena players' games for a game
python index_top_players.py tokaido -n 100

# Scrape raw replays (raw format defaults per-game from bga_replay_parser.constants)
python scrape_raw_replay.py --file data/batch/tokaido/table_ids.json

# Batch-parse raw replays into CSVs
python parse_tokaido.py        data/batch/tokaido/raw/
python parse_terra_mystica.py  data/batch/terra_mystica/replays/
```

Parsed datasets are published at [huggingface.co/datasets/liamdj/bga-replays](https://huggingface.co/datasets/liamdj/bga-replays) — quickstart notebooks live there too. `data/` in this repo is gitignored.

## More

- [`docs/`](docs/) — game reference docs (rules, factions, BGA replay format) — [`docs/README.md`](docs/README.md) is the index.
- [`CLAUDE.md`](CLAUDE.md) — the main architecture doc: scraping flow, parser internals and output columns, VP reconciliation quirks, repo layout.

## License

No license has been chosen yet. The upstream project has no license file either; its README describes it as "for educational and research purposes." The same applies here: this is for personal research and analysis. Respect BGA's terms of service, daily replay limits, and rate limits, and be mindful of player privacy when sharing data.
