"""Data models for Tokaido parser output."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Crossroads-only fields on TokaidoPlayerResult. The base-game CSV writer
# strips these so base-only output stays narrow and self-documenting.
XROADS_ONLY_PLAYER_FIELDS = (
    "vp_calligraphy",
    "vp_bath_house",
    "vp_cherry_tree",
    "vp_legend_bonus",
    "num_amulets_purchased",
    "num_amulets_used",
    "num_calligraphies",
    # Per-category legendary
    "vp_legendary_script",
    "vp_legendary_offering",
    "vp_legendary_sword",
    "num_legendary_script",
    "num_legendary_offering",
    "num_legendary_sword",
    # Per-name calligraphy ownership bools
    "has_calligraphy_foresight",
    "has_calligraphy_contemplation",
    "has_calligraphy_nostalgia",
    "has_calligraphy_patience",
    "has_calligraphy_perfection",
    "has_calligraphy_fasting",
)


@dataclass
class TokaidoMove:
    move_number: int = 0
    player_id: str = ""
    traveler: str = ""
    type: str = ""             # high-level action category (Traveled, Village, Temple, ...)
    subtype: str = ""          # specific within category (panorama color, meal name, achievement, ...)
    space: str = ""            # Tokaido road space label (e.g. "Temple_2") if applicable
    coins_gained: int = 0
    coins_spent: int = 0
    coins_donated: int = 0     # subset of spent that went to the temple
    points_gained: int = 0
    souvenirs_food: int = 0
    souvenirs_clothing: int = 0
    souvenirs_art: int = 0
    souvenirs_trinket: int = 0


@dataclass
class TokaidoPlayerResult:
    player_id: str = ""
    player_name: str = ""
    player_color: str = ""
    traveler: str = ""
    starting_position: int = 0
    starting_coins: int = 0     # value of player_coins counter at travelerChosen event
    final_score: int = 0
    score_aux: int = 0          # BGA tiebreaker (achievements count, per old format)
    final_rank: int = 0
    is_winner: bool = False

    # VP breakdown (sums to final_score). Donation-source VP — Miko encounter
    # (1 VP per donation) and Devotion amulet (variable VP per spent coin) —
    # is folded into vp_temple since the player materially donated to the
    # temple in both cases. The action's count still increments num_encounters
    # / num_amulets_used respectively.
    vp_panorama_mountain: int = 0
    vp_panorama_sea: int = 0
    vp_panorama_field: int = 0
    vp_temple: int = 0
    vp_temple_rank: int = 0     # end-game donation ranking
    vp_hot_spring: int = 0
    vp_encounter: int = 0
    vp_inn: int = 0
    vp_village: int = 0
    vp_achievement: int = 0
    vp_calligraphy: int = 0     # Crossroads — sum of points scored from played calligraphy
    vp_legendary_script: int = 0    # Crossroads — script-type legendary VP (Shodo, Emaki)
    vp_legendary_offering: int = 0  # Crossroads — offering-type (Buppatsu, Ema)
    vp_legendary_sword: int = 0     # Crossroads — sword-type (Murasame, Masamune)
    vp_bath_house: int = 0
    vp_cherry_tree: int = 0
    vp_legend_bonus: int = 0    # generic "${legend}: ${player} earns ${points}" events
    vp_other: int = 0

    # Action / item counts
    num_actions: int = 0
    num_meals: int = 0
    num_amulets_purchased: int = 0
    num_amulets_used: int = 0
    num_calligraphies: int = 0
    num_legendary_script: int = 0
    num_legendary_offering: int = 0
    num_legendary_sword: int = 0
    num_encounters: int = 0
    num_villages_visited: int = 0
    num_donations: int = 0          # includes Temple, Miko encounter, Devotion amulet
    num_panorama_cards_mountain: int = 0
    num_panorama_cards_sea: int = 0
    num_panorama_cards_field: int = 0
    first_to_finish_mountain: bool = False
    first_to_finish_sea: bool = False
    first_to_finish_field: bool = False
    num_souvenirs_food: int = 0
    num_souvenirs_clothing: int = 0
    num_souvenirs_art: int = 0
    num_souvenirs_trinket: int = 0

    # Crossroads — calligraphy ownership bools (true if player bought this calligraphy).
    has_calligraphy_foresight: bool = False
    has_calligraphy_contemplation: bool = False
    has_calligraphy_nostalgia: bool = False
    has_calligraphy_patience: bool = False
    has_calligraphy_perfection: bool = False
    has_calligraphy_fasting: bool = False

    # Economy totals (sum across moves)
    coins_gained_total: int = 0
    coins_spent_total: int = 0
    coins_donated_total: int = 0


@dataclass
class TokaidoGameData:
    table_id: str = ""
    num_players: int = 0
    has_crossroads: bool = False     # Crossroads expansion (CherryTree/BathHouse/Calligraphy/Legendary/Amulet present)
    preparations: bool = False   # Preparations expansion — only modifies starting coins by position
    winner_player_id: str = ""
    winner_player_name: str = ""
    players: Dict[str, TokaidoPlayerResult] = field(default_factory=dict)
    moves: List[TokaidoMove] = field(default_factory=list)
