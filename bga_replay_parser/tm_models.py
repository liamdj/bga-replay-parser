"""Data models for Terra Mystica parser output."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EloData:
    elo_before: Optional[int] = None
    elo_after: Optional[int] = None
    arena_before: Optional[float] = None
    arena_after: Optional[float] = None


@dataclass
class TMPlayerState:
    coins: int = 0
    workers: int = 0
    priests: int = 0
    power_bowl1: int = 0
    power_bowl2: int = 0
    power_bowl3: int = 0
    cult_fire: int = 0
    cult_water: int = 0
    cult_earth: int = 0
    cult_air: int = 0
    score: int = 0
    shipping_level: int = 0
    exchange_level: int = 0
    income_coins: int = 0
    income_workers: int = 0
    income_priests: int = 0
    income_power: int = 0


@dataclass
class TMMove:
    move_number: int = 0
    round_number: int = 0
    phase: str = "setup"
    player_id: str = ""
    player_name: str = ""
    faction: str = ""
    action_type: str = "other"
    description: str = ""
    hex_coord: Optional[str] = None
    secondary_hex: Optional[str] = None  # for bridges: the other endpoint
    structure_type: Optional[str] = None
    upgraded_from: Optional[str] = None
    terrain_from: Optional[str] = None
    terrain_to: Optional[str] = None
    spades_used: Optional[int] = None
    cult_track: Optional[str] = None
    cult_from: Optional[int] = None
    cult_to: Optional[int] = None
    tile_or_card: Optional[str] = None
    town_id: Optional[str] = None
    town_vp: Optional[int] = None
    town_resources: Optional[str] = None
    cost_workers: int = 0
    cost_coins: int = 0
    cost_priests: int = 0
    cost_power: int = 0
    gain_vp: int = 0
    gain_coins: int = 0
    gain_workers: int = 0
    gain_priests: int = 0
    gain_power: int = 0
    power_action_type: Optional[str] = None
    special_action_type: Optional[str] = None
    state_after: Optional[TMPlayerState] = None


@dataclass
class TMRoundSummary:
    round_number: int = 0
    player_id: str = ""
    player_name: str = ""
    faction: str = ""
    scoring_tile: str = ""
    scoring_vp_gained: int = 0
    income_coins: int = 0
    income_workers: int = 0
    income_priests: int = 0
    income_power: int = 0
    cult_bonus_coins: int = 0
    cult_bonus_workers: int = 0
    cult_bonus_priests: int = 0
    cult_bonus_power: int = 0
    cult_bonus_spades: int = 0
    num_actions: int = 0
    spades_used: int = 0
    dwellings_built: int = 0
    structures_upgraded: int = 0
    cult_advances: int = 0
    power_actions_used: int = 0
    towns_founded: int = 0
    power_actions: List[str] = field(default_factory=list)
    power_gained_via_structures: int = 0
    power_gained_via_cults: int = 0
    power_gained_via_other: int = 0
    # Per-round resource flow (generated = positive inflows, spent = positive outflows)
    coins_generated: int = 0
    coins_spent: int = 0
    workers_generated: int = 0
    workers_spent: int = 0
    priests_generated: int = 0
    priests_spent: int = 0
    spades_generated: int = 0
    power_generated: int = 0
    power_spent: int = 0
    vp_generated: int = 0
    vp_leach_cost: int = 0
    vp_faction_spent: int = 0
    # End-of-action-phase snapshots (before cleanup cult bonuses are distributed)
    vp_at_round_end: int = 0
    coins_at_round_end: int = 0
    workers_at_round_end: int = 0
    power_bowl1: int = 0
    power_bowl2: int = 0
    power_bowl3: int = 0
    cult_fire: int = 0
    cult_water: int = 0
    cult_earth: int = 0
    cult_air: int = 0
    bonus_card: str = ""
    pass_order: Optional[int] = None


@dataclass
class TMPlayerResult:
    player_id: str = ""
    player_name: str = ""
    faction: str = ""
    terrain: str = ""
    color: str = ""
    seat_order: int = 0
    starting_vp: int = 0
    final_vp: int = 0
    vp_round_scoring: int = 0
    vp_favor_tiles: int = 0
    vp_bonus_cards: int = 0
    vp_towns: int = 0
    vp_faction_ability: int = 0
    vp_power_leaching: int = 0
    vp_conversions: int = 0
    vp_track_advances: int = 0
    vp_cult_final: int = 0
    vp_network_final: int = 0
    vp_resources_final: int = 0
    dwellings_built: int = 0
    trading_houses_built: int = 0
    temples_built: int = 0
    strongholds_built: int = 0
    sanctuaries_built: int = 0
    bridges_built: int = 0
    towns_formed: int = 0
    cult_fire: int = 0
    cult_water: int = 0
    cult_earth: int = 0
    cult_air: int = 0
    # Resources: generated (positive inflows), spent (positive outflows), conversions (net, can be negative)
    coins_generated: int = 0
    coins_spent: int = 0
    coins_converted: int = 0       # net: positive = gained via conversion, negative = lost
    workers_generated: int = 0
    workers_spent: int = 0
    workers_converted: int = 0
    priests_generated: int = 0
    priests_spent: int = 0
    priests_converted: int = 0
    spades_generated: int = 0
    spades_spent: int = 0          # always 0 (spades are generated and used in same action)
    power_generated: int = 0
    power_spent: int = 0
    power_converted: int = 0       # net: negative (power out), positive shouldn't happen
    vp_generated: int = 0          # all VP gained (scoring, towns, tracks, etc.)
    vp_spent: int = 0              # VP lost (leach cost)
    vp_converted: int = 0          # net: alchemists VP<->coin, end-game resource scoring
    shipping_level: int = 0
    exchange_level: int = 0
    network_size: int = 0
    favor_tiles: List[str] = field(default_factory=list)
    town_tiles: List[str] = field(default_factory=list)
    bonus_cards: List[str] = field(default_factory=list)
    landscape_placed: str = ""  # name of faction landscape placed, empty if not placed
    landscape_hex: str = ""     # hex where landscape was placed
    elo_data: Optional[EloData] = None


@dataclass
class TMAuctionBid:
    """One player's bid on one faction in a fast-auction setup.

    In the fast auction every player submits, for every faction, the starting
    VP they'd accept to play it (lower = more willing). `is_winning_bid` marks
    the (player, faction) pair that the auction actually assigned.
    """
    player_id: str = ""
    player_name: str = ""
    faction: str = ""
    bid_starting_vp: int = 0
    is_winning_bid: bool = False


@dataclass
class TMGameData:
    table_id: str = ""
    player_perspective: str = ""
    game_date: str = ""
    game_speed: str = ""
    game_mode: str = ""
    num_players: int = 0
    board: str = ""
    total_rounds: int = 0
    with_auction: bool = False
    landscape_active: bool = False
    custom_map: bool = False
    variable_turn_order: bool = False
    fire_ice_scoring: bool = False
    auction_type: str = ""      # bid-derived: "fast" | "slow" | "" — the RELIABLE auction indicator
    # Raw "Starting VP" game-option label from table metadata (e.g. "Standard
    # auction", "Fast auction", "Adjusted by Faction", "Standard"). UNRELIABLE
    # pre-2023: ~12k 2020-22 games labelled "Adjusted by Faction" were really
    # auctions (bid sequences present). Use auction_type as ground truth.
    starting_vp_setting: str = ""
    game_version: str = ""
    mini_expansions: List[str] = field(default_factory=list)
    fan_factions: bool = False
    fire_ice_factions: bool = False
    winner_player_id: str = ""
    winner_player_name: str = ""
    conceded: bool = False
    players: Dict[str, TMPlayerResult] = field(default_factory=dict)
    moves: List[TMMove] = field(default_factory=list)
    round_summaries: List[TMRoundSummary] = field(default_factory=list)
    auction_bids: List["TMAuctionBid"] = field(default_factory=list)
    scoring_tiles: List[str] = field(default_factory=list)
    bonus_cards: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseContext:
    """Internal mutable state used during parsing."""
    player_map: Dict[str, str] = field(default_factory=dict)       # id -> name
    factions: Dict[str, str] = field(default_factory=dict)          # id -> faction
    colors: Dict[str, str] = field(default_factory=dict)            # id -> color
    terrains: Dict[str, str] = field(default_factory=dict)          # id -> terrain
    seat_order: Dict[str, int] = field(default_factory=dict)        # id -> turn order
    starting_vp: Dict[str, int] = field(default_factory=dict)       # id -> starting VP
    elo_metadata: Dict[str, Dict] = field(default_factory=dict)     # id -> {elo_before, ...}

    bonus_id_to_type: Dict[str, str] = field(default_factory=dict)
    bonus_type_to_name: Dict[str, str] = field(default_factory=dict)
    scoring_round_to_type: Dict[str, str] = field(default_factory=dict)
    scoring_type_to_name: Dict[str, str] = field(default_factory=dict)
    favor_type_to_name: Dict[str, str] = field(default_factory=dict)

    player_states: Dict[str, TMPlayerState] = field(default_factory=dict)
    current_round: int = 0
    current_phase: str = "setup"
    move_counter: int = 0

    structures: Dict[str, Dict[str, str]] = field(default_factory=dict)
    player_favor_tiles: Dict[str, List[str]] = field(default_factory=dict)
    player_landscape_hex: Dict[str, str] = field(default_factory=dict)  # pid -> hex
    player_town_tiles: Dict[str, List[str]] = field(default_factory=dict)
    player_bonus_card: Dict[str, str] = field(default_factory=dict)
    bonus_card_by_round: Dict[int, Dict[str, str]] = field(default_factory=dict)
    last_town_id: str = ""
    hex_map: Dict[str, str] = field(default_factory=dict)  # bts_id -> standard label
    bbs_map: Dict[str, tuple] = field(default_factory=dict)  # bbs_id -> (sequential_a, sequential_b)

    vp_sources: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Auction bids in log order: list of (player_id, faction, bid_starting_vp).
    # Fast auction = one bid per (player, faction); slow (turn-based) = a
    # sequence with repeats. Collapsed to last-per-(player, faction) at assembly.
    auction_bids: List[tuple] = field(default_factory=list)
    auction_type: str = ""      # "fast" | "slow" | ""

    all_round_income: Dict[int, Dict[str, Dict[str, int]]] = field(default_factory=dict)
    all_round_scoring_vp: Dict[int, Dict[str, int]] = field(default_factory=dict)
    all_round_actions: Dict[int, Dict[str, Dict[str, int]]] = field(default_factory=dict)
    all_pass_order: Dict[int, Dict[str, int]] = field(default_factory=dict)
    all_round_power_actions: Dict[int, Dict[str, List[str]]] = field(default_factory=dict)
    all_round_power_gained: Dict[int, Dict[str, Dict[str, int]]] = field(default_factory=dict)
    all_round_cult_bonus: Dict[int, Dict[str, Dict[str, int]]] = field(default_factory=dict)
    all_round_vp_leach: Dict[int, Dict[str, int]] = field(default_factory=dict)
    all_round_vp_faction: Dict[int, Dict[str, int]] = field(default_factory=dict)

    round_income: Dict[str, Dict[str, int]] = field(default_factory=dict)
    round_scoring_vp: Dict[str, int] = field(default_factory=dict)
    round_actions: Dict[str, Dict[str, int]] = field(default_factory=dict)
    pass_order: Dict[str, int] = field(default_factory=dict)
    pass_counter: int = 0
    round_power_actions: Dict[str, List[str]] = field(default_factory=dict)
    round_power_gained: Dict[str, Dict[str, int]] = field(default_factory=dict)
    round_cult_bonus: Dict[str, Dict[str, int]] = field(default_factory=dict)
    round_vp_leach: Dict[str, int] = field(default_factory=dict)
    round_vp_faction: Dict[str, int] = field(default_factory=dict)

    round_end_states: Dict[int, Dict[str, TMPlayerState]] = field(default_factory=dict)

    # Cumulative resource tracking: {pid -> {resource -> total}}
    # Resources: coins, workers, priests, spades, power, vp
    res_generated: Dict[str, Dict[str, int]] = field(default_factory=dict)
    res_spent: Dict[str, Dict[str, int]] = field(default_factory=dict)
    res_converted: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Per-round resource flow snapshots: round -> {pid -> {resource -> total}}
    # Snapshot of cumulative values at start of round (for delta computation)
    res_generated_snapshot: Dict[str, Dict[str, int]] = field(default_factory=dict)
    res_spent_snapshot: Dict[str, Dict[str, int]] = field(default_factory=dict)
    res_converted_snapshot: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # Stored per-round deltas: round -> {pid -> {resource -> delta}}
    all_round_res_generated: Dict[int, Dict[str, Dict[str, int]]] = field(default_factory=dict)
    all_round_res_spent: Dict[int, Dict[str, Dict[str, int]]] = field(default_factory=dict)
    all_round_res_converted: Dict[int, Dict[str, Dict[str, int]]] = field(default_factory=dict)
