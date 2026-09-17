# Tokaido — Crossroads Expansion

The Crossroads expansion adds a **second option** at every space type except Inns and Farms-as-coin-stop, plus 6 new Travelers and a Fortune die. Players still must walk the same Tokaido road; the choices at each space simply double up.

`game.has_crossroads = True` is set during parsing if any of these move types appear: `CherryTree`, `BathHouse`, `Calligraphy`, `CalligraphyScored`, `LegendaryObject`, `Amulet`, `AmuletUsed`. Output routes to `*_xroads.csv` instead of `*_base.csv` accordingly.

## Card counts (Crossroads only)

| Card type | Cards |
|-----------|-------|
| Amulets | 6 (one of each effect) |
| Legendary Objects | 6 (3 types × 2 copies) |
| Bathhouses | 6 (identical, 4 VP each) |
| Calligraphies | 6 (one of each effect) |
| Cherry Trees | 6 (identical, 2 VP + 1 coin each) |
| Fortune die | 1 (six faces: X, x1, x2, x3, x4, X — the rulebook lists 5 results, BGA implements 6) |

Game variants:
- 2–3p: only **4** of each card type, randomly selected (BGA uses these defaults).
- 4–5p: **5** of each.
- "Good luck" optional rule: each player may pay 1 coin at start to draw a random Amulet.

## New options at each space type

### Panorama → Cherry Tree

When stopping on a Sea/Mountain/Field space, choose:
- Take next-numbered Panorama card (base rule), OR
- Take a **Cherry Tree** card (if available): **2 VP + 1 coin**.

Cherry Trees do NOT count toward Panorama Achievements (no completion-style scoring). No limit on how many Cherry Trees a player can hold.

### Hot Spring → Bathhouse

Choose:
- Draw Hot Spring card (base, 2–3 VP), OR
- Pay 1 coin for a **Bathhouse card**: **4 VP**.

Bathhouses count as Hot Springs for the **Bather** achievement.

### Farm → Gaming Room

Choose:
- Take 3 coins (base), OR
- Gamble in the **Gaming Room**: bet 2 coins, roll the Fortune die. Result multiplier:
  - `X` → lose the bet (2 coins to bank)
  - `x1` → recover the bet (net 0)
  - `x2` → +2 coins
  - `x3` → +4 coins
  - `x4` → +6 coins

Win/loss coins go to/from the bank.

### Temple → Amulet

Choose:
- Donate 1/2/3 coins to the Temple (base), OR
- Pay 1 coin to the bank to draw any 1 available **Amulet card**.

Amulet purchase pays the bank, **not the Temple track** — so it does not count toward Temple donation ranking. Amulets are kept secret from opponents until used. After use, the card returns to its stack and may be drawn again later. A Traveler can hold multiple Amulets simultaneously.

**Important**: An Amulet bought this turn cannot be used this turn — earliest use is the Traveler's next move.

### Shop / Village → Legendary Object

Choose:
- Buy Souvenirs (base), OR
- Buy ONE **Legendary Object** (if available) for 1, 2, or 3 coins (printed on card).

Legendary Objects count toward the **Collector** achievement.

### Encounter → Calligraphy

Choose:
- Draw Encounter card (base), OR
- Pay 1 coin to the bank for any 1 available **Calligraphy card**.

Calligraphies count toward the **Chatterbox** achievement.

## Amulet cards (single-use, secret)

| Amulet | Effect |
|--------|--------|
| **Vitality** | After your move, if you became the lead Traveler, play another move immediately. Cannot use when arriving at an Inn. |
| **Fortune** | Roll the Fortune die before moving; gain 0/1/2/3/4 coins (X=0, x1=1, x2=2, x3=3, x4=4). |
| **Health** | Resolve **both** options of the space you stop on, in order of your choice. Cannot use at an Inn. |
| **Friendship** | Treat a single space occupied by another Traveler as a double space (place yourself adjacent). The single space MUST be occupied. The user of the Amulet leaves first. |
| **Hospitality** | Take a Meal card free of charge at the next Inn. |
| **Devotion** | When buying a purchasable card (Souvenir, Meal, Legendary Object, Bathhouse, Calligraphy, or another Amulet), the spent coins go to the **Temple** instead of the bank. Score 1 VP per coin (just like a Temple donation). The coins also count for end-game Temple ranking. |

Amulet `type_arg` mapping in `tokaido_constants.AMULET_TYPE`.

### Parser routing for donation Amulets

- **Miko** encounter VP and **Devotion** amulet VP both go to `vp_temple` because the player materially donated to the temple. `num_donations` is incremented in both cases. But Miko still increments `num_encounters` and Devotion still increments `num_amulets_used`.
- There is no separate `vp_amulet_used` column — Devotion is the only amulet that scores VP, and that VP is accounted as Temple VP.

## Legendary Objects (6 cards, 3 types)

| Object | Effect |
|--------|--------|
| **Shodo** & **Emaki** (script) | When acquired: 1 VP per other Souvenir/Legendary in your collection. Then 1 VP per *additional* Souvenir/Legendary acquired afterward. |
| **Buppatsu** & **Ema** (offering) | Counts as a *new family* of Souvenir. Goes into your Souvenir set scoring as a 5th family. A complete 5-family set: 1+3+5+7+9 = 25 VP. |
| **Murasame** & **Masamune** (sword) | Flat 8 VP each. |

A Traveler can own both objects of a single type.

Type mapping in `tokaido_constants.LEGENDARY_OBJECT_TYPE`.

Parser stores per-type: `vp_legendary_script`, `vp_legendary_offering`, `vp_legendary_sword` and `num_legendary_*`.

## Calligraphy cards (6 cards, 6 distinct end-game scoring effects)

| Card | End-game VP |
|------|-------------|
| **Foresight** | 2 VP per coin remaining at game end |
| **Contemplation** | 3 VP per *complete* Panorama, +1 VP per Cherry Tree |
| **Nostalgia** | 2 VP per Legendary Object, +1 VP per Souvenir |
| **Patience** | 6 VP if last to arrive at the final Inn, 4 VP if 2nd-last, 2 VP otherwise |
| **Perfection** | 2 VP per Achievement card, +1 VP per Calligraphy card (Perfection counts itself) |
| **Fasting** | 3 VP per *uneaten* Meal (max 4 Inn-meals available) |

A Traveler may hold several Calligraphy cards. Type mapping in `tokaido_constants.CALLIGRAPHY_TYPE_ARG_TO_NAME`.

Parser tracks ownership in `has_calligraphy_<name>` bools and total scored VP in `vp_calligraphy`. The `CalligraphyScored` move type fires at end-of-game when each card pays out — joinable to the buy event via `calligraphy_card_type`.

## Encounter ↔ Crossroads cards

The base Encounter card effects do NOT extend to Crossroads cards:
- Annaibito (Guide) does not award a Cherry Tree.
- Miko (Priest) cannot purchase an Amulet — its 1 free coin still goes to a regular Temple donation.
- Shokunin (Merchant) does not award a Legendary Object.

## Move types added by Crossroads

In the `type` column of `moves_xroads.csv`:

| Move type | Source |
|-----------|--------|
| `CherryTree` | Take Cherry Tree (alt panorama) |
| `BathHouse` | Buy Bathhouse (alt hot spring) |
| `Calligraphy` | Buy Calligraphy at Encounter |
| `CalligraphyScored` | End-game payout per held Calligraphy |
| `LegendaryObject` | Buy Legendary Object at Village/Shop |
| `Amulet` | Buy Amulet at Temple |
| `AmuletUsed` | Activate held Amulet |
| `Gaming` | Use Farm's Gaming Room |
| `JirochoGaming` | Jirocho's free Inn-arrival gamble (see Travelers doc) |
| `LegendBonus` | "${legend}: ..." event lines (free-form Crossroads narration → `vp_legend_bonus`) |
