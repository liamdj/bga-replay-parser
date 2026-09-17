# Tokaido — Base Game Rules

A travel-themed game where 2–5 players walk the historical Tokaido road from Kyoto to Edo, scoring points by collecting experiences (souvenirs, panoramas, hot springs, encounters, donations, meals).

## Object of the game

Each player controls one Traveler. On a turn, **the player whose Traveler is farthest behind moves**. He moves forward to any open space (skipping past spaces is allowed) and collects that space's reward. If after moving he is still last, he moves again. Game ends when all Travelers have arrived at the final Inn (Edo).

Most points are scored immediately when earned. A few are awarded at the end (Temple ranking + 4 end-game achievements).

## Setup

- Each player picks 1 of 2 random Traveler tiles. Starting bank = number printed on the chosen tile.
- All Travelers line up at the first Inn (Kyoto) in random order.
- `Preparations` variation: order-of-departure adjusts starting bank by ±1/±2 coins (4-player example: last gets +2, third +1, second +0, first −1).

## The board: 8 space types + 4 Inns

| Type | Effect |
|------|--------|
| Village | Reveal top 3 Souvenir cards; buy any number for printed cost (1/2/3 coins). Unbought go to bottom of deck. Must have ≥1 coin to stop. |
| Farm | Take 3 coins from the bank. |
| Panorama (Sea / Mountain / Field) | Take the next-numbered card in the matching panorama track (1, then 2, then 3...). Score immediately for the card's value. Cannot revisit a panorama type once completed. |
| Hot Spring | Draw a Hot Spring card (worth 2 or 3 VP, scored immediately). |
| Temple | Donate 1, 2, or 3 coins. Score 1 VP per coin immediately. Coins go on the temple track in your color (used for end-game ranking). Must donate at least 1. |
| Encounter | Draw top Encounter card and apply effect (see below). |
| Inn | Mandatory — every Traveler must stop at every Inn (5 total: Kyoto, 3 intermediate, Edo). |

### Single vs double spaces

Each space type appears multiple times along the route. Some are doubled (an off-road second slot). **Doubled spaces are only used in 4–5p games**; in 2–3p games only the on-road slot is usable. When two Travelers occupy a double space, the first arrival gets the road slot — turn order out of the space follows board position.

### Position layout

Positions 2–55 along the road map to specific space types — see `bga_replay_parser/tokaido_constants.py::POSITION_TO_SPACE`. Inn positions: `15` (Inn_1, mid), `28` (Inn_2, mid), `42` (Inn_3, mid), `55` (Inn_4, Edo/final). Position `1` is the starting Inn (Kyoto). The 4 mandatory Inns are Kyoto + 3 intermediate + final, but in code we see Inn_1..Inn_4 corresponding to the 4 stops *after* Kyoto (i.e. 3 intermediate + final).

## Souvenirs (Village space)

24 cards across 4 families: **food**, **clothing**, **art**, **trinket** (small objects). Each card costs 1/2/3 coins.

A "set" can hold one Souvenir of each family. Within a set, cards score by *order added*:

| Cards in set | VP for that card |
|--------------|------------------|
| 1st          | 1 |
| 2nd (different family) | 3 |
| 3rd (different family) | 5 |
| 4th (different family) | 7 |

So a complete 4-family set = 1+3+5+7 = 16 VP. A second copy of a family starts a new set (so two food + one clothing + one art = 1+1+3+5 = 10).

Souvenir family is mapped from BGA `type_arg` in `tokaido_constants.SOUVENIR_TYPE_ARG_TO_CATEGORY`.

## Panorama (Sea / Mountain / Field)

Three panoramas, each made of cards numbered 1, 2, 3, ... up to the panorama's length (3, 4, or 5 sections). On a panorama space, take the next card *for that color* you haven't taken yet, score VP equal to its number.

Each Traveler can only build *one* panorama of each color — once you complete a color, that space type is closed to you.

**First Traveler to complete each panorama** gets the matching Panorama Achievement (3 VP), awarded mid-game when completion happens.

## Encounters

Reveal top Encounter card. 5 base effects (multiple copies of each in a 14-card deck):

| Card | Effect |
|------|--------|
| Shokunin (traveling merchant) | Take the top Souvenir card and add to collection (scores 1/3/5/7 by family). |
| Annaibito (guide) | Take next-numbered card from any panorama you haven't completed. Score it. |
| Samurai | +3 VP. |
| Kuge (noble) | +3 coins. |
| Miko (Shinto priest) | Take 1 coin from the bank and donate it to the Temple. Score 1 VP. |

After resolving the effect, the card goes face-up into your collection (counts toward Chatterbox).

### The New Encounters (BGA option)

Promo module that adds 4 cards to the Encounter deck. Three of them cost 1 coin; a player who can't or won't pay declines and gets nothing (logged as `declines to pay for an encounter`).

| Card | Cost | Effect |
|------|------|--------|
| Itamae (cook) | 1 coin | Draw a Meal card. If you don't already own that meal, add it to your collection and score its 6 VP; otherwise nothing. |
| Kitoushi | 1 coin | Choose a panorama you haven't completed, take its next card and score it (like Annaibito, but paid). |
| Saru (monkey) | — | Draw a Hot Spring card and score it (2 or 3 VP). |
| Takuhatsuso (mendicant monk) | 1 coin | Score 4 VP. |

A meal gained from Itamae counts as a meal (collection, Gourmet) even though it wasn't eaten at an Inn.

## Inns

All 4 Inns are mandatory. On arrival, the **first Traveler to reach this Inn** draws (player_count + 1) Meal cards in secret (the `Gastronomy` variation reduces this to player_count, making meal availability tighter). They optionally buy one for its printed cost (1/2/3 coins) — Meals are always worth **6 VP** regardless of price. Subsequent arrivals buy from the remaining cards.

Constraints:
- A Traveler may not buy the same meal name twice in one game (across all Inns).
- At most 1 Meal per Inn.
- Buying is optional; Travelers can "go hungry."

After all Travelers have arrived, unbought meals go to the bottom of the deck and the journey resumes (the player still last on the road moves first).

Meal name → cost in `tokaido_constants.MEAL_COST`.

## Game options (BGA modules)

Table-level options in `table_ids.json` (`tables[].options`). Share of the 296K indexed tables with each on:

| Option | On | Effect |
|--------|--:|--------|
| Crossroads | 26% | Expansion — see [crossroads.md](crossroads.md). |
| Gastronomy | 37% | First arrival at an Inn draws `player_count` Meal cards instead of `player_count + 1`. |
| Preparations | 19% | Redistributes starting coins by seat. Observed in 4p games (the only player count in the corpus with it on): `starting_position` 1 → +2, 2 → +1, 3 → +0, 4 → −1. |
| The New Encounters | 18% | 4 extra Encounter cards — see Encounters above. |
| Return trip | 2% | Board is traveled in reverse (right to left). |
| Initiation | 1% | Simplified intro: no traveler selection, everyone starts with 7 coins. |

Rule text for these comes from BGA's Tokaido game help page; the Preparations coin table and the encounter behaviour were checked against replay logs.

## End of game

Triggered when the last Traveler arrives at the final Inn (Edo).

### Temple donation ranking

VP awarded by *rank of total coins donated to the Temple track*:

| Rank | VP |
|------|----|
| 1st  | 10 |
| 2nd  | 7 |
| 3rd  | 4 |
| Other (with ≥1 coin donated) | 2 |
| 0 coins donated | 0 |

Ties: all tied players score the higher rank's VP.

Coins donated come from: regular Temple stops, Miko encounter, Hirotada's free coin, Devotion Amulet (Crossroads), and the Neutral Traveler in 2p games.

### End-game achievement cards

Awarded after all Travelers reach Edo. Each = 3 VP. Ties → both score 3 VP.

| Card | Awarded to |
|------|-----------|
| Gourmet | Highest sum of coins on Meal cards |
| Bather | Most Hot Spring cards |
| Chatterbox | Most Encounter cards |
| Collector | Most Souvenir cards (Crossroads: Legendary Objects also count toward Collector) |

The 3 Panorama Achievements (Sea/Mountain/Field) are awarded mid-game on first completion — see Panorama section.

### Tiebreaker

If final VP ties: most achievement cards wins. (BGA exposes this as `score_aux` = achievement count.)

## Two-player variant

Adds a Neutral Traveler. Whoever is *ahead* on the road moves the Neutral Traveler when it is last. Neutral Traveler has no effect on most spaces *except*:
- **Temple**: take 1 coin from the bank, place it on the Neutral's color track (counts in end-game donation ranking).
- **Inn**: first Inn-arrival draws 4 Meal cards; when the Neutral lands on an Inn, the player who moved him takes the Meal cards and discards one at random.

(BGA games with <3 players are unsupported by our parser — see `should_skip` in `tokaido_parser.py`.)

## VP Reconciliation Note

Sum of `vp_*` columns equals `final_score` for all but a handful of rows (see the reconciliation section in [bga_replay_format.md](bga_replay_format.md)). Modern BGA replays emit per-traveler-ability log lines (e.g. `Hirotada: ${player} earns ${points}`, `Umegae: ...`, `Mitsukuni: ...`) as their own log entries — the parser captures these as `TravelerAbility` rows rather than inlining the bonus on the parent action, otherwise it would double-count.
