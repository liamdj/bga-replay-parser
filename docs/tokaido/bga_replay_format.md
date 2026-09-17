# BGA Tokaido Replay Format Reference

Based on the 33,708 replays parsed from `data/batch/tokaido/raw/` (base game + Crossroads expansion).

## Raw format

Tokaido replays are stored as the JSON output of the BGA archive API:

```
GET /archive/archive/logs.html?table=<id>&translated=true
-> { "data": { "logs": [ ...packets... ] } }
```

`scrape_raw_replay.py --raw-format json` saves `<table_id>.json` containing **just the inner `data.logs` array** — a flat list of packets. The parser also accepts the dict-wrapped form (`{"data": {"data": [...packets...]}}`) found inside `g_gamelogs = ...;` in HTML replays.

This is cheaper than scraping the full replay HTML because Tokaido's parser doesn't need the static `gameui.completesetup(...)` gamedatas — every per-game setting and per-player setup the parser cares about is in the gamelogs.

## Packet / event structure

Each **packet**:
- `channel`, `table_id`, `packet_id`, `packet_type`, `move_id`, `time`
- `data`: array of events

Each **event**:
- `uid`: unique ID
- `type`: event type string (`travelerChosen`, `cardsEarned`, `coinsOrPointsEarned`, `message`, `gameStateChange`, ...)
- `log`: template string with `${var}` placeholders, or `""` for state-change events
- `args`: dict with template values + structured game data

The parser dispatches on **`event.log`** (the template string), not `event.type`. The same `type` is used for many different actions; the log template uniquely identifies what happened.

## Replays to skip

`TokaidoParser.should_skip(packets)` returns a reason string for:

- **Fewer than 3 players** — 2p Tokaido has different rules; the parser was written for 3p+. Detected by counting `travelerChosen` events.
- **Preparations expansion** — detected via any event whose log contains both `"Preparation"` and `"${player_name}"`. Seasons 22-23 use it; not handled.

Crossroads is detected per-game by the presence of any `CherryTree`/`BathHouse`/`Calligraphy`/`CalligraphyScored`/`LegendaryObject`/`Amulet`/`AmuletUsed` move row, and sets `game.has_crossroads`. The batch parser writes Crossroads games to a separate CSV from base games.

## Game setup

### Traveler selection

```
type: "travelerChosen"
log:  "${player_name} travels as ${name} ${nametr}"
args: {
  player_id, player_name, player_color, traveler, name, nametr,
  player_position, player_position_order,
  counters: { player_coins_<pid>: { counter_value: "<starting_coins>" }, ... }
}
```

The `traveler` arg is the canonical short name used throughout the parser: `satsuki`, `hirotada`, `yoshiyasu`, `kinko`, `umegae`, `chuubei`, `mitsukuni`, `zenemon`, `sasayakko`, `hiroshige`, `miyataka`, `jirocho`, `kita`, `daigoro`, `gotozaemon`, `nampo`. (16 distinct travelers across base + Crossroads).

`player_position_order` is the seat order (1..N). The `player_coins` counter visible on this event is the player's **starting coin amount** for their character — varies from 0 (gotozaemon) to 9 (yoshiyasu).

### Final result

The end-of-game scoring block sits in a `gameStateChange` event whose `args.args.result` contains one entry per player:

```
args.args.result = [
  {
    player: "<pid>", name, score: "<int>", score_aux: "<achievements>",
    rank: <1..N>, zombie: 0/1, concede: 0/1, tie: True/False, stats: {...}
  },
  ...
]
```

`score_aux` is the BGA tiebreaker — for Tokaido this is the achievements count (number of `cardsEarned` events with `achievement` arg the player earned).

The `stats` dict has numeric keys (e.g. `"10"`, `"22"`) — these are BGA-internal counters and not documented; the parser ignores them.

## Action events

For each event type below, the parser produces a row in `TokaidoMove` with `points_gained` / `coins_*` populated, then `_apply_move_to_player` accumulates them into the matching `TokaidoPlayerResult` columns.

### Movement

```
log:  "${player_name} travels and gets to a new stop (${name})"
args: { position, position_order, name }
```
The `position` field (numeric string `"2"` … `"55"`) maps to a road space like `Village_2`, `Temple_3`, etc. via `tokaido_constants.POSITION_TO_SPACE`. `name` is the localized space type ("Village", "Inn", "Mountain panorama", …).

### Village (souvenirs)

```
log:  "${player_name} buys ${count} souvenir(s) for ${coins} coin(s) and scores ${points} point(s)"
args: { count, coins, points, cards: { id: {type:"souvenir", type_arg:"0..23"} } }
```

`coins` is the **discounted** total — BGA already subtracts Sasayakko's "free cheapest" and any other discount. Each `cards.<id>.type_arg` maps to a souvenir category via `SOUVENIR_TYPE_ARG_TO_CATEGORY` (food / clothing / trinket / art).

A "skipped" purchase fires `${player_name} doesn\`t buy any Souvenir`.

### Temple

```
log:  "${player_name} gives ${coins} coin(s) to the Temple and earns ${points} point(s)"
args: { coins, points }

# End-game ranking (1st=10, 2nd=7, 3rd=4, 4th=2):
log:  "${player_name} earns ${points} points for his donations to the Temple"
args: { points }
```

### Hot Spring

```
log:  "${player_name} scores ${points} points (Hot spring)"
args: { points }
```

### Panorama (3 colors: mountain / sea / field)

```
log:  "${player_name} scores ${points} points (Panorama)"
args: { points, cards: [{ type: "mountain"|"sea"|"field" }] }
```

The `cards[0].type` gives the panorama color (capitalize → "Mountain"/"Sea"/"Field"). The parser routes VP and count into per-color player-result columns.

Completing a panorama first emits:

```
log:  "${player_name} is the first to finish the ${panorama_type} and scores ${points} points (Achievement)"
args: { points: 3, panorama_type: "Mountain panorama"|"Sea panorama"|"Field panorama" }
```

This sets `first_to_finish_mountain/sea/field` bools on the player result.

### Inn (meals)

```
log:  "${player_name} pays ${coins} coins for a meal (${name}) and scores ${points} points"
args: { coins, points, name: "Dango"|"Sushi"|... }

# Skip:
log:  "${player_name} skips a meal"
```

`coins` is the **paid** amount — Kinko's −1 discount and Hospitality Amulet free-meal are already baked in (often `coins:0`). See `tokaido_constants.MEAL_COST` for retail prices (Nampo's VP bonus uses retail cost).

### Farm

```
log:  "${player_name} earns 3 coins (Farm)"
```

### Encounters

```
log:  "${player_name} earns 3 coins (Kuge)"                                           # coins
log:  "${player_name} earns 3 points (Samourai)"                                      # points
log:  "${player_name} gives 1 coin (from the bank) to the Temple and earns 1 point (Miko)"
log:  "${player_name} gets a panorama card and scores ${points} points (Annaibito)"   # picks panorama color
log:  "${player_name} gets a souvenir card and earns ${points} points (Shokunin)"     # picks souvenir
```

**Important quirk**: Miko is a *bank-funded* temple donation. The coin comes from the bank, not the player's purse. The parser sets `coins_gained=1, coins_donated=1` so the player-purse model `gained − spent − donated` nets to 0 (no actual purse change), but `num_donations` still increments for temple-rank purposes.

### Achievements (souvenir-set + panorama bonus)

```
log:  "${player_name} earns an achievement card (${achievement}) and scores 3 points"
args: { points: 3, achievement: "Collector"|"Bather"|"Chatterbox"|... }
```

### Crossroads — Cherry Tree

```
log:  "${player_name} earns 1 coin and scores 2 points (Cherry Tree)"
```

### Crossroads — Bath House

```
log:  "${player_name} pays ${coins} coin and scores ${points} points (Bath House)"
```

### Crossroads — Legendary Object

```
log:  "${player_name} buys a Legendary Object (${name}) for ${coins} coin(s) and scores ${points} point(s)"
log:  "${player_name} buys a Legendary Object (${name}) for ${coins} coin(s)"     # offering type — no immediate VP
log:  "${player_name} doesn\`t buy any Legendary Object"
args: { coins, points?, cards: [{type:"legendary", type_arg:"0..5"}] }
```

`type_arg` maps to a category via `LEGENDARY_OBJECT_TYPE`:
- `0` Shodo, `1` Emaki → **script**
- `2` Buppatsu, `3` Ema → **offering** (no immediate VP, scores at end-game via LegendBonus)
- `4` Murasame, `5` Masamune → **sword**

The parser routes VP and count into `vp_legendary_{script,offering,sword}` and `num_legendary_{script,offering,sword}`.

```
# Periodic legendary scoring (e.g. Murasame's per-Sea-space trigger):
log:  "${legend_name}: ${player_name} earns ${points} bonus point(s)"
args: { legend_name, points }
```

### Crossroads — Gaming Room

```
log:  "${player_name} bets 2 coins and wins ${won}, and so earns ${coins} coins (Gaming Room)"
args: { won, coins }    # coins = NET gain (won - 2), NOT gross

log:  "${player_name} bets 2 coins and loses the money (Gaming Room)"
```

**Quirk**: `args.coins` is the *net* gain (won − bet), so we use `args.won` for `coins_gained` and `coins_spent=2` for the bet. Same applies to Jirocho's traveler-ability gambling.

### Crossroads — Amulets

Purchase:

```
log:  "${player_name} buys an Amulet for ${coins} coin(s)"
args: { coins, cards: {id: {type:"amulet", type_arg:"0..5"}} }

log:  "${player_name} doesn\`t buy any Amulet"
```

`type_arg` → name (from `AMULET_TYPE`, derived empirically — 1000-game elimination on single-amulet owners):
- `0` vitality, `1` fortune, `2` health, `3` friendship, `4` hospitality, `5` devotion

Use (only one of six amulets emits a separate effect log):

```
log:  "Devotion Amulet: ${player_name} gives ${amount} spent coin(s) to the Temple (instead of the bank) and earns ${points} point(s)"
log:  "Friendship Amulet: ${player_name} shares a single space with another Traveler"
log:  "Health Amulet: ${player_name} can use both actions on this stop"
log:  "Hospitality Amulet: ${player_name} enjoys today's meal for free"
log:  "Vitality Amulet: ${player_name} plays again"
log:  "Fortune Amulet: ${player_name} earns ${coins} coin(s)"
```

**Devotion quirk**: redirects already-spent meal coins from bank to temple. The parser sets `coins_gained=amount, coins_donated=amount` so the purse model nets to 0 (the meal already deducted these coins), but `vp_temple` and `num_donations` both increment.

### Crossroads — Calligraphy

Purchase:

```
log:  "${player_name} buys a Calligraphy for ${coins} coin(s)"
args: { coins:1, cards: {id: {type:"calligraphy", type_arg:"0..5"}} }

log:  "${player_name} doesn\`t buy any Calligraphy"
```

`type_arg` → name (from `CALLIGRAPHY_TYPE_ARG_TO_NAME`):
- `0` foresight, `1` contemplation, `2` nostalgia, `3` patience, `4` perfection, `5` fasting

Sets `has_calligraphy_<name>=True` on the player result.

End-game scoring:

```
log:  "${player_name} scores ${points} points (${calligraphy_name})"
args: {
  calligraphy_name: "Patience Calligraphy",
  calligraphy_card_id, calligraphy_card_type: "calligraphy_<type_arg>",
  points
}
```

Every bought calligraphy is scored at end-game, even if it gives 0 VP.

### Traveler ability bonus events

Modern BGA replays emit explicit log lines for traveler abilities that grant VP/coins. The parser captures these as `TravelerAbility` rows; their VP routes to `vp_other` unless re-routed elsewhere (Hirotada → vp_temple).

```
log:  "Hirotada: ${player_name} gives 1 more coin to the temple (from the bank) and earns 1 more point"
# Bank-funded donation — same `coins_gained=1, coins_donated=1` pairing as Miko.

log:  "Umegae: ${player_name} earns 1 point and 1 coin"
log:  "Gotozaemon: ${player_name} earns 1 coin"            # at Field/Mountain/Sea/CherryTree
log:  "Mitsukuni: ${player_name} earns 1 bonus point"      # at HotSpring/Achievement
log:  "Nampo: ${player_name} scores ${points} bonus point(s)"     # at Inn — points = meal retail cost

# Daigoro: free souvenir at Inn
log:  "Daigoro: ${player_name} gets a souvenir card and earns ${points} points"

# Jirocho: 1-coin gambling (separate from Gaming Room — same NET-vs-GROSS quirk)
log:  "Jirocho: ${player_name} bets 1 coin and wins ${won}, and so earns ${coins} coin(s)"
log:  "Jirocho: ${player_name} bets 1 coin and loses the money"
```

The parser **does NOT inline-credit** these abilities on the main action — modern BGA emits both the explicit log AND the main event, so inlining would double-count. The explicit log is the source of truth.

## Counters

Every event carries an `args.counters` dict with the latest values of various game state counters, including `player_coins_<pid>` and `player_templecoins_<pid>`. The parser only reads `player_coins_<pid>` on the `travelerChosen` event (to capture each character's starting coins) — all other counter snapshots are ignored in favor of computing player state from the move log.

## Cards field — `classified`

Card-bearing events (Calligraphy/Amulet/LegendaryObject purchases, souvenir buys) include `args.classified: true` when the calling viewer can see the card's `type_arg`. Tokaido replays are always classified — the buyer's choice is visible to everyone (verified across 1,333 events: 100% classified). No need for a fallback when the classified flag is `false`.

## VP reconciliation

After parsing, `sum(vp_*) == final_score` exactly for every player in every game (33,708 games × 4 players, 0 discrepancies after the coin-balance and donation-routing fixes documented in [`tokaido_models.py`](../../bga_replay_parser/tokaido_models.py)).

## Storage layout

```
data/batch/tokaido/raw/<table_id>.json     # raw gamelogs (no replay HTML)
data/batch/tokaido/parsed/                 # batch parser output
  player_results_base.csv                   # one row per player per base game
  player_results_xroads.csv                 # one row per player per Crossroads game (+10 cols)
  moves_base.csv                            # one row per action in a base game
  moves_xroads.csv                          # one row per action in a Crossroads game
```
