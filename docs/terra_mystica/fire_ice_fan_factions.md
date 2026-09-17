# Terra Mystica Fire & Ice Fan Factions

6 fan factions requiring the Fire & Ice expansion: 2 Ice, 2 Variable, 2 Volcano.

**Parser note**: Only Ice fan factions are parsed. Games with Variable or Volcano fan factions are skipped.

Standard reference values: starting power 5/7, starting resources 3w+15c, standard building costs as per base game.

---

## Ice Fan Factions

### Selkies (Ice)
- **Starting ability**: When using Transform and Build, may build a Dwelling on a **River space** if you have 2+ structures directly adjacent to it that aren't directly adjacent to each other. Costs 1 extra Worker, grants 2 VP. Cannot upgrade River Dwellings.
- **Stronghold**:
  - Ability: Special action — Transform and Build with 1 free Spade, Shipping +1 for this action only

### Snow Shamans (Ice)
- **Starting ability**: Each round when passing, advance 1 step on Shipping **or** Exchange track for free (no resources, no VP). Cannot advance these tracks by paying resources.
- **Stronghold**:
  - On build: place 1 free Dwelling on each **mass of ice** with at least 1 unoccupied Ice hex (a mass = group of directly adjacent Ice hexes)

---

## Variable Fan Factions

**Parser note**: Games with these factions are skipped.

### Changelings (Variable)
- **Starting power**: 7/5
- **Starting ability**: Choose a Home terrain (A), then after all factions chosen, choose 2 more terrains (B, C) not used by others. Structures on faction board are marked A/B/C — use matching-color pieces. Build Dwellings on terrain matching their color. Upgrades must match the Structure's color.
- **Stronghold**:
  - Ability: When building a Dwelling, may build from the bottom row OR the 9th spot next to SH. When upgrading DW→TH, may return to bottom row or 9th spot.

### Geologists (Variable)
- **Starting power**: 7/5
- **Starting setup**: Choose a Starting terrain (like Shapeshifters). Cover it on Transformation cycle with Glowing Rock token. No Home terrain.
- **Starting ability**: Cannot transform terrain normally. When using Transform and Build, build a Dwelling on any uncovered terrain adjacent to a covered terrain (or marked by Shapeshifter ring) on Transformation cycle. Then cover that terrain. When all 7 covered, remove all tokens. Spades instead place/remove Glowing Rock tokens.
- **Stronghold**:
  - On build: place 2 additional Volcano tiles under any structures
  - Ability: Special action — place or remove 1 Glowing Rock token (as if for a Spade)

---

## Volcano Fan Factions

**Parser note**: Games with these factions are skipped.

### Firewalkers (Volcano)
- **Starting setup**: Pyro token starts 4 VP behind your VP marker. Pyro may never be ahead of VP marker.
- **Starting ability**: Anytime during turn, move Pyro 1 space forward to gain 1 Power. Transform terrain by losing VP (move VP marker back): 6 VP for another faction's Home terrain → Volcano, 4 VP for other terrains. Cannot use Spades — instead move Pyro 4 spaces back per Spade.
- **Stronghold**:
  - Income: 2pw
  - Ability: When passing, 1 VP per group of structures on the board

### Kingdom of Ember (Volcano)
- **Starting ability**: Only way to transform terrain is "let the lava flow." Cannot use Spades — instead place 1 Volcano tile under a Dwelling per Spade. When upgrading, gain 1 Power and place 1 Volcano tile under a Dwelling. Cannot upgrade Dwellings with >1 Volcano tile. Let the lava flow: move Structure + all but 1 Volcano tile to adjacent non-Volcano space (complex movement rules involving rivers and Home terrains).
- **Stronghold**:
  - Income: 5pw
  - On build: place 2 additional Volcano tiles under any structures (including non-Dwellings, only way to do so)
