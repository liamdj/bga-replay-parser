# Tokaido parser

How `bga_replay_parser/tokaido_*.py` turns a replay into CSVs: output columns, move types, skip rules, VP reconciliation. Raw event schemas are in [bga_replay_format.md](bga_replay_format.md).

`TokaidoParser` in `tokaido_parser.py` reads BGA Tokaido replays into per-player and per-move CSV-friendly views. Uses `tokaido_models.py` for dataclasses and `tokaido_constants.py` for souvenir/position/object lookups. Event dispatch is inline.

## Raw input format

Tokaido raw replays are stored as JSON gamelogs (the format produced by the BGA `/archive/archive/logs.html` API): a flat list of packets, each with a `data: [...events]` array. Same packet schema as the inner `g_gamelogs.data.data` list extracted from HTML replays — the parser also accepts the dict-wrapped form for symmetry with TerMys.

## Output: 4 CSVs, base and Crossroads kept separate

Base game and Crossroads expansion differ enough that mixing them adds noise (19 Crossroads-only VP/count/flag columns would be 0 in every base row). Each game routes to one of two player files and one of two moves files:

- `player_results_base.csv` — one row per player per base game (42 columns)
- `player_results_xroads.csv` — one row per player per Crossroads game (61 columns: base + 19 Crossroads-only)
- `moves_base.csv` — one row per action in a base game (15 columns)
- `moves_xroads.csv` — one row per action in a Crossroads game (same columns; only `type` value space differs)

`game.has_crossroads` is set during parsing — true if any of `CherryTree`, `BathHouse`, `Calligraphy`, `CalligraphyScored`, `LegendaryObject`, `Amulet`, `AmuletUsed` move types appear.

**TokaidoPlayerResult**:
- Game: table_id, num_players, preparations (bool: Preparations expansion in play)
- Identity: player_id, player_name, player_color, traveler, starting_position, starting_coins (post-Preparations allocation when that expansion is on)
- Result: final_score, score_aux (BGA tiebreaker = achievements count), final_rank, is_winner
- VP breakdown (sums to final_score for all but ~9 of ~270K rows — see VP reconciliation): vp_panorama_mountain/sea/field, vp_temple, vp_temple_rank, vp_hot_spring, vp_encounter, vp_inn, vp_village, vp_achievement, vp_other (+ Crossroads-only: vp_calligraphy, vp_legendary_script/offering/sword, vp_bath_house, vp_cherry_tree, vp_legend_bonus)
- Donation routing: vp_temple includes Miko encounter VP and Devotion-amulet VP (both are temple donations); num_donations counts these too. Miko still increments num_encounters; Devotion still increments num_amulets_used. There is no `vp_amulet_used` column — Devotion is the only amulet that scores VP, and it goes to vp_temple.
- Action counts: num_actions, num_meals, num_encounters, num_villages_visited, num_donations, num_panorama_cards_mountain/sea/field, first_to_finish_mountain/sea/field (bools), num_souvenirs_food/clothing/art/trinket (+ Crossroads-only: num_amulets_purchased/used, num_calligraphies, num_legendary_script/offering/sword, has_calligraphy_foresight/contemplation/nostalgia/patience/perfection/fasting bools)
- Economy: coins_gained_total, coins_spent_total, coins_donated_total

The Crossroads-only field list lives at `bga_replay_parser.tokaido_models.XROADS_ONLY_PLAYER_FIELDS` (what the writer drops for the base CSV). Calligraphy `type_arg → name` mapping in `tokaido_constants.CALLIGRAPHY_TYPE_ARG_TO_NAME`.

**TokaidoMove** — one row per scoring/economy action (~200 per game):
- table_id, move_number, player_id, traveler, type, subtype, space
- coins_gained, coins_spent, coins_donated, points_gained
- souvenirs_food/clothing/art/trinket

## Move types (the `type` column)

`Traveled`, `Village`, `Temple`, `TempleRank`, `HotSpring`, `Panorama`, `Inn`, `RoadMeal`, `Encounter`, `Achievement`, `Farm`, `CherryTree`, `BathHouse`, `LegendaryObject`, `Calligraphy`, `CalligraphyScored`, `Amulet`, `AmuletUsed`, `Gaming`, `JirochoGaming`, `DaigoroSouvenir`, `LegendBonus`, `TravelerAbility`. The Crossroads-only types are also flagged at the game level via `has_crossroads`.

`RoadMeal` is the meal from The New Encounters' Itamae card (scored into `vp_inn`/`num_meals` but not an Inn stop). New Encounters paid cards (Itamae, Kitoushi, Takuhatsuso) are `Encounter` rows with `coins_spent=1`; Saru's VP goes to `vp_hot_spring`. See `bga_replay_format.md` → Encounters.

The parser uses `Panorama` with the color in `subtype` (not separate `Mountain`/`Sea`/`Field` types). `Achievement` rows for completed panoramas use `subtype="mountain_panorama"` etc.

## VP reconciliation

Sum of `vp_*` components equals `final_score` for all but ~9 of ~270K player rows (small unexplained positive gaps). The 21 games with sentinel `score_aux` (-4245 abandoned, -4242 zeroed result) used to account for another ~84 negative-residual rows; they are now skipped.

Until 2026-09 the parser missed The New Encounters cards (Saru, Takuhatsuso, Itamae's road meal), which left 1.7% of base rows and 11.4% of Crossroads rows short by typically 2–10 VP — concentrated in Preparations games only because those tables have The New Encounters on 55% of the time (vs 9% otherwise). CSVs parsed before that fix carry the gap.

Traveler abilities are handled correctly: the parser captures explicit traveler-ability log lines (`Hirotada: ...`, `Umegae: ...`, `Gotozaemon: ...`, `Nampo: ...`, `Mitsukuni: ...`) as their own `TravelerAbility` rows rather than inlining the bonus on the main action — modern BGA replays emit both, so inlining would double-count.

## Skip logic

`should_skip(packets)` returns a reason string for:
- Fewer than 3 players (2p Tokaido is unsupported).
- A negative `score_aux` in the replay's result block (normal games have `score_aux` ≥ 0 = achievement count): `-4245` = abandoned (remaining players scored 1, the leaver 0); `-4242` = finished game whose archived result is zeroed (all 0, all rank 1), so `final_score`/rank are unusable.

 Preparations games are parsed: the expansion only redistributes starting coins, which `travelerChosen.player_coins` already reflects; the `preparations` column flags them.
