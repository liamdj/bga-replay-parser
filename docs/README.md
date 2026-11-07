# Docs

Reference docs for the games this repo parses. Each file covers a focused area so you only need to read what's relevant.

## Terra Mystica — [terra_mystica/](terra_mystica/)

| File | Covers |
|------|--------|
| [parser.md](terra_mystica/parser.md) | Parser output: the five CSVs and their columns, `turn_number`/`convert` row semantics, BGA event quirks, excluded factions, VP and resource reconciliation. |
| [basics.md](terra_mystica/basics.md) | High-level rules: 8 actions, scoring, towns, adjacency, terrain types, setup. Faction-terrain mapping tables for base/F&I/fan factions. Lists excluded factions to skip. |
| [specifics.md](terra_mystica/specifics.md) | Standard building costs & income slots, power actions, shipping/exchange tracks, favor tiles, scoring tiles, bonus cards, town tiles, cult thresholds. No faction-specific data. |
| [factions.md](terra_mystica/factions.md) | 14 base factions: per-faction starting power, abilities, non-standard building costs/income, stronghold abilities. |
| [fire_ice_factions.md](terra_mystica/fire_ice_factions.md) | Fire & Ice factions: Ice (Ice Maidens, Yetis), Volcano (Dragonlords, Acolytes), Variable (Shapeshifters, Riverwalkers). |
| [fire_ice_scoring.md](terra_mystica/fire_ice_scoring.md) | F&I final scoring tiles: Greatest Distance, SH-SA distance, Outposts (border), Settlements count. All use 18/12/6 VP area-scoring rules. |
| [fan_factions.md](terra_mystica/fan_factions.md) | 14 fan factions for the 7 standard terrains. Per-faction starting power, abilities, non-standard costs. |
| [fire_ice_fan_factions.md](terra_mystica/fire_ice_fan_factions.md) | 6 F&I fan factions: Ice (Selkies, Snow Shamans), Variable (Changelings, Geologists), Volcano (Firewalkers, Kingdom of Ember). Parser skips variable/volcano. |
| [fan_faction_balance_history.md](terra_mystica/fan_faction_balance_history.md) | When each fan faction was last rebalanced, recovered from per-game `gamedatas` specs. Three patch waves (~2022-09, ~2022-12, ~2024-07) + standalone tweaks. Data floor ~2022-03. |
| [bga_replay_format.md](terra_mystica/bga_replay_format.md) | `g_gamelogs` structure, all event types (base + fan-faction-specific), args field schemas, HTML resource icon formats, skip rules for excluded factions/landscapes/maps. |

## Tokaido — [tokaido/](tokaido/)

| File | Covers |
|------|--------|
| [parser.md](tokaido/parser.md) | Parser output: the four CSVs and their columns, move types, VP reconciliation, skip logic. |
| [basics.md](tokaido/basics.md) | Core rules: 8 space types, souvenir family scoring (1/3/5/7), panorama tracks, encounter card effects, meal rules at Inns, Temple donation ranking (10/7/4/2 VP), end-game achievements (Gourmet/Bather/Chatterbox/Collector). 2p variant. |
| [crossroads.md](tokaido/crossroads.md) | Crossroads expansion: per-space alt option, 6 Amulets (Vitality/Fortune/Health/Friendship/Hospitality/Devotion), 6 Calligraphies (end-game scoring), 3 Legendary Object types (script/offering/sword), Donation routing notes for Devotion/Miko, new move types. |
| [travelers.md](tokaido/travelers.md) | All 16 traveler abilities (10 base + 6 Crossroads). Notes on `TravelerAbility` move rows and per-traveler log line formats. Skip rules for Preparations expansion and 2p games. |
| [bga_replay_format.md](tokaido/bga_replay_format.md) | JSON gamelogs structure (`/archive/archive/logs.html` API), every dispatched event template, type_arg → name maps (calligraphies / amulets / legendary), bank-funded donation quirks (Miko / Hirotada / Devotion), Gaming-Room net-vs-gross quirk, VP reconciliation. |

## Wingspan — [wingspan/](wingspan/)

| File | Covers |
|------|--------|
| [parser.md](wingspan/parser.md) | Parser output: the CSVs and their columns, turn structure, skip logic, reconciliation checks. |
| [basics.md](wingspan/basics.md) | Core rules: 4 rounds of 8/7/6/5 turns, the four actions and their strength per column, habitat trades, egg costs, power colours, setup, the six VP components, round-goal majority scoring. Arena format seen in the corpus. |
| [cards.md](wingspan/cards.md) | BGA id tables: 180 birds (base + Swift Start), 26 bonus cards, 16 round goals (mapping derived from board state). Column reference for `birds.csv`. |
| [birds.csv](wingspan/birds.csv) | Static attributes of the 180 BGA birds keyed by `bird_id`: VP, nest, egg capacity, wingspan, habitats, food cost, power colour/category/text, bonus-card eligibility. |
| [bird_data.json](wingspan/bird_data.json) | Source of `birds.csv`: 446 birds across all sets with rulings text. Its `id` is not the BGA id. |
| [bga_replay_format.md](wingspan/bga_replay_format.md) | JSON gamelogs structure, public/private channel pairing, undo behaviour, slot/food/dice encodings, turn structure, every gameplay and scoring event, result-block stat keys, the 2024-09 `drawBirdsPublic` change, skip rules, reconciliation checks. |
