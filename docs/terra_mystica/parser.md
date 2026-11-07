# Terra Mystica parser

How `bga_replay_parser/tm_*.py` turns a replay into CSVs: output columns, BGA event quirks, skip rules, reconciliation. Raw event schemas are in [bga_replay_format.md](bga_replay_format.md).

`TerraMysticaParser` in `tm_parser.py` converts raw BGA replay HTML into `TMGameData`; `tm_csv.py` flattens that into six CSVs (player results, round summaries, moves, leech offers, auction bids, setup). Uses `tm_models.py` for dataclasses, `tm_handlers.py` for event dispatch, `tm_constants.py` for faction/tile lookups.

## Data extraction

Two JSON sources are extracted from replay HTML:
1. **g_gamelogs** — game log packets (brace-balanced extraction from `g_gamelogs = {...}`).
2. **gamedatas** — static game setup from `gameui.completesetup(...)` call. Contains bonus_card_types, scoring_tile_types, favor_tile_types, town_tile_types (static defs) plus per-game assignments.

## Output views

**TMPlayerResult** — one row per player per game (~41 fields):
- Identity: player_id, player_name, faction, terrain, color, seat_order
- VP breakdown: starting_vp, final_vp, vp_round_scoring, vp_favor_tiles, vp_bonus_cards, vp_towns, vp_faction_ability, vp_power_leaching (≤0), vp_conversions (always 0; Alchemists' VP→coins is a negative part of vp_faction_ability), vp_track_advances, vp_cult_final, vp_network_final, vp_resources_final
- Structures: dwellings/trading_houses/temples/strongholds/sanctuaries_built, bridges_built, towns_formed
- Cult: cult_fire/water/earth/air (final positions, 0–10)
- Economy: coins/workers/priests/power/vp `_generated`, `_spent`, `_converted` and spades `_generated`/`_spent`, summed over the game
- Tracks: shipping_level, exchange_level, network_size
- Tiles: favor_tiles (list), town_tiles (list), bonus_cards (list of 6 in round order)

**TMRoundSummary** — one row per player per round (~34 fields):
- Round context: round_number, scoring_tile, bonus_card (held this round)
- Income phase: income_coins/workers/priests/power
- Cult bonuses (cleanup): cult_bonus_coins/workers/priests/power/spades
- Actions: num_actions, spades_used, dwellings_built, structures_upgraded, cult_advances, power_actions_used, towns_founded
- Power actions: power_actions (list of types like `["spade", "coins"]`)
- Power gained: power_gained_via_structures/cults/other
- Resource flow: coins/workers/priests/power `_generated`, `_spent`, `_converted` (net conversions; includes Alchemists VP↔coins)
- End-of-round state: vp_at_round_end, coins/workers_at_round_end, power_bowl1/2/3, cult positions
- Pass: pass_order (1=first)

**TMMove** — one row per action (~33 fields, ~500 per game):
- Action types: select_faction, place_initial_dwelling, select_bonus_card, transform_terrain, build_dwelling, upgrade_structure, advance_cult, send_priest_to_cult, advance_shipping, advance_exchange, power_action, special_action, faction_action, convert, found_town, choose_favor_tile, choose_bonus_card, receive_income, receive_cult_bonus, round_scoring, final_scoring, pass, power_via_structures, other
- `turn_number`: turn within the round, counted across all players, reset each round, so (`table_id`, `round_number`, `turn_number`) identifies one turn. Every row produced during the turn shares it: the active player's conversions, action and follow-ups, and other players' leech rows. Blank outside the action phase. A turn starts at BGA game state 41 (`gameStateChange`, the active player's main-action state). Every turn has at least one row, so numbers are contiguous.
- Hex labels: BGA's `bts_id` for every space, land and river alike (row letter A–I + position in the row counting all spaces, e.g. `A11`, `H6`). This is **not** Snellman notation, which skips rivers. See bga_replay_format.md → Hex Coordinates.
- `found_town` rows carry the town tile: `town_vp`, `town_resources` (e.g. `6coins`, `1priest`; empty for tiles whose extra is a cult step or shipping) and `tile_or_card` (e.g. `5vp_6coins`).
- Context: hex_coord, structure_type, upgraded_from, terrain_from/to, cult_track, cult_from/to, tile_or_card
- Cost/gain: cost_workers/coins/priests/power, gain_vp/coins/workers/priests/power
- `convert` rows: one per free-action conversion batch (`conversionsApplied` with non-zero amounts; what was given up is in `cost_*`, what was received in `gain_*`), plus one per Alchemists VP→coins trade (negative `gain_vp`), one per Darklings stronghold workers→priests trade, and one per The Enlightened coins→power-token purchase. Conversions are free actions, not turns; `move_number` is a row sequence over all rows (scoring, leech, income, conversions), not a turn index — use `turn_number` for turns.
- `special_action` rows and `special_action_type`: `bonus` / `favor` (bonus-card or favor-tile action, logged after the cult step or transform it granted), `stronghold` (one row per stronghold action, from BGA's `actionUsed` with `stronghold: true`; logged before the effect rows for most factions — Witches' build, Nomads'/Giants' transform, Swarmlings' upgrade, Auren's cult step, Conspirators' favor swap, Chaos Magicians' double action — and after them for Architects' bridge, Children of the Wyrm's tokens, The Enlightened and Time Travellers), `cultists_ability` (the Cultists' cult step after an opponent leeches), `goblins_ability`. Blank only for a handful of cult steps BGA logs without a source.
- `faction_action` rows: Goblins spending a Treasure token (gains in `gain_*`); Children of the Wyrm stronghold action (the two token hexes in `hex_coord`/`secondary_hex`). A Treasurers power action whose proceeds go to the Treasury is a `power_action` row described "(n to Treasury)" with no `gain_*` (the deposit never reaches the board). Gold Diggers' stronghold action is a `special_action` with `special_action_type="stronghold"`. End-of-game automatic resource→coin conversion is not emitted.

**TMLeechOffer** (`leech_offers.csv`) — one row per leech ("power via structures") offer per offered player, including declines, which leave no row in `moves.csv`:
- offer_id (running number of the leech phase in the game), round_number, turn_number (the builder's turn; joins to `moves.csv`), builder_id, target_id
- n_offered (targets in the phase with offered > 0), offered (power the target could take), cap (extra adjacency power cut off because their bowls were too full)
- auto (1 = free 1-power leech BGA took without asking; never listed as an offer), response (`accept` / `decline` / `none`), gained, vp_cost
- `accept` rows match `power_via_structures` rows in `moves.csv` on (round_number, turn_number, player, power gained): all but 30 of 2.35 M leech rows (12 games). The exceptions are mostly late answers, where BGA logs the leech in a later turn than the offer.

**TMAuctionBid** (`auction_bids.csv`) — one row per (player, faction) bid in auction games: faction, bid_starting_vp, is_winning_bid. Fast auctions have exactly one bid per pair; slow (standard) auctions are collapsed to each player's last bid on each faction, so the table is sparse (only factions that player bid on). `TMGameData.auction_type` (`"fast"`/`"slow"`/`""`) is derived from bid sequences and is the reliable auction indicator; the `starting_vp_setting` game-option label is unreliable pre-2023.

**setup.csv** — one row per game: game-level `TMGameData` fields (board, options, scoring tiles, bonus cards, winner), plus `game_mode` and `starting_vp_setting` from table metadata. `with_auction` = bids present OR the gamedatas flag (the flag alone misses ~12k pre-2023 slow auctions). Use `auction_type != ""` to select auction games, never `starting_vp_setting`.

## Event handling

`EVENT_HANDLERS` in `tm_handlers.py` maps every BGA event type seen in replays (~56) to a handler; about half are explicit no-ops. Key quirks:
- `incomePhase` is its own event type (not `justAMessage`). Fires once with no player_id (round marker) then per-player with income HTML.
- `someIncome` during cleanup phase carries cult bonus resources (detected via `addendum="(Cult bonus)"`). Pre-mid-2022 replays use a separate `cultBonus` event instead. Cult-bonus spades are read from `spade_income` (on `cultBonus`, or on `updateCounters` in later replays).
- `structureUpgraded` cost is one `resource_cost` field from mid-2022; older replays split it into `workers_cost` + `coins_cost`. The handler reads both.
- `townBonus` VP is not tracked via `updateScore` — captured directly from townBonus event.
- `powerViaStructures` VP cost is silent — detected from newScore field.
- Alchemists trades are `justAMessage` events ("converts ... (Alchemists Ability)") carrying the amounts, always followed by a `conversionsApplied` carrying `newScore`. VP→coins is a conversion: `convert` row, coins in `coins_converted`, VP (negative) in `vp_faction_ability`. Coins→VP (2:1) is treated as their end-game resource scoring, not a conversion: no row, nothing in `coins_converted`, VP in `vp_resources_final`, and `coins_at_round_end`/`vp_at_round_end` are reported as if the trade had not happened yet.
- There is no workers counter in `updateCounters`. Worker stock (`workers_at_round_end`) comes from the 65 worker tokens (`workers: {worker_id: {player_id}}`): build/upgrade/transform events send all of them, income/bonus/conversion/power-action events only the ones that moved, so the parser keeps an owner per token.
- In rounds 1–5 the first player to pass gets `firstPlayerChanged` instead of `playerPassed`; both produce a `pass` row and a `pass_order`.
- Some ability gains exist only as a logged `updateCounters`: Conspirators coins (`coins_bonus`), Gold Diggers stronghold action (`coins_gain`), Wisps/Halflings free spades.
- Treasurers: deposits (`updateTreasury`) are withheld before resources reach the board, except `addendum="(Conversion)"` which comes off the board. The doubled return arrives as a `someIncome` right after `emptyTreasury`.
- The final-scoring phase starts at the "~ Final scoring ~" message, and only once round 1 has begun: in setup, the game-option message "Fire and Ice - Final Scoring tiles: …" also mentions final scoring.
- `select_faction` descriptions record the faction BGA logged as selected, which in some newer fan-faction setups differs from the faction the player ends up with. The `faction` column on every row is the player's final faction.
- Round 6 has no Cleanup phase marker — goes straight to `~ Final scoring ~`.

## Excluded factions

`should_skip_replay()` skips games with: shapeshifters, riverwalkers, changelings, geologists, dragonlords, acolytes, firewalkers, kingdomofember. Also skips games with the landscapes expansion (`landscape_active` in gamedatas, or any `landscapePlaced` event).

## Starting cult positions

BGA logs no event for a faction's starting cult steps. The parser takes them from the game's own faction specs (`gamedatas.factions` / `alternate_factions`, `<cult>cult_setup`) when the faction is assigned, so round snapshots and final `cult_*` include them even for tracks that never moved. Setup choices (e.g. Djinn) arrive later as `advanceCultTrack` and overwrite.

## VP reconciliation

Sum of VP components (starting_vp + all `vp_*` columns) equals `final_vp` exactly for 99.99% of player rows; the remainder are conceded-game artifacts. Three handler details make this hold: `powerActionBridge` buckets the Architects-stronghold VP from `score_inc` (the follow-up updateScore has score_delta=0), `advanceIncomeTrack` buckets Chash Dallah income-track VP the same way, and `factionBoardSwapped` initializes player state (fan-faction games have no `factionPositionSelected`; without init the starting-VP updateScore was dropped and mis-bucketed later). Alchemists' VP→coins goes to `vp_faction_ability` (negative); `vp_conversions` is always 0.

## Resource reconciliation

For coins and workers, cumulative `generated − spent + converted` through any round equals the stock at that round's end minus the starting stock (15 coins / 3 workers for most factions), exactly, for every faction — checked on ~10k player-rounds across 2020–2026. A mismatch after a parser change means an unbooked cost or gain. Priests in hand (from the `priests` token list) match the same way at 99.8% of checks; the known misses are the end-of-game auto-conversion and rare Fakirs transforms where BGA omits the carpet-flight priest from `other_cost`. Power is not reconciled.
