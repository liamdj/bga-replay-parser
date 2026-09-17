# Terra Mystica Specifics Reference

Detailed costs, tiles, and component data for parser development. Faction-specific details are in separate docs.

## Buildings (Standard Costs & Income)

Income is gained each round from structures removed from the faction board (left-to-right).

### Dwelling — cost: 1w+2c
| Slot | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|------|---|---|---|---|---|---|---|---|
| Income | 1w | 1w | 1w | 1w | 1w | 1w | 1w | — |

### Trading House — cost: 2w+3c (6c if not directly adjacent to opponent)
| Slot | 1 | 2 | 3 | 4 |
|------|---|---|---|---|
| Income | 2c+1pw | 2c+1pw | 2c+2pw | 2c+2pw |

### Temple — cost: 2w+5c — grants 1 Favor tile
| Slot | 1 | 2 | 3 |
|------|---|---|---|
| Income | 1p | 1p | 1p |

### Sanctuary — cost: 4w+6c — grants 1 Favor tile
| Slot | 1 |
|------|---|
| Income | 1p |

### Stronghold — cost: 4w+6c
Income and ability vary by faction.

## Power Actions

| Action    | Power Cost | Effect       |
|-----------|------------|--------------|
| Bridge    | 3          | 1 Bridge     |
| Priest    | 3          | 1 Priest     |
| Workers   | 4          | 2 Workers    |
| Coins     | 4          | 7 Coins      |
| Single Spade   | 4          | 1 Spade      |
| Double Spade  | 6          | 2 Spades     |

Each usable once per round (first come, first served).

## Shipping Track

| Level | VP Gained | Cost              |
|-------|-----------|-------------------|
| 0→1   | 2 VP      | 1p + 4c           |
| 1→2   | 3 VP      | 1p + 4c           |
| 2→3   | 4 VP      | 1p + 4c           |

Mermaids are the only faction that can advance shipping beyond 3.

Dwarves and Fakirs cannot advance Shipping (they use Tunneling/Carpet Flight instead).

## Exchange Track (Spade cost in Workers)

| Level | Workers per Spade | VP for advancing | Cost to advance    |
|-------|-------------------|------------------|--------------------|
| 0     | 3w/Spade          | —                | —                  |
| 1     | 2w/Spade          | 6 VP             | 2w + 5c + 1p      |
| 2     | 1w/Spade          | 6 VP             | 2w + 5c + 1p      |

## Terrain Transformation Cycle

```
Plains → Swamp → Lakes → Forest → Mountains → Wasteland → Desert → Plains
```

Each step costs 1 Spade. Transforming goes either direction around the cycle; the shorter path is used.

Steps between terrains:
| From\To    | Plains | Swamp | Lakes | Forest | Mountains | Wasteland | Desert |
|------------|--------|-------|-------|--------|-----------|-----------|--------|
| Plains     | 0      | 1     | 2     | 3      | 3         | 2         | 1      |
| Swamp      | 1      | 0     | 1     | 2      | 3         | 3         | 2      |
| Lakes      | 2      | 1     | 0     | 1      | 2         | 3         | 3      |
| Forest     | 3      | 2     | 1     | 0      | 1         | 2         | 3      |
| Mountains  | 3      | 3     | 2     | 1      | 0         | 1         | 2      |
| Wasteland  | 2      | 3     | 3     | 2      | 1         | 0         | 1      |
| Desert     | 1      | 2     | 3     | 3      | 2         | 1         | 0      |

Ice and Volcano are outside this cycle and cannot be transformed into or from other terrains by non-Ice/Volcano factions.

## Favor Tiles (12 total)

Gained when building Temple or Sanctuary. Chaos Magicians get 2 per Temple/Sanctuary.

| Favor Tile | Ability                                              |
|------------|------------------------------------------------------|
| Fire +3    | —                                                    |
| Fire +2    | -1 structure power to found Town (7 → 6 needed)     |
| Fire +1    | 3c income                                            |
| Water +3   | —                                                    |
| Water +2   | Advance 1 on any cult (special action)               |
| Water +1   | +3 VP when buildng Trading House                         |
| Earth +3   | —                                                    |
| Earth +2   | 1w+1pw income                                        |
| Earth +1   | +2 VP when building Dwelling                             |
| Air +3     | —                                                    |
| Air +2     | 4pw income                                           |
| Air +1     | Pass for 2/3/3/4 VP for 1/2/3/4 TP built             |

## Scoring Tiles (9 total incl. mini expansion, 6 used per game)

Each tile has two halves: left side awards VP during the Action phase, right side grants resources during Phase III based on cult progress.

| Left (Action phase)  | Right (Phase III cult bonus)           |
|----------------------|----------------------------------------|
| 2 VP/Dwelling        | per 4 Fire → 4pw                       |
| 5 VP/SH or SA        | per 2 Fire → 1w                        |
| 2 VP/Dwelling        | per 4 Water → 1p                       |
| 3 VP/Trading House   | per 4 Water → 1 Spade                  |
| 5 VP/Town            | per 4 Earth → 1 Spade                  |
| 2 VP/Spade*          | per 1 Earth → 1c                       |
| 3 VP/Trading House   | per 4 Air → 1 Spade                    |
| 5 VP/SH or SA        | per 2 Air → 1w                         |
| 4 VP/Temple (mini)   | per Priest on Cult Board → 2c          |

*Spade scoring tile cannot be placed in rounds 5 or 6.

## Bonus Cards (10 total incl. mini expansion)

Number available per game: player count + 3 (2p=5, 3p=6, 4p=7, 5p=8).

| Name           | Income                |  Bonus              |
|----------------------|-----------------------|----------------------------|
| priest            | 1p              | —                          |
| worker power            | 1w, 3pw     | —                          |
| coins             | 6c               | —                          |
| shipping        | 3pw               | 3 VP per Shipping level (mini expansion) |
| spade           | 2c               | 1 free Spade (special action) |
| cult coins            | 4c               | Advance 1 on any cult (special action) |
| dwelling       | 2c               | 1 VP per Dwelling on board when passing |
| trading post     | 1w              | 2 VP per Trading House on board when passing |
| big building   | 2w                     | 4 VP per Stronghold/Sanctuary on board when passing |
| temp ship  | 3pw              | Temporarily increase shipping range by 1 |

## Town Tiles (14 total)

Each provides 1 Town Key (allows advancing to space 10 on any cult track) unless noted.

| Town Tile       | Qty | Bonus                                                                      |
|-----------------|-----|----------------------------------------------------------------------------|
| 11 VP           | ×1  | 11 VP (mini exp.)                                                          |
| 9 VP + Priest   | ×2  | 9 VP + 1p                                                                  |
| 8 VP + Cults    | ×2  | 8 VP + advance 1 on all 4 cult tracks                                      |
| 7 VP + Workers  | ×2  | 7 VP + 2w                                                                  |
| 6 VP + Power    | ×2  | 6 VP + 8pw                                                                 |
| 5 VP + Coins    | ×2  | 5 VP + 6c                                                                  |
| 4 VP + Ship     | ×2  | 4 VP + advance 1 Shipping (gain VP). Fakirs: +1 Carpet Flight range (mini exp.) |
| 2 VP + Cults×2  | ×1  | 2 VP + advance 2 on all 4 cults + provides 2 Town Keys total (mini exp.)   |

## Cult Track Power Thresholds

| Space reached | Power gained |
|---------------|-------------|
| 3             | 1           |
| 5             | 2           |
| 7             | 2           |
| 10            | 3           |
