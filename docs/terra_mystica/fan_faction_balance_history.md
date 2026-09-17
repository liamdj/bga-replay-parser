# Terra Mystica Fan-Faction Balance History

Balance changes to the BGA fan factions, recovered empirically from the parsed
game corpus. Each game's replay embeds the faction's full starting/balance
spec (`gamedatas.factions.<faction>`: `*_setup`, `*_cost`, `*_income`,
`*_gain`, `token_setup`, ability text, etc.) exactly as it stood when the game
was played. Grouping those specs by game start date reveals when each parameter
last changed.

## Method & caveats

- **Source**: per-game faction spec from `gamedatas`, keyed by game start
  timestamp (from `table_ids.json`). 10,056 fan-faction games.
- **Mechanical vs text**: numeric/boolean fields (power, costs, income, tokens)
  are unambiguous balance changes. Ability *text* changes are included only when
  the numbers in the text changed (e.g. "2 spades" → "1 spade"); pure
  reformatting and renames are excluded.
- **Coverage floor**: fan-faction games in the corpus begin **~2022-03**. Any
  change at/near that date is a lower bound — the real change may predate the
  data. Everything from mid-2022 onward is precise to a few days (the transition
  is bracketed between the last game of the old spec and the first of the new).
- **Dates below** are the onset of the new spec (first game observed with it).

## Key finding: changes come in coordinated waves

Most fan-faction balance changes shipped in three bundled patches
(**~2022-09-09**, **~2022-12-15**, **~2024-07-11**), plus a few standalone
tweaks. Most affected factions had several parameters change at once.

### Wave 1 — ~2022-09-09/10 (major fan rebalance, 8 factions)

| Faction | Change |
|---|---|
| djinni | starting power 0/12 → 5/7 (same total, less immediately usable); variable-cult setup 3 → 2 |
| archivists | starting power 0/12 → 5/7; 1st-dwelling worker income 2 → 1 |
| childrenofthewyrm | starting power 6/6 → 5/7; sanctuary & stronghold worker cost 5 → 4 |
| timetravellers | starting power 3/9 → 5/7; sanctuary & stronghold coin cost 6 → 8 |
| goblins | sanctuary/stronghold cost cuts (8 → 6 coins, 5 → 4 workers) |
| chashdallah | **nerf**: base extra-track coin income 2 → 0; SH coin income 6 → 4; track VP gains 2/3/4/5 → 1/2/3/4 |
| dyniongeifr | priest→worker conversion gained **+2 coins** (was +1 worker only) |
| wisps | ability-text tweak (numbers changed) |

### Wave 2 — ~2022-12-15/19 (3 factions)

| Faction | Change |
|---|---|
| treasurers | starting power 9/3 → 4/8; SH power income 2 → 4; +4 power on 2nd temple |
| dyniongeifr | starting power 8/4 → 5/7; SH power income 2 → 4 |
| archivists | 1st-dwelling worker income 1 → 2; 5th-dwelling worker income 1 → 0 |

### Wave 3 — ~2024-07-11/17 (3 factions)

| Faction | Change |
|---|---|
| goblins | **`token_setup` 2 → 1** (starts with 1 special marker instead of 2) |
| chashdallah | base extra-track coin income 0 → **2** (restores the Wave-1 nerf) |
| theenlightened | dwelling power income 2 → 3 (all dwellings); **removed** double-power on cult steps |

### Standalone changes (not part of a wave)

| Date | Faction | Change |
|---|---|---|
| 2022-03-26 | conspirators | SH power income 2 → 0 (at the data floor — only ~10 games precede it) |
| 2023-01-09 | wisps | trading-house terraform **2 spades → 1 spade** |
| 2023-10-14 | dyniongeifr | now **starts with the Fire2 favor** |

## Per-faction summary

**Had real balance changes (11):**
djinni, archivists, childrenofthewyrm, timetravellers, goblins, chashdallah,
dyniongeifr, wisps, treasurers, theenlightened, conspirators.

Change counts worth noting:
- **dyniongeifr** — 3 changes: conversion +2c (2022-09), power + SH income (2022-12), Fire2 favor (2023-10)
- **chashdallah** — base track coin 2 → 0 (2022-09 nerf) → 2 (2024-07 restore)
- **goblins** — cost cuts (2022-09), token 2 → 1 (2024-07)
- **archivists** — power + dwelling income (2022-09), dwelling income again (2022-12)
- **wisps** — ability tweak (2022-09), spades 2 → 1 (2023-01); **starting power never changed** (bowl1=7/bowl2=5 throughout)

**No balance change in the data (5):**
- architects — only stronghold rules-text *clarifications* (2023-03, 2023-11); no parameter change
- atlanteans — text formatting only
- golddiggers — name rename only (Gold Diggers → Prospectors)
- selkies — river-build wording tweak ("2 hexes" → "2 hexes on land")
- snowshamans — single spec version across the corpus (recent addition)

## Not covered

Official factions (base 14, and F&I ice: icemaidens/yetis) are out of scope
here. The excluded F&I factions (Variable: shapeshifters/riverwalkers/
changelings/geologists; Volcano: dragonlords/acolytes/firewalkers/
kingdomofember) are skipped by the parser and absent from the corpus.
