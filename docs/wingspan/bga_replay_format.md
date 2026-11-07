# BGA Wingspan Replay Format Reference

Based on the 76,442 replays in `data/batch/wingspan/raw/` (2022-10 → 2025-01, base game + Swift Start, 2- and 3-player Arena).

## Raw format

Same as Tokaido: the JSON output of the BGA archive API, saved by `scrape_raw_replay.py --raw-format json` as `<table_id>.json` — a flat list of packets.

```
GET /archive/archive/logs.html?table=<id>&translated=true
-> { "data": { "logs": [ ...packets... ] } }
```

No `gameui.completesetup` gamedatas is needed: everything the parser uses is in the gamelogs.

## Packet / event structure

Each **packet**: `channel`, `table_id`, `packet_id`, `packet_type`, `move_id`, `time`, `data: [events]`.

Each **event**: `uid`, `type`, `log` (template with `${var}` placeholders, or `""`), `args`.

The parser dispatches on **`event.type`** — Wingspan's types are specific (`playBird`, `layEggs`, `cacheFood`). The log template is only used to split `noAction` into its sub-cases.

### Channels: every player's hidden information is present

| Channel | Contents |
|---|---|
| `/table/t<table_id>` | Public events |
| `/player/p<player_id>` | That player's private events — one channel **per player**, all present in the archive |

So card draws, tucked cards and bonus-card choices are visible for every player, not just the account that scraped the replay. Private events have `move_id: null` before the first move and otherwise share the `move_id` of their public counterpart, and **arrive before it**.

Hidden actions come as a private/public pair:

| Private (`/player`) | Public (`/table`) | Private adds |
|---|---|---|
| `drawBirdsPrivate` | `drawBirdsPublic` | Card ids (see quirk below) |
| `tuckCardFromHandPrivate` | `tuckCardFromHandPublic` | `tucked_card`, `tucked_name` |
| `moveBonusPrivate` | `moveBonusPublic` | Bonus ids drawn and the one kept |
| `initialDiscardBirds` / `initialDiscardBonus` | `initialDiscardPublic` | Nothing — the public event repeats it once all players have chosen |

Several private halves can queue up within one move before their public halves; the parser keeps a FIFO per player.

### Undo: undone actions are not in the archive

`undoRestorePoint` ("takes back his move") appears ~1.7 times per game, but the events it undid are already gone from the log — no rollback is needed. Checked on the whole corpus: every player in every non-conceded game has exactly 26 `setCube` events. `newSavePoint` / `invalidateSavePoint` / `undoInitialDiscard` can be ignored.

## Ids

| Thing | Encoding |
|---|---|
| Food | `0` invertebrate, `1` seed, `2` fish, `3` fruit, `4` rodent. `-1` / `-2` are "none" sentinels inside lists. |
| Dice faces (`rollAllDice.dice_sides`) | `0`–`4` as food; `5` = the invertebrate-or-seed face |
| Board slot (`location`) | `8 × row + column`: forest `9–13`, grassland `17–21`, wetland `25–29`. `8`/`16`/`24` = the cube's resting place at the row start. `changeHabitat` writes it as `"tableau_19"`. |
| `setCube.location` | `0` = play a bird; otherwise the leftmost empty slot of the row. `14`/`22`/`30` = column 6 (row full). |
| Birds, bonus cards | See [cards.md](cards.md). Bird ids appear as `bird_type`, `type_arg`, `type_args`, `tucked_card`, `bird_discard`, `card_discard`. |

Ints arrive as either numbers or strings, inconsistently, including within one event type.

## Setup

```
type: "initialDiscardPublic"                  (one per player, move 3)
args: { player_id, bird_discard: [bird ids], food_discard: [food ids], bonus_discard: [bonus id] }
```

- Starting food = the five food types minus `food_discard`; birds kept = `5 − len(bird_discard)`.
- The **kept birds are not listed anywhere**. They can only be inferred later: a card that leaves a hand (played, tucked, discarded) without ever being drawn was a kept starting card. `starting_birds_kept_known` holds those; kept cards still in hand at game end stay unknown.
- The kept bonus card is the single key of `bonus_data` in the player's first private `updateGoalData`.

## Turn structure

```
setCube        { player_id, location, habitat_name }      # turn start; fixes the action
  ...action and power events...
moveCube       { player_id, location, bird_name }          # cube stops on a bird: brown power activates
  ...that power's events...
moveCube       { player_id, location: 8|16|24 }            # log "...and ends their turn" (habitat actions only)
refillTray / discard / mustDiscardBird                     # after the turn's last action
```

- A "play a bird" turn has `setCube` with `location: 0` and no `moveCube`.
- Power-driven events carry the power's bird in `bird_name`; base-action events have `bird_name: ""` or no key.
- Pink powers fire inside another player's turn, with the pink bird's owner in `player_id`.
- Round end: `resetPlayerCubes`, one `scoreGoal` per rank group, `discardTray`, `refillTray`, `changeFirstPlayer { player_id, current_round }`. Round 4 ends with `scoreGoal` followed directly by `setupFinalScoring`.

## Gameplay events

| Type | Key args | Notes |
|---|---|---|
| `playBird` | `bird_type`, `location`, `food_paid: [food ids]`, `eggs_paid: [slots]` | `eggs_paid` lists the slot each egg came from |
| `gainFood` | `food_types`, `dice_ids`, `card_discard`, `bird_name` | From the birdfeeder. `card_discard` ≠ -1 = the forest trade (a bird card for one more food). Empty `food_types` = chose not to take food. |
| `foodFromSupply` | `food_type`, `delta`, `bird_name` | `delta: 1` gain, `delta: -1` pay ("pays food to supply", e.g. Green Heron). Always a power. |
| `layEggs` | `locations: [slots]`, `egg_nbr`, `food_discard`, `bird_name` | One slot per egg. `food_discard` ≠ -1 = the grassland trade. |
| `discardEgg` | `location`, `bird_name`, `source_bird_name` | Without `source_bird_name`: wetland trade, `bird_name` is the egg's bird. With it: a power (`bird_name`) took an egg from `source_bird_name`. |
| `drawBirdFromTray` | `type_arg`, `tray_bird_name`, `location`, `bird_name` | `location: "hand"` normally |
| `drawBirdsPublic` | `nbr`, `type_args`, `location`, `prev_location`, `bird_name` | From the deck. See quirks. |
| `tuckCardFromHandPublic` | `location`, `bird_name` | 1 card from hand behind the bird at `location` |
| `tuckCardFromDeck` | `location`, `nbr`, `bird_name` | `nbr` cards from the deck |
| `huntWingspan` | `type_arg` (prey), `limit`, `success`, `location`, `bird_name` | Reveals a deck card; on success it is tucked |
| `rollDiceNotInFeeder` + `cacheFood` / `noAction` | `values` | Dice-hunt predators: a hit is a `cacheFood`, a miss is `noAction` "None of the rolled dice match" |
| `cacheFood` | `food_type`, `location`, `delta`, `dice_id`, `bird_name` | Food onto the bird; never comes out of the player's own supply |
| `changeHabitat` | `from_location`, `to_location`, `type_arg`, `moved_tableau` | A bird moves rows, taking its eggs, cache and tucked cards along |
| `discard` | `bird_discard: [bird ids]` | End-of-turn discards forced by a power (announced by `mustDiscardBird`) |
| `moveBonusPublic` | `location`, `prev_location`, `type_args` | `deck → discard_one` (2 drawn), then `discard_one → discard` (the rejected one, public). The kept one is only in `moveBonusPrivate` (`location: "hand"`). |
| `noAction` | `bird_name`, … | ~20 log templates: power declined, power failed (no eggs/cards/food/nest space/…), "repeats ${repeated_name}'s power". Often has no `player_id`. |

Every scoring-relevant event also carries `score`, the player's running total.

Ignored (UI/bookkeeping): `gameStateChange`, `updateGoalData` and `updateBonusData` on the table channel, `updateReflexionTime`, `reorderHand`, `setPinkPowersActivated`, `setAutoActivate`, `updateArgs`, `gameStateChangePrivateArg`, `gameStateMultipleActiveUpdate`, `wakeupPlayers`, `rollAllDice`, `refillTray`, `discardTray`, `mustDiscardBird`, `simpleNote`, `simpleNode`, `timeJokerUsed`, `switchToTurnbased`, `reshuffleDeck`.

### Quirks

- **`drawBirdsPublic` lost its card ids on 2024-09-02.** Before, the public event has `type_args`; after, only `nbr`, and the ids are on `drawBirdsPrivate` alone. The parser takes names from the public event when present, else from the queued private half.
- **American Oystercatcher's shared display.** Cards go `deck`/tray → `location: "special"` (not a hand), then each player takes one: `drawBirdsPublic` with log "draws a card" and `prev_location: "special"`. Only moves into `location: "hand"` count as draws; the parser tags these `detail = "display"`.
- **`noAction` owner.** With no `player_id`, the parser attributes the row to the owner of `bird_name` (cards are unique), falling back to the active player.
- **Id-keyed maps can arrive as lists.** A map whose keys happen to be `0..n-1` is serialized as a JSON list, so a player holding only bonus card 0 (Anatomist) has `bonus_data: [[{...}, 0]]` and `scored_bonuses: [[...]]`. Empty maps arrive as `[]`.
- **Private `updateGoalData`** (sent after nearly every action) has `goal_data: [{value, rank, score} × 4]` — the player's current standing on all four goals — and `bonus_data: {bonus_id: [{slot: bird_id}, count]}` for each bonus card held. The parser uses it for the starting bonus card and for the goal count of players who score 0.

## Scoring events

```
type: "scoreGoal"                                  (end of each round, one per rank group)
args: { player_ids: [...], round: "0".."3", position, value, score_value, score_string? }
```

Tied players share one event (`player_ids` has several entries; `score_value` is already the split amount). A group that scores 0 with nothing to count has no `position`/`value`.

Final scoring, per player:

| Type | Args |
|---|---|
| `finalScoringPlayerSetup` | `scored_bonuses: {bonus_id: [{slot: bird_id}, score]}` — the bonus cards held |
| `scoreBirds` | `score_birds`, `bird_vp_by_location: {slot: vp}` |
| `scoreBonus` | `index` (bonus id), `bonus_name`, `count`, `score` — one per bonus card |
| `scoreGoals` | `score_goals`, `score_by_goal: {"1".."4": points}` |
| `scoreEggs` | `nbr` |
| `scoreCache` | `score_cache`, `cache_by_location: {slot: n}` |
| `scoreTucked` | `score_tucked`, `tucked_by_location: {slot: n}` |

## Result block

The last `gameStateChange` (state 99) has `args.args = { table: {...}, result: [...] }`.

`table.concede` is the conceded flag. `table.stats`:

| Key | Meaning |
|---|---|
| `40`–`43` | Round-goal id for rounds 1–4 ([cards.md](cards.md)) |

Other table and player stat keys (`1`–`4`, `16`–`31`, `50`–`57`) are not decoded and not used.

`result[i]`: `player`, `name`, `score`, `score_aux`, `rank`, `tie`, `zombie`, `concede`, `stats`. `score_aux` is the tiebreaker, the player's unused food tokens. Player `stats`:

| Key | Meaning |
|---|---|
| `10`–`15` | VP from birds, bonus cards, round goals, eggs, cached food, tucked cards — sums to `score` |
| `60`–`74` | Bird id in each board slot (forest 1–5, grassland 1–5, wetland 1–5); `999` = empty |

## Replays to skip

`WingspanParser.should_skip(packets)` returns a reason for:

- **`conceded`** — `table.concede` is true, or a `playerConcedeGame` / `gameQuitWithNoPenalty` / `gameResultNeutralized` event exists (5,101 games). These stop mid-game: no final scoring events, and the VP stats do not sum to the score.
- **`no_result`** — no result block (6 games).

Zero-byte files from failed scrapes are parked in `data/batch/wingspan/raw_invalid/`.

## Reconciliation

The parser tracks each player's board, eggs/cache/tucked per slot, food stock and hand size, and records a warning on the game (`WingspanGameData.warnings`, logged by the batch parser) when any of these fail:

- `vp_birds + vp_bonus + vp_goals + vp_eggs + vp_cached + vp_tucked == final_score`
- board slots match `bird_vp_by_location`; eggs sum to `scoreEggs.nbr`; cache and tucked match per slot
- 26 turns per player
- food stock never negative; final food equals `score_aux`
- hand size never negative; no more undrawn cards leave a hand than were kept at setup
