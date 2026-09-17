# BGA Terra Mystica Replay Format Reference

Based on analysis of tables 762552045 (Fire & Ice, fast auction), 791779890 (Base Game, fast auction w/ fan factions), 606358758 (Base Game, slow auction), and bulk analysis of 419 replays in data/batch/terra_mystica/replays/.

## Replays to Skip

**Skip any replay where any player uses an excluded faction:**
- Variable factions: `shapeshifters`, `riverwalkers`, `changelings`, `geologists`
- Volcano factions: `dragonlords`, `acolytes`, `firewalkers`, `kingdomofember`

**Skip any replay using unsupported settings:**
- Landscapes expansion: On or Random (detected via `landscapePlaced` event type or table page settings)
- Non-standard maps: skip all except "Base Game", "Fjords", "Fire & Ice" boards

Detection: faction names appear as `"type":"<faction_name>"` entries in g_gamelogs. Check for excluded faction types before parsing. Landscape games can be detected by presence of `landscapePlaced` event type.

## g_gamelogs Structure

```
g_gamelogs = {
  "status": 1,
  "data": {
    "valid": 1,
    "data": [ ...packets... ]
  }
};
```

Each **packet** has:
- `channel`, `table_id`, `packet_id`, `packet_type`, `move_id`, `time`
- `data`: array of log entries

Each **log entry** has:
- `uid`: unique ID
- `type`: event type string
- `log`: template string with `${var}` placeholders
- `args`: dict with template values + structured game data
- `h`: optional hash (present on some entries)

## Event Types

### Setup Events
- `justAMessage` — game settings, phase announcements, misc messages
- `factionPositionSelected` — player selects faction and position
- `factionBoardSwapped` — faction boards assigned after auction
- `factionBoardChosen` — all factions finalized
- `updateScoreSmallDelay` — starting VP announcement
- `startingTerrainChosen` — Ice/Volcano/Variable faction picks starting terrain (appears in all games on updated BGA client)
- `terrainRingUpdated` — transformation cycle ring position updated (Ice/Shapeshifter ring)
- `addNewBonusCard` — extra bonus card added (Archivists setup)

### Resource/State Tracking
- `gameStateChange` — state machine transitions (has inner `args` with board state)
- `updateCounters` — resource counters for all players
- `updateScore` — VP change for a player
- `updateReflexionTime` — thinking time updates
- `gameStateMultipleActiveUpdate` — multiple players active simultaneously
- `updateExchangeTrack` — exchange track state update (visual sync event)
- `newPowerTokens` — power tokens added to a player's bowls (e.g., Enlightened buying tokens)
- `updateTreasury` — Treasurers treasury resource update
- `emptyTreasury` — Treasurers treasury emptied (doubled resources returned)

### Actions
- `terrainTransformed` — terraform action
- `dwellingPlaced` — build dwelling
- `structureUpgraded` — upgrade building (DW→TH, TH→TE/SH, TE→SA)
- `advanceCultTrack` — advance on a cult track
- `orderAPriest` — send priest to cult order
- `advanceShippingTrack` — advance shipping
- `advanceExchangeTrack` — advance spade exchange rate
- `advanceIncomeTrack` — Chash Dallah advances income track
- `powerActionConvert` — use power action (spades, workers, coins)
- `powerActionBridge` — use power action to build bridge
- `conversionsApplied` — resource conversions
- `conversionsAppliedWithDelay` — conversions during final scoring
- `specialActionUsed` — stronghold/favor/bonus special action
- `actionUsed` — marks a power/special action as used
- `powerIncome` — faction ability power gain (e.g., Prospectors get +1 Power when digging)
- `swapCultTrack` — Djinn swaps two cult markers via Magic Lamp
- `favorTileLost` — Conspirators return a Favor tile (cult marker moves down)
- `tokenPlaced` — generic token placement (Treasure tokens for Goblins, etc.)

### Town & Scoring
- `townFounded` — town founded
- `townBonus` — town tile bonus received
- `favorTileChosen` — favor tile selected
- `bonusCardChosen` — bonus card selected
- `tileScored` — scoring tile bonus
- `finalScoring` — end-game scoring entries

### Phase Events
- `incomePhase` — start of income phase
- `someIncome` — individual income details
- `coinsOnBonusCards` — leftover bonus cards get coins
- `playerPassed` — player passes
- `firstPlayerChanged` — first player to pass
- `returnActionTokens` — cleanup phase
- `undoRestoreDISAB` — undo tracking
- `wakeupPlayers` — wake players for new round (base game replays)

### Resource Gain/Cost Events (new in updated BGA client)
- `powerViaStructures` — explicit power gain/decline from opponent building (was previously only in log templates)
- `someCost` — resource cost paid for an action
- `gainRessources` — generic resource gain event
- `gainPriests` — priest(s) gained
- `workersForPriests` — workers exchanged for priests (Prospectors: spades → priests)
- `workersIncome` — workers received as income
- `createSomeWorkers` — workers created/gained
- `createLandBridges` — bridges created (base game, landscape games)

### Misc
- `timeJokerUsed` — player uses holiday time joker (turn-based games)
- `simpleNote` — informational message (similar to justAMessage)
- `newCustomBoard` — custom/random board layout

### Excluded Faction Events (skip games with these)
- `shapeshifted` — Shapeshifters change home terrain
- `priestFromTerrainCycle` — Riverwalkers unlock terrain
- `lavaAdded` — Volcano tile placed (Dragonlords, Acolytes, Kingdom of Ember, Firewalkers)
- `lavaFlow` — Kingdom of Ember lava flow movement
- `landscapePlaced` — Landscapes expansion tile placed

### End
- `simpleNode` — "End of game : ${player_name} wins!"

## Key Args Fields by Event Type

### terrainTransformed
```json
{
  "player_id": "84208794",
  "player_name": "Redrame",
  "extra": " [G6]",        // hex coordinate
  "bts_id": "G7",           // board tile space ID
  "orig": "<div ...>",      // HTML icon for original terrain
  "dest": "<div ...>",      // HTML icon for destination terrain
  "terrain_dest": "...",
  "spades_used": "...",
  "transform_cost": "...",
  "other_cost": "..."
}
```

### dwellingPlaced
```json
{
  "player_id": "...",
  "extra": " [E3]",         // hex coordinate
  "bts_id": "E3",
  "workers_cost": "<div ...workers_amount'>1</div>...",
  "coins_cost": "<div ...coins_amount'>2</div>..."
}
```

### structureUpgraded
```json
{
  "player_id": "...",
  "extra": " [G7]",
  "old_struct": {
    "struct_id": "52",
    "struct_type": "dwelling",    // dwelling, tradinghouse, temple, stronghold, sanctuary
    "struct_color": "red"
  },
  "new_struct": {
    "struct_id": "60",
    "struct_type": "tradinghouse",
    "struct_color": "red"
  },
  "old_struct_name": "Dwelling",
  "new_struct_name": "Trading house",
  "resource_cost": "<div ...>"
}
```

### advanceCultTrack
```json
{
  "player_id": "...",
  "cult_id": "2",            // 1=fire, 2=water, 3=earth, 4=air
  "cult_name": "Cult of Water",
  "initial_pos": "1",
  "final_pos": 4
}
```

### orderAPriest
```json
{
  "player_id": "...",
  "cult_id": "2",
  "cult_name": "Cult of Water",
  "order_space_id": "1",
  "lose_priest": true,
  "player": {
    "player_aircult": "0",
    "player_firecult": "0",
    "player_earthcult": "1",
    "player_watercult": "1"
  }
}
```

### favorTileChosen
```json
{
  "player_id": "...",
  "favor_id": "19",
  "favor_type": "9"
}
```

### bonusCardChosen
```json
{
  "player_id": "...",
  "bonus_id": "2",
  "bonus_id_2": "0",
  "nb_bonus_card": 1,
  "coins_gain": "<div ...>"
}
```

### townFounded
```json
{
  "player_id": "...",
  "extra": " [E4]",
  "bts_id": "E8",
  "town_id": "10"
}
```

### townBonus
```json
{
  "player_id": "...",
  "player": {
    "player_score": "58",
    "player_coins": "6",
    "player_earthcult": "0",
    "player_firecult": "2",
    "player_watercult": "0",
    "player_aircult": "4"
  },
  "score_inc": "<div ...vp_amount'>5</div>...",
  "coins_income": "...",
  "workers_income": "...",
  "priests_income": "..."
}
```

### updateCounters
```json
{
  "counters": {
    "<player_id>": {
      "coins_count": "19",
      "spades_count": "0",
      "power1_count": "4",    // Bowl I
      "power2_count": "8",    // Bowl II
      "power3_count": "0",    // Bowl III
      "tokens_count": null,
      "ak": 0,                // unknown
      "sc": "0",              // unknown
      "sdc": "-",             // unknown (or number)
      "icc": 0,               // income coins count?
      "ipc": 0,               // income priests count?
      "iwc": 3,               // income workers count?
      "iptc": 0               // income power tokens count?
    }
  }
}
```

### updateScore
```json
{
  "player_id": "84208794",
  "player_name": "Redrame",
  "score_inc": "<div ...vp_amount'>3</div>...",
  "newScore": "43",
  "score_delta": 3,
  "scoring_node": "scoring_tile_holder_1"
}
```

### finalScoring
```json
{
  "player_id": 92703186,
  "player_name": "_Yotsuba_",
  "score_inc": "<div ...vp_amount'>8</div>...",
  "score_delta": 8,
  "newScore": 115,
  "scoring_node": "firecult_token_92703186"
  // or: "connected_number": "15", "connected_scoring_type": "connected Structures (Area scoring)"
  // or: "coins_number": "<div ...>", scoring for resources
}
```

### powerViaStructures
Log templates:
- `${player_name} gets ${power_income} via Structures ${extra}` (accepted freely)
- `${player_name} pays ${vp_price} and gets ${power_income} via Structures ${extra}` (paid VP)
- `${player_name} declines getting Power via Structures ${extra}` (declined)

### Auction bids (justAMessage)

One event per bid, `log` = `${player_name} bids on the ${faction_name} with ${starting_vp} Starting VP(s)`. Args: `player_id`, `player_name`, `faction_type`, `starting_vp`. Two formats:

- **Fast auction** (sealed, simultaneous): every player bids once on every faction. `starting_vp` is HTML — `<div class='tmlogs_icon' title='VP'><div class='vp_amount'>40</div></div>`. Resolves as an assignment, so a seat's final starting VP can differ from its own winning bid.
- **Slow / standard auction** (ascending, turn by turn): `starting_vp` is a plain integer string (`'39'`). A player can bid the same faction repeatedly as they are outbid; lower starting VP = higher bid. Followed by `${player_name} has not been outbid for Faction ${faction_name} and is skipping` and `~ The Factions auction is over ~`.

The winning price is confirmed by `updateScoreSmallDelay`: `${player_name} is playing the ${faction_name} Faction (with ${starting_vp} ...)`.

**Detecting auction games:** use the presence of bid events. gamedatas `with_auction` (and `auctioned_factions`) is absent on most pre-2023 games, and the table-page "Starting VP" option files ~12k 2020–22 slow auctions under "Adjusted by Faction" (see below).

## Table Page Game Settings

Settings are in `<div class="row-data">` elements containing `<div class="gameoption_description">`.
Parent text contains label + selected value. Key settings:

- **Game board**: "Base Game", "Revised Base Game", "Fire & Ice", "Lakes", "Fjords", "The Archipelago", "Random", "Custom", "Randomly generated"
- **River template**: "Base Game", "Fire & Ice", etc.
- **Faction board**: "Factions selected in player order", "Random Faction selection", "Introductory game"
- **Starting VP**: "Standard", "Adjusted by Faction", "Standard auction", "Fast auction" — **unreliable before 2023**: most games labelled "Adjusted by Faction" in 2020–22 contain real auction bidding. Trust "Standard auction"/"Fast auction", and anything 2023+.
- **Turn order**: "Clockwise from the first player", "Variable turn order"
- **Mini-expansions**: "On" / "Off"
- **Landscapes expansion**: "Off" / "On" / "Random" — **SKIP if On or Random**
- **Fire and Ice - Final Scoring tiles**: "Off" / "On" / "Random"
- **Fire and Ice - Factions**: "Off" / "On" / "Random"
- **Fan Factions**: "Off", "On - with Fire & Ice", "On - no Fire & Ice"
- **Game mode**: "Normal mode", "Friendly mode"
- **Game speed**: "Turn-based • 2 moves per day", "Real-time • Normal speed", etc.

### Supported Maps (all others should be skipped)
- "Base Game"
- "Fjords"
- "Fire & Ice"

## Game Flow in Replay

1. **Setup**: justAMessage (board, settings) → factionPositionSelected × N → auction bids → factionBoardSwapped/Chosen → startingTerrainChosen (if Ice/Variable factions) → dwellingPlaced (initial) → bonusCardChosen
2. **Each Round**: incomePhase → someIncome × N → coinsOnBonusCards → "Action phase" message → player actions (transform, build, upgrade, cult, pass...) → playerPassed × N → returnActionTokens → tileScored
3. **Final Round**: last actions → all pass → "Final scoring" → finalScoring (cults × 4, area, F&I final scoring if enabled, resources) → simpleNode (winner)

## HTML Resource Icons

Resource amounts are embedded as HTML in args:
```html
<div class='tmlogs_icon' title='VP'><div class='vp_amount'>8</div></div>
<div class='tmlogs_icon' title='Workers'><div class='workers_amount'>1</div></div>
<div class='tmlogs_icon' title='Coins'><div class='coins_amount'>2</div></div>
<div class='tmlogs_icon' title='Priests'><div class='priests_amount'>1</div></div>
<div class='tmlogs_icon' title='Power'><div class='power_amount'>3</div></div>
```

Terrain icons:
```html
<div class='tmlogs_icon' title='swamp'><div class='trans_swamp'>&nbsp;</div></div>
```
Terrain types: plains, swamp, forest, lakes, mountains, wasteland, desert, ice, volcano

## Hex Coordinates

Format: `[A-I][1-13]` (letter = column, number = row). Shown in `extra` field as ` [E3]`.
The `bts_id` field also contains hex coordinates but sometimes differs (board tile space mapping).
