# Wingspan parser

How `bga_replay_parser/wingspan_*.py` turns a replay into CSVs: output columns, turn structure, skip rules, reconciliation. Raw event schemas are in [bga_replay_format.md](bga_replay_format.md).

`WingspanParser` in `wingspan_parser.py` reads BGA Wingspan replays (JSON gamelogs, same raw format as Tokaido) into five CSV views. Uses `wingspan_models.py` for dataclasses and `wingspan_constants.py` for id lookups. Dispatch is on `event.type` via `_ev_<type>` methods; the log template only splits `noAction`. Format details: `bga_replay_format.md`.

Corpus: `data/batch/wingspan/raw/` — 76,442 replays, 2022-10 → 2025-01, Arena seasons 11–19, base game + Swift Start only (bird ids 0–179), 3-player until 2023-04 and 2-player after. 71,335 parse; the rest are conceded. `~/Desktop/old-bga-replays/data/wingspan` is a symlink back to `data/batch/wingspan`. Also there: `wingspan_tables.csv` (old index: `table_id, player_id, elo, season, arena_rank`, ELO for the indexed player only), `parsed_v0/` (old per-game CSVs), `raw_invalid/` (zero-byte failed scrapes).

## Format facts the parser relies on

- Every player's private channel (`/player/p<id>`) is in the archive, so draws, tucked cards and bonus choices are known for all players. Private halves arrive before their public halves and are queued per player.
- Undone actions are already stripped from the archive — no rollback. Every player has exactly 26 `setCube` events.
- `drawBirdsPublic` carries card ids only until 2024-09-02; after that they are on `drawBirdsPrivate` alone.
- Maps keyed by ids 0..n-1 arrive as JSON lists (PHP): a hand holding only bonus card 0 (Anatomist) is `bonus_data: [[...]]`. Use `_keyed()`.
- Round-goal ids come from result-block table stats `40`–`43`; the id → name map (`GOAL_NAMES`) was derived from board state, not from the logs.
- Kept starting birds are never listed; they are inferred as cards that leave a hand without having been drawn (`starting_birds_kept_known`, complete for 98% of players).

## Output: 5 CSVs

List-valued columns are `;`-joined. 2-player and 3-player games share the files (`num_players`).

**player_results.csv** — one row per player per game:
- Game/identity: table_id, num_players, player_id, player_name, seat_order
- Result: final_score, score_aux (tiebreaker = unused food), final_rank, is_winner
- VP breakdown (sums to final_score): vp_birds, vp_bonus, vp_goals, vp_eggs, vp_cached, vp_tucked; vp_goal_1..4 split vp_goals by round
- Board: num_birds, birds_forest/grassland/wetland
- Turns by action (sum to 26): turns_play_bird/gain_food/lay_eggs/draw_cards
- Totals (base actions + powers): food_gained, food_spent, eggs_laid, eggs_spent, cards_drawn (cards_drawn_tray + cards_drawn_deck), cards_tucked, cards_discarded, food_cached, bonus_cards_drawn
- End state: final_food, final_hand
- Setup: starting_food, starting_birds_kept (count), starting_birds_kept_known, starting_birds_discarded, starting_bonus, starting_bonus_discarded, bonus_cards (held at game end)
- Metadata (blank without `--metadata`): elo_before, elo_after, arena_before, arena_after

**moves.csv** — one row per action or power effect (~170 per game):
- Turn context: round_number, turn_number (turn within the round across players, so `table_id, round_number, turn_number` identifies a turn), player_turn (the active player's nth turn, 1–26), active_player_id, action (`play_bird`/`gain_food`/`lay_eggs`/`draw_cards`), action_column (1–6: the column the cube was placed on, i.e. the action's strength; blank for play_bird). Blank outside turns (setup, round goals, final scoring).
- `player_id` is who the costs/gains belong to; differs from `active_player_id` for pink powers and "all players" powers.
- `type`: setup, play_bird, gain_food, pay_food, lay_eggs, discard_egg, draw_cards, discard_cards, tuck_card, cache_food, hunt, move_bird, draw_bonus, discard_bonus, power_declined, power_failed, repeat_power, round_goal, bonus_score
- `source`: the bird whose power produced the row; blank = the base action or a rule
- `location` (slots like `forest_2`), `birds` (cards involved), `detail` (tray/deck/display for draws, birdfeeder/supply for food, hand/deck for tucks, success/fail for hunts, cached food type, goal or bonus name, failure reason, origin slot for move_bird)
- Cost/gain: gain_/cost_ × invertebrate/seed/fish/fruit/rodent, gain_eggs, cost_eggs, gain_cards, cost_cards (cards leaving hand), tucked, cached, gain_vp (round_goal and bonus_score rows only)
- The habitat trades are not separate types: a forest card-for-food trade is `cost_cards` on the gain_food row, a grassland food-for-egg trade is `cost_*` food on the lay_eggs row, a wetland egg-for-card trade is a `discard_egg` row with blank `source`.
- `setup` rows carry starting food in `gain_*`, kept bird count in `gain_cards` and the discarded birds in `birds`, so food and hand size reconcile from row 1.

**birds.csv** — one row per bird played: bird_id, bird, play_order, round_number, turn_number, player_turn, habitat, column, cost_* food, cost_eggs, activations (times the cube stopped on it), eggs_laid, times_moved, final_habitat, final_column, vp (printed), final_eggs, final_cached, final_tucked. Join static attributes from `birds.csv`.

**round_goals.csv** — one row per player per round: round_number, goal_id, goal, player_id, value, position, tied, points. `position` is blank for a player who scored 0 with a count of 0.

**setup.csv** — one row per game: num_players, start_time, end_time (unix seconds), game options from metadata as BGA labels (game_mode, game_speed, goal_board, powerful_birds, swift_start_birds, language_bonus_cards; blank without `--metadata`), goal_1..4, first_player_id, winner_player_id/name (blank when rank 1 is shared), player_ids, player_names, final_scores (seat order).

## Skip logic

`should_skip(packets)`: `conceded` (`table.concede`, or a concede/quit/neutralized event — these stop mid-game with no final scoring) and `no_result`.

## Reconciliation

`WingspanGameData.warnings` lists failed checks; the batch parser logs them and still writes the game. Checks: VP components sum to final_score; board slots, eggs, cache and tucked match the final scoring events per slot; 26 turns per player; food stock never negative and final food equals `score_aux`; hand size never negative. On the full corpus all 148,243 player rows pass the VP and turn checks; 3 games fail one of the others (one unlogged tuck, two food-stock mismatches). A new warning after a parser change means an unbooked cost or gain.
