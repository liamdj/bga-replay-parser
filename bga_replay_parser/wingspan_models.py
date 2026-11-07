"""Data models for Wingspan parser output."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

FOODS = ("invertebrate", "seed", "fish", "fruit", "rodent")


@dataclass
class WingspanMove:
    move_number: int = 0
    round_number: Optional[int] = None   # 1-4; None for setup and final scoring rows
    turn_number: Optional[int] = None    # turn within the round, counted across players
    player_turn: Optional[int] = None    # the active player's nth turn of the game (1-26)
    active_player_id: str = ""           # whose turn it is
    player_id: str = ""                  # who the row's costs/gains belong to
    action: str = ""                     # the turn's action: play_bird, gain_food, lay_eggs, draw_cards
    action_column: Optional[int] = None  # column the action cube was placed on (1-5); None for play_bird
    type: str = ""                       # what this row is (see docs/wingspan/bga_replay_format.md)
    source: str = ""                     # bird whose power produced the row; "" = the base action / a rule
    location: str = ""                   # board slot(s), e.g. "forest_2"; ";"-joined when several
    birds: str = ""                      # bird card(s) involved, ";"-joined
    detail: str = ""                     # type-specific: tray/deck, goal or bonus name, failure reason, ...
    gain_invertebrate: int = 0
    gain_seed: int = 0
    gain_fish: int = 0
    gain_fruit: int = 0
    gain_rodent: int = 0
    cost_invertebrate: int = 0
    cost_seed: int = 0
    cost_fish: int = 0
    cost_fruit: int = 0
    cost_rodent: int = 0
    gain_eggs: int = 0
    cost_eggs: int = 0
    gain_cards: int = 0                  # bird cards added to hand
    cost_cards: int = 0                  # bird cards leaving hand (played, tucked, discarded)
    tucked: int = 0                      # cards tucked behind a bird (1 VP each)
    cached: int = 0                      # food cached on a bird (1 VP each)
    gain_vp: int = 0                     # round_goal and bonus_score rows only


@dataclass
class WingspanBird:
    """One bird played onto a player's board."""
    player_id: str = ""
    bird_id: int = 0
    bird: str = ""
    play_order: int = 0                  # nth bird this player played (1-based)
    round_number: int = 0
    turn_number: int = 0
    player_turn: int = 0
    habitat: str = ""                    # where it was played
    column: int = 0
    cost_invertebrate: int = 0
    cost_seed: int = 0
    cost_fish: int = 0
    cost_fruit: int = 0
    cost_rodent: int = 0
    cost_eggs: int = 0
    activations: int = 0                 # times the action cube stopped on it (brown powers)
    eggs_laid: int = 0                   # eggs ever laid on it
    times_moved: int = 0                 # habitat changes after being played
    final_habitat: str = ""
    final_column: int = 0
    vp: int = 0                          # printed VP
    final_eggs: int = 0
    final_cached: int = 0
    final_tucked: int = 0


@dataclass
class WingspanRoundGoal:
    round_number: int = 0
    goal_id: Optional[int] = None
    goal: str = ""
    player_id: str = ""
    value: Optional[int] = None          # the player's count for the goal
    position: Optional[int] = None       # 1 = best; None when the player scored 0 with nothing to count
    tied: bool = False
    points: int = 0


@dataclass
class WingspanPlayerResult:
    player_id: str = ""
    player_name: str = ""
    seat_order: int = 0                  # turn order in round 1 (1 = first player)
    final_score: int = 0
    score_aux: int = 0                   # BGA tiebreaker (unused food tokens)
    final_rank: int = 0
    is_winner: bool = False

    # VP breakdown (sums to final_score)
    vp_birds: int = 0
    vp_bonus: int = 0
    vp_goals: int = 0
    vp_eggs: int = 0
    vp_cached: int = 0
    vp_tucked: int = 0
    vp_goal_1: int = 0
    vp_goal_2: int = 0
    vp_goal_3: int = 0
    vp_goal_4: int = 0

    # Board
    num_birds: int = 0
    birds_forest: int = 0
    birds_grassland: int = 0
    birds_wetland: int = 0

    # Turns by action (sums to 26)
    turns_play_bird: int = 0
    turns_gain_food: int = 0
    turns_lay_eggs: int = 0
    turns_draw_cards: int = 0

    # Totals across the game (base actions + powers)
    food_gained: int = 0
    food_spent: int = 0
    eggs_laid: int = 0
    eggs_spent: int = 0
    cards_drawn: int = 0
    cards_drawn_tray: int = 0
    cards_drawn_deck: int = 0
    cards_tucked: int = 0
    cards_discarded: int = 0             # discarded from hand (not played, not tucked)
    food_cached: int = 0
    bonus_cards_drawn: int = 0           # bonus cards kept from bird powers

    # End state
    final_food: int = 0
    final_hand: int = 0

    # Setup
    starting_food: List[str] = field(default_factory=list)
    starting_birds_kept: int = 0
    starting_birds_kept_known: List[str] = field(default_factory=list)   # kept birds later seen leaving the hand
    starting_birds_discarded: List[str] = field(default_factory=list)
    starting_bonus: str = ""
    starting_bonus_discarded: str = ""
    bonus_cards: List[str] = field(default_factory=list)                 # held at game end


@dataclass
class WingspanGameData:
    table_id: str = ""
    num_players: int = 0
    start_time: Optional[int] = None     # unix seconds of the first / last packet
    end_time: Optional[int] = None
    goal_ids: List[Optional[int]] = field(default_factory=list)   # rounds 1-4
    goals: List[str] = field(default_factory=list)
    first_player_id: str = ""
    winner_player_id: str = ""           # "" when rank 1 is shared
    winner_player_name: str = ""
    players: Dict[str, WingspanPlayerResult] = field(default_factory=dict)
    moves: List[WingspanMove] = field(default_factory=list)
    birds: List[WingspanBird] = field(default_factory=list)
    round_goals: List[WingspanRoundGoal] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)   # failed reconciliation checks
