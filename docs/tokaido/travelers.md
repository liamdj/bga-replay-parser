# Tokaido — Travelers

Each player picks 1 of 2 random Travelers at game start. The Traveler's printed coin count = starting bank. Most Travelers also get a passive or trigger ability that fires throughout the game; modern BGA replays emit these as their own log lines (`${traveler_name}: ${player} earns ${X} points` or similar), captured by the parser as `TravelerAbility` rows.

## Base game travelers (10)

| Traveler | Ability |
|----------|---------|
| **Hiroshige the artist** | At each of the 3 intermediate Inns, before the meal, take 1 Panorama card of his choice and score it immediately. (4 free panorama cards over the trip in addition to normal panorama stops.) |
| **Chuubei the messenger** | At each intermediate Inn, before the meal, draw 1 Encounter card and apply its effect. |
| **Kinko the ronin** | All Meal cards cost 1 coin less. (1-coin meals become free.) |
| **Yoshiyasu the functionary** | On Encounter spaces, draw 2 cards, keep 1, return the other to the bottom of the deck (hidden). |
| **Satsuki the orphan** | At each Inn, receives one of the available Meal cards at random for free. May reject it and instead buy a meal normally. |
| **Mitsukuni the old man** | +1 VP for every Hot Spring card and every Achievement card. (Resolves at end of game; emits `Mitsukuni: ${player} earns ${points}` log lines.) |
| **Sasayakko the geisha** | When buying ≥2 Souvenirs in a single Village stop, the cheapest is free. (Must still have coins to cover the full cost on hand.) |
| **Hirotada the priest** | At each Temple stop, takes 1 free coin from the bank and donates it to the Temple, earning 1 VP. This is *additional* to the 1–3 coins he donates personally or 0 when buying an amulet. |
| **Umegae the street entertainer** | At each Encounter, before drawing the card: +1 VP and +1 coin. |
| **Zen-emon the merchant** | Once per Village stop, may buy 1 Souvenir for 1 coin instead of its printed price. |

## Crossroads travelers (6)

| Traveler | Ability |
|----------|---------|
| **Jirocho the yakuza** | At each intermediate Inn, before the meal, may bet 1 coin in the Gaming Room: roll the Fortune die, lose / recover / win 1–3 extra coins by table. (Free-bet, 1-coin stake — distinct from Farm's 2-coin Gaming Room.) |
| **Daigoro the kid** | At each intermediate Inn, before the meal, draws a Souvenir card. (Souvenir is added to collection and scores normally for set position.) |
| **Nampo the gourmet** | At each Inn, scores extra VP for the Meal eaten = the Meal's coin cost (1, 2, or 3 VP). |
| **Gotozaemon the souvenir seller** | +1 coin every time he stops on a Panorama space. Does not trigger on Annaibito (Guide) encounter. If he takes a Cherry Tree on the panorama space, he gets 2 VP + 2 coins (1 from Cherry Tree + 1 from his ability). |
| **Miyataka the superstitious woman** | At Temple spaces: may do **both** options — donate coins AND buy an Amulet. |
| **Kita the old woman** | At Encounter spaces: may do **both** options — draw an Encounter card AND buy a Calligraphy. |

## Parser handling

- Traveler-ability bonus VP is *not* inlined onto the parent move row. It appears as separate `TravelerAbility` move rows (BGA emits explicit `Hirotada: ...`, `Umegae: ...`, `Gotozaemon: ...`, `Nampo: ...`, `Mitsukuni: ...` log lines). This avoids double-counting against `final_score` and lets `vp_*` components reconcile to total exactly.
- Jirocho's Gaming Room rolls show up as `JirochoGaming` move type (distinct from `Gaming` on Farm spaces) because they're at-Inn free actions with a 1-coin stake rather than the 2-coin Farm-stop bet.
- Daigoro's bonus Souvenirs scored via `DaigoroSouvenir` move type.

## Skip / unsupported

- Tokaido at BGA always uses the base 10 + Crossroads 6 traveler pool when expansions are on. Newer expansions (Matsuri, Preparations) add more travelers; the parser doesn't model them and `should_skip` rejects games using the **Preparations** expansion (BGA seasons 22+).
- 2-player games are unsupported (parser rejects via `should_skip`); the bga-replays seasons 11/12/21 are all 2p and excluded from the dataset.
