# Wingspan Basics

Rules summary for reading the parsed data. Covers the base game as played on BGA Arena (the only configuration in the corpus: base birds + Swift Start promo birds, no expansions).

## Structure

- 4 rounds. Each player takes **8 / 7 / 6 / 5** turns in rounds 1–4 — 26 turns per game, always.
- A turn is one of four actions, chosen by placing an action cube:

| Action | Row | Base effect |
|--------|-----|-------------|
| Play a bird | — | Pay the bird's food cost and the column's egg cost; put it in the leftmost empty slot of one of its habitats |
| Gain food | Forest | Take food dice from the birdfeeder |
| Lay eggs | Grassland | Put eggs on birds with free nest capacity |
| Draw cards | Wetland | Draw bird cards from the 3-card tray or the deck |

- For the three habitat actions the cube goes on the **leftmost empty slot of the row**, so each bird already in the row makes the action stronger. The cube then moves right-to-left over the row's birds, activating each brown power, and ends at the row's start.
- At the end of each round: the round goal is scored, the tray is discarded and refilled, and the first-player token passes on.

## Player board

Three rows (forest, grassland, wetland) of five columns. The parser labels slots `forest_1` … `wetland_5`.

| Column the cube is on | 1 | 2 | 3 | 4 | 5 | 6 (row full) |
|---|---|---|---|---|---|---|
| Gain food | 1 | 1 + | 2 | 2 + | 3 | 3 + |
| Lay eggs | 2 | 2 + | 3 | 3 + | 4 | 4 + |
| Draw cards | 1 | 1 + | 2 | 2 + | 3 | 3 + |

`+` = optional trade for one more: discard a **bird card** for a food (forest), a **food** for an egg (grassland), an **egg** for a card (wetland).

Egg cost to play a bird into a column: **0 / 1 / 1 / 2 / 2** for columns 1–5.

## Food

Five types: invertebrate, seed, fish, fruit, rodent. Food comes from the birdfeeder (five dice; rerolled when empty, or optionally when all showing dice match) or, for some powers, straight from the supply. One die face is invertebrate-or-seed; the player picks one when taking it.

## Birds

Each bird card has: habitat(s), food cost, VP, nest type (bowl / cavity / ground / platform / star = wild / none), egg capacity, wingspan, and usually a power:

| Power colour | Triggers |
|---|---|
| Brown ("when activated") | Each time the action cube passes over the bird |
| Pink ("once between turns") | On a specific action by another player |
| White ("when played") | Once, when the bird is played |
| None | — |

Common power effects: gain food, lay eggs, draw cards, **tuck** a card behind the bird (1 VP each), **cache** food on the bird (1 VP each), hunt (predators: reveal a card and tuck it if its wingspan is under a limit, or roll dice outside the feeder and cache on a hit), draw bonus cards, repeat another bird's power, move to another habitat.

Bird cards are unique — one copy of each in the deck. Static per-bird attributes are in [birds.csv](birds.csv) (see [cards.md](cards.md)).

## Setup

- Each player is dealt 5 bird cards and holds 5 food (one of each type), then keeps any **5 in total** — every bird kept costs one food.
- Each player is dealt 2 bonus cards and keeps 1.
- Four round goals are drawn, one per round.

## Scoring

Final score is the sum of six components (the `vp_*` columns):

| Component | Points |
|---|---|
| Birds | Printed VP of every bird on the board |
| Bonus cards | Each bonus card scores by the number of qualifying birds |
| Round goals | See below |
| Eggs | 1 per egg on a bird at game end |
| Cached food | 1 per food token cached on a bird |
| Tucked cards | 1 per card tucked behind a bird |

Tiebreaker: unused food tokens (BGA `score_aux`).

### Round goals

BGA Arena uses the competitive (majority) side of the goal board. Players are ranked by their count for the round's goal:

| Round | 1st | 2nd | 3rd |
|---|---|---|---|
| 1 | 4 | 1 | 0 |
| 2 | 5 | 2 | 1 |
| 3 | 6 | 3 | 2 |
| 4 | 7 | 4 | 3 |

Tied players add up the points for the places they occupy and split them, rounded down. A player with a count of 0 scores 0. The 16 goals are listed in [cards.md](cards.md).

## Arena format in the corpus

- Arena seasons 11–19 (2022-10 → 2025-01). 3-player until April 2023 (seasons 11–12), 2-player after.
- Wood Duck is not played after April 2024 (removed from the Arena deck from season 17).
- Four base birds never appear: Chihuahuan Raven, Common Raven, Franklin's Gull, Killdeer. This is the table option `Powerful bird cards: Remove` (later `Remove + Wood Duck`).
- Table options (from `tableinfos`, surfaced in `setup.csv`): `Game mode`, `Game speed`, `Goal board` (`Green` = majority scoring), `Powerful bird cards`, `Swift Start Birds` (`Do not use` / `Shuffle into deck`), `Language-dependent bonus cards`.
