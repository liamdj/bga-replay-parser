# Wingspan Cards: Birds, Bonus Cards, Round Goals

BGA numeric ids and reference data for the three card types. The id → name tables live in `bga_replay_parser/wingspan_constants.py`.

## Birds

| File | Contents |
|------|----------|
| [birds.csv](birds.csv) | The 180 birds BGA uses (base + Swift Start), keyed by BGA `bird_id`. Join to parsed `birds.csv` / `moves.csv` on `bird` (name) or `bird_id`. |
| [bird_data.json](bird_data.json) | Source for the above: 446 birds across base, Swift Start, European, Oceania and Asia, with rulings text and per-bonus-card eligibility flags. Its `id` field is **not** the BGA id. |

BGA bird ids:

- `0–169` — base-game birds in alphabetical order.
- `170–179` — Swift Start promo birds: American Redstart, Black-Chinned Hummingbird, Brant, Broad-Winged Hawk, Canvasback, Painted Whitestart, Red-Breasted Merganser, Scaled Quail, Vaux's Swift, White-Throated Swift.
- `53`, `62`, `76`, `96` (Chihuahuan Raven, Common Raven, Franklin's Gull, Killdeer) never appear in the corpus (`in_arena_corpus = 0`).

`birds.csv` columns:

| Column | Meaning |
|--------|---------|
| `bird_id`, `bird`, `scientific_name` | BGA id and names. `bird` matches the spelling BGA logs use, case-insensitively. |
| `set` | `base` or `swift_start` |
| `in_arena_corpus` | 0 for the four birds never seen |
| `vp`, `nest`, `egg_capacity`, `wingspan_cm` | Printed values. `nest` is `bowl`/`cavity`/`ground`/`platform`/`wild`/`none` (`none`: the two cowbirds). |
| `forest`, `grassland`, `wetland` | 1 if the bird may be played there |
| `cost_invertebrate` … `cost_rodent`, `cost_wild`, `cost_total`, `cost_is_or` | Food cost. `cost_is_or` = 1 when the listed foods are alternatives (pay any one). |
| `power_color` | `brown` / `pink` / `white` / `none` |
| `power_category`, `power_text` | Power classification and full text |
| `predator`, `flocking`, `draws_bonus_card` | 1 if the power hunts / tucks from hand / draws bonus cards |
| `bonus_cards` | `;`-joined bonus cards this bird counts toward (per-bird bonus cards only) |

## Bonus cards

26 bonus cards, `index` in `scoreBonus` / keys of `bonus_data`:

| id | Name | id | Name |
|---|---|---|---|
| 0 | Anatomist | 13 | Large Bird Specialist |
| 1 | Backyard Birder | 14 | Nest Box Builder |
| 2 | Bird Counter | 15 | Omnivore Specialist |
| 3 | Bird Feeder | 16 | Oologist |
| 4 | Breeding Manager | 17 | Passerine Specialist |
| 5 | Cartographer | 18 | Photographer |
| 6 | Ecologist | 19 | Platform Builder |
| 7 | Enclosure Builder | 20 | Prairie Manager |
| 8 | Falconer | 21 | Rodentologist |
| 9 | Fishery Manager | 22 | Visionary Leader |
| 10 | Food Web Expert | 23 | Viticulturalist |
| 11 | Forester | 24 | Wetland Scientist |
| 12 | Historian | 25 | Wildlife Gardener |

Breeding Manager, Ecologist, Oologist and Visionary Leader score on board state (eggs, habitat sizes, hand size), not on per-bird attributes, so they have no column in `bird_data.json`. `bird_data.json` calls Omnivore Specialist "Omnivore Expert" and also lists bonus cards from expansions.

## Round goals

16 goals — eight double-sided tiles in the physical game. The goal for each round is in the result block's table stats `40`–`43` (see [bga_replay_format.md](bga_replay_format.md)); the ids are not named anywhere in the logs. The mapping below was derived by matching every scored goal value against tracked board state and is exact.

| id | `goal` | Counts |
|---|---|---|
| 0 | `eggs_in_bowl_nests` | Eggs on birds with a bowl nest |
| 1 | `eggs_in_cavity_nests` | Eggs on birds with a cavity nest |
| 2 | `eggs_in_ground_nests` | Eggs on birds with a ground nest |
| 3 | `eggs_in_platform_nests` | Eggs on birds with a platform nest |
| 4 | `birds_in_forest` | Birds in the forest row |
| 5 | `birds_in_grassland` | Birds in the grassland row |
| 6 | `birds_in_wetland` | Birds in the wetland row |
| 7 | `total_birds` | Birds on the board |
| 8 | `bowl_nest_birds_with_eggs` | Bowl-nest birds holding at least one egg |
| 9 | `cavity_nest_birds_with_eggs` | Cavity-nest birds holding at least one egg |
| 10 | `ground_nest_birds_with_eggs` | Ground-nest birds holding at least one egg |
| 11 | `platform_nest_birds_with_eggs` | Platform-nest birds holding at least one egg |
| 12 | `eggs_in_forest` | Eggs on forest birds |
| 13 | `eggs_in_grassland` | Eggs on grassland birds |
| 14 | `eggs_in_wetland` | Eggs on wetland birds |
| 15 | `sets_of_eggs` | Sets of one egg in each habitat (the minimum of the three habitat egg counts) |

Star (`wild`) nests count as every nest type. Each of the 16 goals appears in roughly a quarter of games.
