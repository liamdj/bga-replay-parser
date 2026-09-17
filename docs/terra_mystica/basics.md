# Terra Mystica Rules Overview (for Parser Development)

2-5 players, 6 rounds. Most Victory Points (VP) wins.

## Factions

Each faction is bound to one terrain type (its "Home terrain") and color.

### Base Game Factions (14)

| Terrain    | Color  | Factions                  |
|------------|--------|---------------------------|
| Plains     | brown  | Halflings, Cultists       |
| Swamp      | black  | Alchemists, Darklings     |
| Forest     | green  | Witches, Auren            |
| Lakes      | blue   | Mermaids, Swarmlings      |
| Mountains  | grey   | Dwarves, Engineers        |
| Wasteland  | red    | Chaos Magicians, Giants            |
| Desert     | yellow | Fakirs, Nomads   |

### Fire & Ice Factions (6)

| Terrain    | Color  | Factions                  | Notes |
|------------|--------|---------------------------|-------|
| Ice        | white  | Ice Maidens, Yetis        | Choose a Starting terrain at faction selection |
| Volcano    | orange | Dragonlords, Acolytes     | Choose a Starting terrain at faction selection |
| Variable   | varies | Shapeshifters             | Choose a Home terrain at faction selection |
| Variable   | varies | Riverwalkers              | Choose a Starting terrain; unlock terrains via Priests |

### Fan Factions (BGA implementation)

| Terrain    | Color  | Factions                  |
|------------|--------|---------------------------|
| Plains     | brown  | Time Travelers, Prospectors (Gold Diggers) |
| Swamp      | black  | Goblins, Children of the Wyrm |
| Forest     | green  | Chash Dallah, The Enlightened |
| Lakes      | blue   | Atlanteans, Wisps         |
| Mountains  | grey   | Conspirators, Dynion Geifr |
| Wasteland  | red    | Architects, Treasurers    |
| Desert     | yellow | Archivists, Djinn         |
| Ice        | white  | Selkies, Snow Shamans     |

| Variable   | varies | Changelings, Geologists   | Fan factions |
| Volcano    | orange | Firewalkers, Kingdom of Ember | Fan factions |

**Parser note**: Skip games with Variable or Volcano factions.

Each faction has a starting ability, a stronghold ability, unique starting resources, and some have unique costs or income. See faction-specific docs for details.

## Terrain

### Base Game Terrains (7)

Plains, Swamp, Lakes, Forest, Mountains, Wasteland, Desert. Arranged in a circular Transformation cycle. Each step costs 1 Spade; shorter direction around the cycle is used.

### Fire & Ice Terrains (2)

- **Ice** (white): Home terrain of Ice Maidens and Yetis. Placed as tiles on the board. Ice cannot ever be transformed into any other terrain type by any faction.
- **Volcano** (orange): Home terrain of Dragonlords and Acolytes. Placed as tiles on the board. Volcanoes cannot ever be transformed into any other terrain type by any faction.

Ice and Volcano factions choose a Starting terrain at faction selection, which determines spade costs relative to the standard Transformation cycle.

## Structures

Building hierarchy (taken left-to-right off faction board):

```
Dwelling → Trading House → Temple → Sanctuary
                         → Stronghold
```

Supply per faction: 8 Dwellings, 4 Trading Houses, 3 Temples, 1 Sanctuary, 1 Stronghold, 3 Bridges

**Power values** (used for opponent adjacency power gains and Town formation threshold):
- Dwelling: 1
- Trading House: 2, Temple: 2
- Stronghold: 3, Sanctuary: 3

Building a Temple or Sanctuary grants a Favor tile.

## Resources

- **Workers**: income from Dwellings
- **Coins**: income from Trading Houses
- **Priests**: income from Temples/Sanctuary; limited to 7 total
- **Power**: 12 tokens across 3 Bowls (I → II → III); spend from Bowl III → Bowl I

### Power Bowls
- Gain Power: move tokens I→II, then II→III
- Spend Power: move tokens from Bowl III to Bowl I
- Sacrifice Power: remove 1 token from Bowl II permanently to move another II→III

### Conversions (any number, anytime during your turn)
- 5 Power → 1 Priest
- 3 Power → 1 Worker
- 1 Power → 1 Coin
- 1 Priest → 1 Worker
- 1 Worker → 1 Coin

## The 8 Actions (Phase II)

Each player takes exactly 1 action per turn:

1. **Transform and Build** — terraform terrain (costs Spades from Workers/Exchange track, Power actions, or Bonus card), optionally build a Dwelling
2. **Advance Shipping** — increases indirect adjacency range across rivers
3. **Advance Exchange Track** — reduces Workers needed per Spade
4. **Upgrade a Structure** — triggers opponent Power gain via adjacency
5. **Send a Priest to a Cult Track** — advance 2 or 3 spaces; space 10 requires a Town key, 1 player per cult
6. **Power Action** — six actions on game board, each usable once per round
7. **Special Action** — from Stronghold, Bonus card, or Favor tile; each once per round
8. **Pass** — return Bonus card, take a new one; some award VP when returned

See specifics doc for costs.

### Turn Order (Variable, standard on BGA)
The order in which players pass determines turn order for the next round. 1st to pass → 1st next round, etc.

## Cult Tracks (Fire, Water, Earth, Air)

- Spaces 0-10 per cult
- Advancing to/past certain spaces gains Power (see specifics for thresholds)
- Space 10 requires a Town key; only 1 player per cult

## Towns

Founded automatically when a group of directly adjacent structures (connected via hex edges or Bridges, not Shipping) has:
- 4+ structures with combined Power value ≥ 7

Benefits: choose a Town tile (one-time VP + resources) and gain a Town key (needed for cult space 10).

## Scoring

### During the Game
- **Scoring tiles** (1 per round): VP for specific actions that round
- **Bonus cards**: some award VP when passing
- **Favor tiles**: some award VP when building
- **Track advances**: VP from Shipping/Exchange track advances
- **Town tiles**: VP from chosen tile

### End-of-Game Scoring
1. **Cult scoring**: 8/4/2 VP for 1st/2nd/3rd highest on each cult track (ties split, round down)
2. **Area scoring**: 18/12/6 VP for largest/2nd/3rd connected area (direct + indirect adjacency; ties split)
3. **Fire & Ice final scoring** (if enabled): additional 18/12/6 VP tile scored after Area scoring (see `terra_mystica_fire_ice_scoring.md`)
4. **Resource scoring**: 1 VP per 3 leftover Coins. Resources may be converted to Coins first.

## Round Structure (6 rounds)

1. **Phase I — Income**: from faction board (structures removed reveal income) + Bonus card + Favor tiles
2. **Phase II — Actions**: players alternate taking 1 action each until all have passed
3. **Phase III — Cult Bonuses & Clean-up**: award cult bonuses from Scoring tile, return Action tokens (no Phase III after round 6)

## Adjacency

**Direct**: share a hex edge, or connected by Bridge across a River

**Indirect**: separated by River spaces, reachable with Shipping value ≥ distance in rivers

Special: Dwarves use Tunneling, Fakirs use Carpet Flight (both count for adjacency/Area scoring instead of Shipping).

## Opponent Power via Structures

When a player builds or upgrades, each opponent with directly adjacent structures may gain Power equal to the total power value of their adjacent buildings. If the gain would require moving tokens out of Bowl I, opponent must pay 1 VP per extra Power gained or decline entirely.

## Game Setup (BGA Standard)

1. Randomly select 7 Scoring tiles and Bonus cards (player count + 3)
2. Faction selection via auction
3. Place initial Dwellings (first→last, then last→first)
4. Choose initial Bonus cards (last→first)

### Faction Auction (Starting VP)

Factions start at equal VP (e.g., 40). Players bid VP to sacrifice for their preferred faction.

**Slow auction (real-time):** Players take turns bidding, able to see and respond to each other's bids.

**Fast auction (turn-based):** All players simultaneously submit secret max bids for every faction. System resolves automatically.

Turn order after auction is tied to factions (each has a predefined position).

### BGA Game Options

- **Game board**: Base Game, Revised Base Game, Fire & Ice, Lakes, Fjords, The Archipelago, Random, Custom, Randomly generated
- **Mini-expansions**: On / Off (adds extra Scoring tile, Bonus cards, Town tiles)
- **Fire and Ice - Final Scoring tiles**: Off / On / Random
- **Fire and Ice - Factions**: Off / On / Random
- **Fan Factions**: Off, On - with Fire & Ice, On - no Fire & Ice
