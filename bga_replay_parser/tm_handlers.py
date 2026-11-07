"""Event handlers for Terra Mystica parser."""

import re
from typing import Dict, Optional

from .tm_constants import CULT_NAMES, FACTIONS, FAVOR_TYPE_NAMES
from .tm_models import ParseContext, TMLeechOffer, TMMove, TMPlayerState


_RESOURCE_KEYS = {
    "vp": "vp", "power": "power", "coins": "coins",
    "workers": "workers", "priests": "priests",
}


def parse_resource_html(html_str: str) -> Dict[str, int]:
    """Extract resource amounts from BGA HTML resource icons."""
    if not html_str:
        return {}
    from .tm_constants import RESOURCE_AMOUNT_PATTERN
    resources = {}
    for m in RESOURCE_AMOUNT_PATTERN.finditer(html_str):
        title = m.group(1).lower()
        res_type = m.group(2).lower()
        amount = int(m.group(3))
        key = (_RESOURCE_KEYS.get(title)
               or _RESOURCE_KEYS.get(res_type, res_type))
        resources[key] = resources.get(key, 0) + amount
    return resources


def extract_hex(args: Dict, ctx=None) -> Optional[str]:
    """Extract the hex label from event args.

    BGA stores it in bts_id (most events) or new_struct.bts_id (upgrades). It is
    used as is: row letter A-I plus the position in the row counting every
    space, land and river alike (A1..A13, B1..B12, ...). Land and river spaces
    are labelled the same way. (The `[E3]` labels BGA prints in its log text
    skip rivers and number river spaces ambiguously, so they are not used.)
    """
    bts_id = args.get("bts_id")
    if not bts_id:
        new_struct = args.get("new_struct")
        if isinstance(new_struct, dict) and new_struct.get("bts_id"):
            bts_id = new_struct["bts_id"]
    if not bts_id:
        return None
    return str(bts_id)


def inc_round_action(ctx: ParseContext, pid: str, action: str):
    ctx.round_actions.setdefault(pid, {})
    ctx.round_actions[pid][action] = ctx.round_actions[pid].get(action, 0) + 1


def inc_vp_source(ctx: ParseContext, pid: str, category: str, amount: int):
    ctx.vp_sources.setdefault(pid, {})
    ctx.vp_sources[pid][category] = ctx.vp_sources[pid].get(category, 0) + amount


_ZERO_RES = {"coins": 0, "workers": 0, "priests": 0, "spades": 0, "power": 0, "vp": 0}


def _gen(ctx, pid, **resources):
    """Record generated resources (positive inflows)."""
    d = ctx.res_generated.setdefault(pid, dict(_ZERO_RES))
    for k, v in resources.items():
        if v and v > 0:
            d[k] = d.get(k, 0) + v


def _spend(ctx, pid, **resources):
    """Record spent resources (positive outflows)."""
    d = ctx.res_spent.setdefault(pid, dict(_ZERO_RES))
    for k, v in resources.items():
        if v and v > 0:
            d[k] = d.get(k, 0) + v


def _convert(ctx, pid, **resources):
    """Record conversion (net: positive = gained, negative = lost)."""
    d = ctx.res_converted.setdefault(pid, dict(_ZERO_RES))
    for k, v in resources.items():
        if v:
            d[k] = d.get(k, 0) + v


def _sync_score(args, pid, ctx):
    """Sync score from player.player_score in event args."""
    player_data = args.get("player", {})
    if isinstance(player_data, dict):
        p_score = player_data.get("player_score")
        if p_score is not None and pid in ctx.player_states:
            ctx.player_states[pid].score = int(p_score)


def _make_move(ctx, pid, **kwargs):
    """Create a TMMove with common fields filled from context."""
    ctx.move_counter += 1
    in_turn = ctx.current_phase == "action" and ctx.turn_number > 0
    if in_turn:
        ctx.turn_has_rows = True
    return TMMove(
        move_number=ctx.move_counter,
        round_number=ctx.current_round,
        turn_number=ctx.turn_number if in_turn else None,
        phase=ctx.current_phase,
        player_id=pid,
        player_name=ctx.player_map.get(pid, ""),
        faction=ctx.factions.get(pid, ""),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Setup handlers
# ---------------------------------------------------------------------------

def init_starting_cults(ctx, pid, faction):
    """Set a player's cult positions to their faction's starting ones (from the
    game's own faction specs, `<cult>cult_setup`). BGA logs no event for them;
    choices made during setup (e.g. Djinn) arrive later as advanceCultTrack."""
    spec = ctx.faction_specs.get(faction)
    st = ctx.player_states.get(pid)
    if not spec or st is None:
        return
    for cult in ("fire", "water", "earth", "air"):
        setattr(st, f"cult_{cult}", _safe_int(spec.get(f"{cult}cult_setup")) or 0)


def handle_faction_selected(event, args, ctx):
    pid = str(args.get("player_id", ""))
    name = args.get("player_name", "")
    ctx.player_map[pid] = name
    ctx.factions[pid] = args.get("faction_type", "")
    ctx.terrains[pid] = args.get("faction_terrain_type", "")
    ctx.player_states.setdefault(pid, TMPlayerState())
    init_starting_cults(ctx, pid, ctx.factions[pid])
    ctx.structures.setdefault(pid, {})
    ctx.player_favor_tiles.setdefault(pid, [])
    ctx.player_town_tiles.setdefault(pid, [])
    ctx.vp_sources.setdefault(pid, {})

    return _make_move(ctx, pid,
        action_type="select_faction",
        description=f"Selected {args.get('faction_name', ctx.factions[pid])}",
    )


def handle_faction_board_swapped(event, args, ctx):
    pid = str(args.get("player_id", ""))
    name = args.get("player_name", "")
    if name:
        ctx.player_map[pid] = name
    ctx.factions[pid] = args.get("new_faction", "")
    ctx.colors[pid] = args.get("player_color", "")
    ctx.terrains[pid] = args.get("faction_starting_terrain", "")
    turn_order = args.get("turn_order", "")
    if turn_order:
        ctx.seat_order[pid] = int(turn_order)
    # Fan-faction selection path: no factionPositionSelected event fires for these,
    # so initialize per-player containers here (else handle_update_score's `pid in
    # player_states` guard fails and the starting-VP updateScore goes unrecorded,
    # then handle_conversions later sees vp_delta = newScore − 0 and mis-buckets it).
    ctx.player_states.setdefault(pid, TMPlayerState())
    ctx.structures.setdefault(pid, {})
    ctx.player_favor_tiles.setdefault(pid, [])
    ctx.player_town_tiles.setdefault(pid, [])
    ctx.vp_sources.setdefault(pid, {})
    init_starting_cults(ctx, pid, ctx.factions[pid])
    return None


def handle_update_score_small_delay(event, args, ctx):
    pid = str(args.get("player_id", ""))
    new_score = int(args.get("newScore", 0))
    ctx.starting_vp[pid] = new_score
    if pid in ctx.player_states:
        ctx.player_states[pid].score = new_score
    faction_key = args.get("faction_name", "").lower().replace(" ", "")
    if faction_key in FACTIONS:
        ctx.factions[pid] = faction_key
    return None


# ---------------------------------------------------------------------------
# Core action handlers
# ---------------------------------------------------------------------------

def handle_dwelling_placed(event, args, ctx):
    pid = str(args.get("player_id", ""))
    hex_coord = extract_hex(args, ctx)
    bts_id = args.get("bts_id", "")
    if pid in ctx.structures:
        ctx.structures[pid][bts_id or hex_coord or ""] = "dwelling"
    inc_round_action(ctx, pid, "dwellings_built")
    cost_w = parse_resource_html(args.get("workers_cost", "")).get("workers", 0)
    cost_c = parse_resource_html(args.get("coins_cost", "")).get("coins", 0)
    # other_cost = range-extension surcharge (Dwarves tunneling, Fakirs carpet flight)
    other = parse_resource_html(args.get("other_cost", ""))
    cost_w += other.get("workers", 0)
    cost_c += other.get("coins", 0)
    cost_p = other.get("priests", 0)
    _spend(ctx, pid, workers=cost_w, coins=cost_c, priests=cost_p)
    return _make_move(ctx, pid,
        action_type="place_initial_dwelling" if ctx.current_round == 0 else "build_dwelling",
        description=args.get("struct_name", "Dwelling"),
        hex_coord=hex_coord, structure_type="dwelling",
        cost_workers=cost_w, cost_coins=cost_c, cost_priests=cost_p,
    )


def handle_landscape_placed(event, args, ctx):
    """Landscapes expansion: faction places its unique landscape tile.
    Cost (typically a priest sent to a cult track) flows through separate
    orderAPriest / advanceCultTrack events handled normally."""
    pid = str(args.get("player_id", ""))
    hex_coord = extract_hex(args, ctx)
    bts_id = args.get("bts_id", "")
    if pid in ctx.structures:
        ctx.structures[pid][bts_id or hex_coord or ""] = "landscape"
    ctx.player_landscape_hex[pid] = hex_coord or ""
    return _make_move(ctx, pid,
        action_type="place_landscape",
        description="Placed landscape tile",
        hex_coord=hex_coord, structure_type="landscape",
    )


def handle_terrain_transformed(event, args, ctx):
    pid = str(args.get("player_id", ""))
    hex_coord = extract_hex(args, ctx)
    terrain_to = args.get("terrain_dest", "")
    terrain_from = ""
    title_match = re.search(r"title='(\w+)'", args.get("orig", ""))
    if title_match:
        terrain_from = title_match.group(1)
    # transform_cost = spades icon; other_cost = resources spent for them
    # (workers/priests; coins or power for some fan factions)
    spades = parse_resource_html(
        args.get("transform_cost", "")).get("spade", 0)
    other = parse_resource_html(args.get("other_cost", ""))
    w_cost = other.get("workers", 0)
    p_cost = other.get("priests", 0)
    c_cost = other.get("coins", 0)
    pw_cost = other.get("power", 0)
    # Resources spent to generate spades
    _spend(ctx, pid, workers=w_cost, priests=p_cost, coins=c_cost, power=pw_cost)
    _gen(ctx, pid, spades=spades)
    inc_round_action(ctx, pid, "terrain_transforms")
    return _make_move(ctx, pid,
        action_type="transform_terrain",
        description=f"Transform {terrain_from} -> {terrain_to}",
        hex_coord=hex_coord,
        terrain_from=terrain_from, terrain_to=terrain_to,
        spades_used=spades or None,
        cost_workers=w_cost, cost_priests=p_cost,
        cost_coins=c_cost, cost_power=pw_cost,
    )


def handle_structure_upgraded(event, args, ctx):
    pid = str(args.get("player_id", ""))
    hex_coord = extract_hex(args, ctx)
    old_struct = args.get("old_struct", {})
    new_struct = args.get("new_struct", {})
    old_type = (old_struct.get("struct_type", "")
                if isinstance(old_struct, dict) else "")
    new_type = (new_struct.get("struct_type", "")
                if isinstance(new_struct, dict) else "")
    bts_id = (new_struct.get("bts_id", "")
              if isinstance(new_struct, dict) else "")
    if pid in ctx.structures and bts_id:
        ctx.structures[pid][bts_id] = new_type
    # Cost is one combined resource_cost field since mid-2022; older replays
    # split it into workers_cost + coins_cost.
    if args.get("resource_cost"):
        cost = parse_resource_html(args["resource_cost"])
    else:
        cost = parse_resource_html(
            str(args.get("workers_cost") or "") + str(args.get("coins_cost") or ""))
    w, c, p = cost.get("workers", 0), cost.get("coins", 0), cost.get("priests", 0)
    _spend(ctx, pid, workers=w, coins=c, priests=p)
    inc_round_action(ctx, pid, "structures_upgraded")
    if new_type:
        inc_round_action(ctx, pid, f"{new_type}_built")
    return _make_move(ctx, pid,
        action_type="upgrade_structure",
        description=(f"Upgrade {args.get('old_struct_name', old_type)}"
                     f" to {args.get('new_struct_name', new_type)}"),
        hex_coord=hex_coord, structure_type=new_type,
        upgraded_from=old_type, cost_workers=w, cost_coins=c, cost_priests=p,
    )


def handle_advance_cult(event, args, ctx):
    pid = str(args.get("player_id", ""))
    cult_id = args.get("cult_id", "")
    cult_name = CULT_NAMES.get(cult_id, str(cult_id))
    initial = int(args.get("initial_pos", 0))
    final = int(args.get("final_pos", 0))
    if pid in ctx.player_states:
        setattr(ctx.player_states[pid], f"cult_{cult_name}", final)
    # Free cult bumps (Cultists Ability, Favor Tile) don't count as actions
    addendum = str(args.get("addendum", ""))
    ctx.last_cult_source[pid] = addendum
    is_free = "Cultists Ability" in addendum or "Favor Tile" in addendum
    if not is_free:
        inc_round_action(ctx, pid, "cult_advances")
    pw = parse_resource_html(
        args.get("power_income", "")).get("power", 0)
    if pw > 0:
        ctx.round_power_gained.setdefault(
            pid, {"structures": 0, "cults": 0, "other": 0})
        ctx.round_power_gained[pid]["cults"] += pw
        _gen(ctx, pid, power=pw)
    # If preceded by orderAPriest for same player, merge into one move
    pending = getattr(ctx, "_pending_priest", None)
    if pending and pending[0] == pid:
        ctx._pending_priest = None
        return _make_move(ctx, pid,
            action_type="send_priest_to_cult",
            description=f"Send priest to {cult_name} {initial} -> {final}",
            cult_track=cult_name, cult_from=initial, cult_to=final,
            cost_priests=1, gain_power=pw,
        )
    return _make_move(ctx, pid,
        action_type="advance_cult",
        description=f"Advance {cult_name} {initial} -> {final}",
        cult_track=cult_name, cult_from=initial, cult_to=final,
        gain_power=pw,
    )


def handle_order_priest(event, args, ctx):
    pid = str(args.get("player_id", ""))
    _spend(ctx, pid, priests=1)
    # Stash for merging with the next advanceCultTrack event
    ctx._pending_priest = (pid,)
    return None


def handle_power_action(event, args, ctx):
    pid = str(args.get("player_id", ""))
    cost = parse_resource_html(args.get("power_cost", ""))
    # Parse each gain field independently — they're separate HTML fields
    gain = {}
    for field in ("spades_gain", "workers_gain", "coins_gain", "priests_gain", "priest_gain"):
        gain.update(parse_resource_html(args.get(field, "")))
    pw_cost = cost.get("power", 0)
    g_w = gain.get("workers", 0)
    g_c = gain.get("coins", 0)
    g_p = gain.get("priests", 0)
    spades = gain.get("spade", 0)
    # Classify by which resource is gained
    if spades == 1:
        label = "single_spade"
    elif spades >= 2:
        label = "double_spade"
    elif g_c > 0:
        label = "coins"
    elif g_w > 0:
        label = "workers"
    elif g_p > 0:
        label = "priest"
    else:
        label = "unknown"
    # power_cost holds coins when a fan faction pays the power action in coins
    c_cost = cost.get("coins", 0)
    _spend(ctx, pid, power=pw_cost, coins=c_cost)
    _gen(ctx, pid, workers=g_w, coins=g_c, priests=g_p)
    if spades > 0:
        _gen(ctx, pid, spades=spades)
    inc_round_action(ctx, pid, "power_actions_used")
    ctx.round_power_actions.setdefault(pid, []).append(label)
    return _make_move(ctx, pid,
        action_type="power_action",
        description=f"Power action: {label}",
        power_action_type=label,
        cost_power=pw_cost, cost_coins=c_cost,
        gain_workers=g_w, gain_coins=g_c, gain_priests=g_p,
    )


def handle_power_action_bridge(event, args, ctx):
    pid = str(args.get("player_id", ""))
    cost = parse_resource_html(args.get("power_cost", ""))
    log = event.get("log", "") if isinstance(event, dict) else ""
    # workers_cost is populated on every bridge event but only charged for
    # ability bridges (Engineers: workers; Architects: a priest), whose log
    # template is the one that references it.
    alt = (parse_resource_html(args.get("workers_cost", ""))
           if "${workers_cost}" in log else {})
    cost_w, cost_p = alt.get("workers", 0), alt.get("priests", 0)
    cost_c = cost.get("coins", 0)   # fan factions paying power actions in coins
    _spend(ctx, pid, power=cost.get("power", 0), coins=cost_c,
           workers=cost_w, priests=cost_p)
    inc_round_action(ctx, pid, "power_actions_used")
    inc_round_action(ctx, pid, "bridges_built")
    ctx.round_power_actions.setdefault(pid, []).append("bridge")
    # Architects Stronghold ability grants VP per bridge action (no scoring_node on
    # the follow-up updateScore). Bucket here so the bucket sum reconciles with
    # final_vp; the trailing updateScore arrives with score_delta=0 (no double-count).
    vp = parse_resource_html(args.get("score_inc", "")).get("vp", 0)
    if vp:
        inc_vp_source(ctx, pid, "vp_faction_ability", vp)
        _gen(ctx, pid, vp=vp)
    _sync_score(args, pid, ctx)
    # Bridge endpoints. A power-action bridge's log text carries "[D6-E9]" in
    # BGA's skip-rivers notation (decoded to bts_id here); ability bridges
    # (Engineers etc.) have no such text, so use the bridge slot (bbs_id).
    # The two sources disagree for ~9% of bridges (see parser.md).
    hex_a = hex_b = None
    m = re.search(r'\[([A-I]\d+)-([A-I]\d+)\]', log)
    if m and m.group(1) in ctx.log_label_to_bts and m.group(2) in ctx.log_label_to_bts:
        hex_a = ctx.log_label_to_bts[m.group(1)]
        hex_b = ctx.log_label_to_bts[m.group(2)]
    else:
        bbs_id = args.get("bbs_id")
        if bbs_id is not None:
            hex_a, hex_b = ctx.bbs_map.get(str(bbs_id), (None, None))
    return _make_move(ctx, pid,
        action_type="power_action",
        description="Power action: bridge",
        power_action_type="bridge",
        hex_coord=hex_a, secondary_hex=hex_b,
        cost_power=cost.get("power", 0),
        cost_workers=cost_w, cost_priests=cost_p, cost_coins=cost_c,
    )


# Cult-step addendum -> special_action_type, for specialActionUsed events with
# no favor/bonus id (they close the cult step logged just before them)
_CULT_STEP_SOURCES = {"Cultists Ability": "cultists_ability",
                      "Auren Stronghold": "stronghold",
                      "Goblins ability": "goblins_ability"}


def stronghold_marker(ctx, pid):
    """The current turn's stronghold-action row for pid, if any."""
    m = ctx.turn_sh_marker
    return m[1] if m and m[0] == pid else None


def handle_action_used(event, args, ctx):
    """actionUsed with stronghold=true marks a stronghold action (logged before
    its effect for most factions, after it for Architects / Children of the
    Wyrm). Emit one special_action row per turn; Chaos Magicians' double
    action shows up here too."""
    if not args.get("stronghold"):
        return None
    pid = str(args.get("player_id", ""))
    if not pid or stronghold_marker(ctx, pid) is not None:
        return None
    move = _make_move(ctx, pid,
        action_type="special_action",
        description="Special action (stronghold)",
        special_action_type="stronghold")
    ctx.turn_sh_marker = (pid, move)
    return move


def handle_special_action(event, args, ctx):
    pid = str(args.get("player_id", ""))
    source = ""
    if args.get("favor_id") and str(args["favor_id"]) != "0":
        source = "favor"
    elif args.get("bonus_id") and str(args["bonus_id"]) != "0":
        source = "bonus"
    else:
        addendum = ctx.last_cult_source.get(pid, "")
        source = next((v for k, v in _CULT_STEP_SOURCES.items() if k in addendum), "")
        if source == "stronghold" and stronghold_marker(ctx, pid) is not None:
            return None     # Auren: the stronghold row is already there
    return _make_move(ctx, pid,
        action_type="special_action",
        description=f"Special action ({source})" if source else "Special action",
        special_action_type=source,
    )


def handle_advance_shipping(event, args, ctx):
    pid = str(args.get("player_id", ""))
    if pid in ctx.player_states:
        ctx.player_states[pid].shipping_level += 1
    cost_p = parse_resource_html(args.get("priests_cost", "")).get("priests", 0)
    cost_c = parse_resource_html(args.get("coins_cost", "")).get("coins", 0)
    vp = parse_resource_html(args.get("score_inc", "")).get("vp", 0)
    _spend(ctx, pid, priests=cost_p, coins=cost_c)
    if vp:
        inc_vp_source(ctx, pid, "vp_track_advances", vp)
        _gen(ctx, pid, vp=vp)
    _sync_score(args, pid, ctx)
    return _make_move(ctx, pid, action_type="advance_shipping", description="Advance shipping",
                      cost_priests=cost_p, cost_coins=cost_c, gain_vp=vp)


def handle_advance_exchange(event, args, ctx):
    pid = str(args.get("player_id", ""))
    if pid in ctx.player_states:
        ctx.player_states[pid].exchange_level += 1
    cost_w = parse_resource_html(args.get("workers_cost", "")).get("workers", 0)
    cost_c = parse_resource_html(args.get("coins_cost", "")).get("coins", 0)
    cost_p = parse_resource_html(args.get("priests_cost", "")).get("priests", 0)
    vp = parse_resource_html(args.get("score_inc", "")).get("vp", 0)
    _spend(ctx, pid, workers=cost_w, coins=cost_c, priests=cost_p)
    if vp:
        inc_vp_source(ctx, pid, "vp_track_advances", vp)
        _gen(ctx, pid, vp=vp)
    _sync_score(args, pid, ctx)
    return _make_move(ctx, pid, action_type="advance_exchange", description="Advance exchange rate",
                      cost_workers=cost_w, cost_coins=cost_c, cost_priests=cost_p, gain_vp=vp)


# ---------------------------------------------------------------------------
# Town, tile, card handlers
# ---------------------------------------------------------------------------

def handle_town_founded(event, args, ctx):
    pid = str(args.get("player_id", ""))
    hex_coord = extract_hex(args, ctx)
    town_id = str(args.get("town_id", ""))
    inc_round_action(ctx, pid, "towns_founded")
    ctx.last_town_id = town_id
    move = _make_move(ctx, pid,
        action_type="found_town", description="Found town",
        hex_coord=hex_coord, town_id=town_id,
    )
    ctx.last_town_move = move
    return move


def handle_town_bonus(event, args, ctx):
    pid = str(args.get("player_id", ""))
    vp = parse_resource_html(args.get("score_inc", "")).get("vp", 0)
    inc_vp_source(ctx, pid, "vp_towns", vp)
    town_id = ctx.last_town_id
    workers = parse_resource_html(args.get("workers_income", "")).get("workers", 0)
    coins = parse_resource_html(args.get("coins_income", "")).get("coins", 0)
    priests = parse_resource_html(args.get("priests_income", "")).get("priests", 0)
    power = parse_resource_html(args.get("power_income", "")).get("power", 0)
    parts = [f"{vp}vp"]
    if priests: parts.append(f"{priests}priest")
    if workers: parts.append(f"{workers}workers")
    if coins: parts.append(f"{coins}coins")
    if power: parts.append(f"{power}power")
    town_name = "_".join(parts)
    ctx.player_town_tiles.setdefault(pid, []).append(
        town_name or f"town_{town_id}")
    # Fill the found_town row this bonus belongs to (townBonus follows it)
    tm = ctx.last_town_move
    if tm is not None and tm.player_id == pid and tm.town_vp is None:
        tm.town_vp = vp
        tm.town_resources = "_".join(parts[1:])
        tm.tile_or_card = town_name
    _gen(ctx, pid,
         coins=coins, workers=workers, priests=priests,
         power=power, vp=vp)
    _sync_score(args, pid, ctx)
    return None


def handle_favor_tile(event, args, ctx):
    pid = str(args.get("player_id", ""))
    favor_type = str(args.get("favor_type", ""))
    tile_name = FAVOR_TYPE_NAMES.get(favor_type, f"favor_{favor_type}")
    ctx.player_favor_tiles.setdefault(pid, []).append(tile_name)
    return _make_move(ctx, pid,
        action_type="choose_favor_tile",
        description=f"Choose favor tile: {tile_name}",
        tile_or_card=tile_name,
    )


def handle_bonus_card(event, args, ctx):
    pid = str(args.get("player_id", ""))
    bonus_id = str(args.get("bonus_id", ""))
    btype = ctx.bonus_id_to_type.get(bonus_id, "")
    card_name = ctx.bonus_type_to_name.get(
        btype, f"bonus_{bonus_id}")
    ctx.player_bonus_card[pid] = card_name
    coins = parse_resource_html(
        args.get("coins_gain", "")).get("coins", 0)
    if coins > 0:
        _gen(ctx, pid, coins=coins)
    at = ("select_bonus_card" if ctx.current_round == 0
          else "choose_bonus_card")
    return _make_move(ctx, pid,
        action_type=at,
        description=f"Choose bonus card: {card_name}",
        tile_or_card=card_name, gain_coins=coins,
    )


# ---------------------------------------------------------------------------
# Scoring, passing, income handlers
# ---------------------------------------------------------------------------

def handle_player_passed(event, args, ctx):
    # Also handles firstPlayerChanged: in rounds 1-5 the first player to pass
    # gets that event instead of playerPassed.
    pid = str(args.get("player_id", ""))
    if pid in ctx.pass_order:
        return None
    ctx.pass_counter += 1
    ctx.pass_order[pid] = ctx.pass_counter
    return _make_move(ctx, pid, action_type="pass", description="Pass")


def classify_scoring_node(scoring_node: str, args: Dict) -> str:
    if not scoring_node:
        return "vp_track_advances"
    if scoring_node.startswith("scoring_tile_holder"):
        return "vp_round_scoring"
    if scoring_node.startswith("favor_tile"):
        return "vp_favor_tiles"
    if scoring_node.startswith("bonus_card"):
        return "vp_bonus_cards"
    if scoring_node.startswith(("ability_clicker", "terrain_space_clicker")):
        return "vp_faction_ability"
    if any(cult in scoring_node for cult in ("firecult", "watercult", "earthcult", "aircult")):
        return "vp_cult_final"
    if scoring_node.startswith("struct_"):
        return "vp_area_final"
    if scoring_node.startswith("coins_icon"):
        return "vp_resources_final"
    return "vp_track_advances"


def handle_update_score(event, args, ctx):
    pid = str(args.get("player_id", ""))
    delta = int(args.get("score_delta", 0))
    new_score = int(args.get("newScore", 0))
    scoring_node = args.get("scoring_node", "")
    if pid in ctx.player_states:
        # Ancient replays occasionally mis-report score_delta vs the
        # authoritative newScore movement. When the event claims real scoring
        # (nonzero delta), trust the tracked-score difference instead.
        # delta==0 events (starting-VP set, post-ability syncs) keep arg-based
        # behavior — their VP is bucketed by the originating handlers.
        if delta != 0:
            actual = new_score - ctx.player_states[pid].score
            if actual != delta:
                delta = actual
        ctx.player_states[pid].score = new_score
    category = classify_scoring_node(scoring_node, args)
    inc_vp_source(ctx, pid, category, delta)
    if delta > 0:
        _gen(ctx, pid, vp=delta)
    elif delta < 0:
        _spend(ctx, pid, vp=-delta)
    if category == "vp_round_scoring" and ctx.current_round > 0:
        ctx.round_scoring_vp.setdefault(pid, 0)
        ctx.round_scoring_vp[pid] += delta
    if delta != 0:
        at = ("round_scoring" if category == "vp_round_scoring"
              else "other")
        return _make_move(ctx, pid,
            action_type=at,
            description=event.get("log", ""), gain_vp=delta,
        )
    return None


def handle_final_scoring(event, args, ctx):
    pid = str(args.get("player_id", ""))
    delta = int(args.get("score_delta", 0))
    new_score = int(args.get("newScore", 0))
    if pid in ctx.player_states:
        ctx.player_states[pid].score = new_score
    # Area/network final scoring. Detect by scoring_node ("struct_<n>"), NOT by
    # "connected_scoring_type": that key is only present in some client versions,
    # while others emit the same event with just "connected_number". Requiring it
    # missed area scoring for ~22% of base / ~38% of F&I players, leaving
    # network_size=0 and mis-bucketing the area VP into vp_cult_final.
    scoring_node = args.get("scoring_node", "")
    category = "vp_cult_final"
    if scoring_node.startswith("struct_"):
        category = "vp_area_final"
        connected = int(args.get("connected_number", 0))
        ctx.vp_sources.setdefault(pid, {})
        ctx.vp_sources[pid]["_largest_connected"] = max(
            ctx.vp_sources[pid].get("_largest_connected", 0),
            connected)
    elif "coins_icon" in scoring_node:
        category = "vp_resources_final"
    inc_vp_source(ctx, pid, category, delta)
    # Resource scoring is a conversion (coins -> VP)
    if category == "vp_resources_final" and delta > 0:
        _convert(ctx, pid, vp=delta)
    elif delta > 0:
        _gen(ctx, pid, vp=delta)
    return _make_move(ctx, pid,
        action_type="final_scoring",
        description=event.get("log", ""),
        gain_vp=delta,
    )


def handle_some_income(event, args, ctx, is_cult_bonus=None):
    pid = str(args.get("player_id", ""))
    coins = parse_resource_html(args.get("coins_income", "")).get("coins", 0)
    workers = parse_resource_html(args.get("workers_income", "")).get("workers", 0)
    priests = parse_resource_html(args.get("priests_income", "")).get("priests", 0)
    power = parse_resource_html(args.get("power_income", "")).get("power", 0)

    if is_cult_bonus is None:
        is_cult_bonus = "Cult bonus" in str(args.get("addendum", ""))
    if is_cult_bonus:
        cb = ctx.round_cult_bonus.setdefault(
            pid, {"coins": 0, "workers": 0, "priests": 0,
                  "power": 0, "spades": 0})
        cb["coins"] += coins
        cb["workers"] += workers
        cb["priests"] += priests
        cb["power"] += power
    else:
        ri = ctx.round_income.setdefault(
            pid, {"coins": 0, "workers": 0, "priests": 0,
                  "power": 0})
        ri["coins"] += coins
        ri["workers"] += workers
        ri["priests"] += priests
        ri["power"] += power

    _gen(ctx, pid,
         coins=coins, workers=workers,
         priests=priests, power=power)
    at = ("receive_cult_bonus" if is_cult_bonus
          else "receive_income")
    return _make_move(ctx, pid,
        action_type=at,
        description="Cult bonus" if is_cult_bonus
                    else "Receive income",
        gain_coins=coins, gain_workers=workers,
        gain_priests=priests, gain_power=power,
    )


def add_cult_bonus_spades(args, pid, ctx):
    """Record cult-bonus spades from the spade_income arg; returns the amount."""
    spades = parse_resource_html(args.get("spade_income", "")).get("spade", 0)
    if spades > 0:
        cb = ctx.round_cult_bonus.setdefault(
            pid, {"coins": 0, "workers": 0, "priests": 0,
                  "power": 0, "spades": 0})
        cb["spades"] += spades
        _gen(ctx, pid, spades=spades)
    return spades


def handle_cult_bonus(event, args, ctx):
    """Pre-mid-2022 cult bonus event (later replays use someIncome with a
    "(Cult bonus)" addendum, plus updateCounters for spades). Fires once per
    cult-bonus slot per player, mostly with all-zero amounts."""
    pid = str(args.get("player_id", ""))
    add_cult_bonus_spades(args, pid, ctx)
    if not any(parse_resource_html(args.get(f, "")).get(r, 0)
               for r, f in [("coins", "coins_income"), ("workers", "workers_income"),
                            ("priests", "priests_income"), ("power", "power_income")]):
        return None
    return handle_some_income(event, args, ctx, is_cult_bonus=True)


def handle_conversions(event, args, ctx):
    pid = str(args.get("player_id", ""))
    new_score = args.get("newScore")
    if new_score is not None and pid in ctx.player_states:
        new_score = int(new_score)
        vp_delta = new_score - ctx.player_states[pid].score
        ctx.player_states[pid].score = new_score
        if vp_delta != 0:
            # VP changes during conversions:
            # - Negative: Alchemists VP→coin (faction ability)
            # - Positive during action phase: scoring tile VP triggered
            #   alongside conversions (round scoring)
            # - Positive during final_scoring: resource→VP (resource scoring)
            # - Positive, announced by a preceding Alchemists coins→VP
            #   message: their 2:1 resource scoring, not round scoring
            alch_vp = min(ctx.alch_vp_pending.pop(pid, 0), max(vp_delta, 0))
            if alch_vp:
                inc_vp_source(ctx, pid, "vp_resources_final", alch_vp)
                _gen(ctx, pid, vp=alch_vp)
                vp_delta -= alch_vp
            if vp_delta < 0:
                inc_vp_source(ctx, pid, "vp_faction_ability", vp_delta)
                _spend(ctx, pid, vp=-vp_delta)
                ctx.round_vp_faction[pid] = ctx.round_vp_faction.get(pid, 0) + (-vp_delta)
            elif vp_delta == 0:
                pass
            elif ctx.current_phase == "final_scoring":
                inc_vp_source(ctx, pid, "vp_resources_final", vp_delta)
                _gen(ctx, pid, vp=vp_delta)
            else:
                inc_vp_source(ctx, pid, "vp_round_scoring", vp_delta)
                _gen(ctx, pid, vp=vp_delta)
                if ctx.current_round > 0:
                    ctx.round_scoring_vp.setdefault(pid, 0)
                    ctx.round_scoring_vp[pid] += vp_delta

    # Track resource conversions (net per resource)
    cost, gain = {}, {}
    for res, field in [("power", "power_spent"),
                       ("workers", "workers_spent"),
                       ("priests", "priests_spent")]:
        amt = parse_resource_html(
            args.get(field, "")).get(res, 0)
        if amt > 0:
            cost[res] = amt
            _convert(ctx, pid, **{res: -amt})
    for res, field in [("coins", "coins_gained"),
                       ("workers", "workers_gained"),
                       ("priests", "priests_gained")]:
        amt = parse_resource_html(
            args.get(field, "")).get(res, 0)
        if amt > 0:
            gain[res] = amt
            _convert(ctx, pid, **{res: amt})
    # Most conversionsApplied events are empty score/counter carriers
    if not cost and not gain:
        return None
    return _make_move(ctx, pid,
        action_type="convert",
        description="Convert {} -> {}".format(
            ", ".join(f"{v} {k}" for k, v in cost.items()),
            ", ".join(f"{v} {k}" for k, v in gain.items())),
        cost_power=cost.get("power", 0), cost_workers=cost.get("workers", 0),
        cost_priests=cost.get("priests", 0),
        gain_coins=gain.get("coins", 0), gain_workers=gain.get("workers", 0),
        gain_priests=gain.get("priests", 0),
    )


def handle_alchemists_conversion(event, args, ctx):
    """Alchemists ability, logged as a justAMessage.

    1 VP -> 1 coin (vp_spent/coins_gained) is a conversion: books the coins
    and emits a row; the VP side is bucketed by the conversionsApplied event
    that always follows (it carries newScore).

    2 coins -> 1 VP (coins_spent/vp_gained) is treated as end-game resource
    scoring at 2:1 rather than a conversion: no row, no coins_converted, VP
    into vp_resources_final, and round-end snapshots are taken as if it had
    not happened yet (see apply_alch_cashout)."""
    pid = str(args.get("player_id", ""))
    vp_spent = parse_resource_html(args.get("vp_spent", "")).get("vp", 0)
    c_gain = parse_resource_html(args.get("coins_gained", "")).get("coins", 0)
    c_spent = parse_resource_html(args.get("coins_spent", "")).get("coins", 0)
    vp_gain = parse_resource_html(args.get("vp_gained", "")).get("vp", 0)
    if not (vp_spent or c_gain or c_spent or vp_gain):
        return None
    if vp_gain or c_spent:
        ctx.alch_vp_pending[pid] = ctx.alch_vp_pending.get(pid, 0) + vp_gain
        cash = ctx.alch_cashout.setdefault(pid, [0, 0])
        cash[0] += c_spent
        cash[1] += vp_gain
    if not (vp_spent or c_gain):
        return None
    _convert(ctx, pid, coins=c_gain)
    return _make_move(ctx, pid,
        action_type="convert",
        description=f"Alchemists: {vp_spent} vp -> {c_gain} coins",
        gain_coins=c_gain, gain_vp=-vp_spent,
    )


def apply_alch_cashout(states: Dict[str, TMPlayerState], ctx: ParseContext):
    """Put Alchemists' cashed-out coins back (and take the VP off) in a
    round-end snapshot: that trade is scored as end-game resource scoring."""
    for pid, (coins, vp) in ctx.alch_cashout.items():
        if pid in states:
            states[pid].coins += coins
            states[pid].score -= vp


# ---------------------------------------------------------------------------
# Leech offers
# ---------------------------------------------------------------------------
# A leech phase runs from game state 44 (active_player = the builder) to the
# next one or the next round. Inside it: accept events (a free 1-power leech
# is auto-accepted, logged before the offer and sometimes with no offer at
# all), at most one offer listing who must decide, and decline messages.

def leech_close(ctx):
    """Finish the open leech phase, turning it into TMLeechOffer rows."""
    ph = ctx.leech_phase
    ctx.leech_phase = None
    if ph is None:
        return
    targets = {}
    for t, (off, cap) in ph["offers"].items():
        targets[t] = (off, cap, 0) + ph["resp"].get(t, ("none", 0, 0))
    for t, resp in ph["resp"].items():
        if t not in targets:   # auto-accepted, never listed as an offer
            targets[t] = (resp[1], 0, 1) + resp
    n = sum(1 for v in targets.values() if v[0] > 0)
    for t, (off, cap, auto, resp, gained, vp) in targets.items():
        ctx.leech_offers.append(TMLeechOffer(
            offer_id=ph["offer_id"], round_number=ph["round"],
            turn_number=ph["turn"], builder_id=ph["builder"], target_id=t,
            n_offered=n, offered=off, cap=cap, auto=auto,
            response=resp, gained=gained, vp_cost=vp))


def leech_state_change(args, ctx):
    """Feed a gameStateChange: state 44 opens a phase; a state whose inner
    args carry power_bonuses/power_caps is the offer."""
    if str(args.get("id")) == "44":
        leech_close(ctx)
        ctx.leech_counter += 1
        ctx.leech_phase = {
            "offer_id": ctx.leech_counter, "round": ctx.current_round,
            "turn": ctx.turn_number or None,
            "builder": str(args.get("active_player", "")),
            "offers": {}, "resp": {}}
        return
    inner = args.get("args")
    if (ctx.leech_phase is None or not isinstance(inner, dict)
            or not isinstance(inner.get("power_bonuses"), dict)):
        return
    caps = inner.get("power_caps")
    caps = caps if isinstance(caps, dict) else {}
    for t, amount in inner["power_bonuses"].items():
        ctx.leech_phase["offers"][str(t)] = (
            _safe_int(amount) or 0, _safe_int(caps.get(t)) or 0)


def leech_response(ctx, pid, response, gained=0, vp_cost=0):
    ph = ctx.leech_phase
    if ph is None or pid in ph["resp"] or pid == ph["builder"]:
        return
    if response == "decline" and pid not in ph["offers"]:
        return
    ph["resp"][pid] = (response, gained, vp_cost)


def handle_power_via_structures(event, args, ctx):
    pid = str(args.get("player_id", ""))
    hex_coord = extract_hex(args, ctx)
    pw = parse_resource_html(
        args.get("power_income", "")).get("power", 0)
    vp_cost = parse_resource_html(
        args.get("vp_price", "")).get("vp", 0)
    log = event.get("log", "") if isinstance(event, dict) else ""
    if " gets " in log or " pays " in log:
        leech_response(ctx, pid, "accept", pw,
                       vp_cost if " pays " in log else 0)
    new_score = args.get("newScore")
    if new_score is not None and pid in ctx.player_states:
        prev = ctx.player_states[pid].score
        ctx.player_states[pid].score = int(new_score)
        # Some faction abilities (e.g. Wisps stronghold) grant VP on a leech
        # event with no dedicated arg — the gain only shows up in newScore.
        # Bucket any movement beyond the advertised -vp_cost as ability VP.
        residual = int(new_score) - prev + vp_cost
        if residual:
            inc_vp_source(ctx, pid, "vp_faction_ability", residual)
            _gen(ctx, pid, vp=residual)
    if vp_cost > 0:
        inc_vp_source(ctx, pid, "vp_power_leaching", -vp_cost)
        _spend(ctx, pid, vp=vp_cost)
        ctx.round_vp_leach[pid] = ctx.round_vp_leach.get(pid, 0) + vp_cost
    if pw > 0:
        ctx.round_power_gained.setdefault(
            pid, {"structures": 0, "cults": 0, "other": 0})
        ctx.round_power_gained[pid]["structures"] += pw
        _gen(ctx, pid, power=pw)
    if vp_cost > 0 or pw > 0:
        return _make_move(ctx, pid,
            action_type="power_via_structures",
            description=f"Gain {pw} power (cost {vp_cost} VP)",
            hex_coord=hex_coord,
            gain_power=pw, gain_vp=-vp_cost,
        )
    return None


def handle_update_counters(event, args, ctx):
    if "counters" in args and isinstance(args["counters"], dict):
        update_counters(args["counters"], ctx)
    # Some faction abilities are only logged on an updateCounters event.
    log = event.get("log", "") if isinstance(event, dict) else ""
    if not log:
        return None
    pid = str(args.get("player_id", ""))
    if "${coins_bonus}" in log:      # Conspirators ability
        _gen(ctx, pid, coins=parse_resource_html(
            args.get("coins_bonus", "")).get("coins", 0))
    elif "${coins_gain}" in log:     # Gold Diggers stronghold action
        coins = parse_resource_html(args.get("coins_gain", "")).get("coins", 0)
        _gen(ctx, pid, coins=coins)
        marker = stronghold_marker(ctx, pid)
        if marker is not None:
            marker.gain_coins += coins
            return None
        move = _make_move(ctx, pid,
            action_type="special_action",
            description="Special action (stronghold)",
            special_action_type="stronghold", gain_coins=coins)
        ctx.turn_sh_marker = (pid, move)
        return move
    elif "Spades to transform" in log:   # Wisps ability, Halflings stronghold
        m = re.search(r"gains (\d+) Spades", log)
        _gen(ctx, pid, spades=_safe_int(args.get("nb_spades"))
             or (int(m.group(1)) if m else 0))
    return None


def _safe_int(v):
    if v is None or v == "-" or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# Maps counter field prefixes to TMPlayerState attributes
_COUNTER_FIELDS = {
    "coins_count": "coins",
    "workers_count": "workers",
    "power1_count": "power_bowl1",
    "power2_count": "power_bowl2",
    "power3_count": "power_bowl3",
    "icc": "income_coins",
    "iwc": "income_workers",
    "iptc": "income_priests",
    "ipc": "income_power",
}


def update_counters(counters: Dict, ctx: ParseContext):
    # BGA sends counters in two formats:
    # Format 1: {counter_name_PID: {counter_name: "coins_count_PID", counter_value: "20"}}
    # Format 2: {PID: {coins_count: "13", power1_count: "4", icc: 0, ...}}
    player_updates: Dict[str, Dict[str, int]] = {}
    for key, cdata in counters.items():
        if not isinstance(cdata, dict):
            continue
        if "counter_value" in cdata:
            # Format 1: nested counter_name/counter_value
            counter_name = str(cdata.get("counter_name", key))
            val = _safe_int(cdata.get("counter_value"))
            if val is None:
                continue
            for prefix, attr in _COUNTER_FIELDS.items():
                if counter_name.startswith(prefix + "_"):
                    pid = counter_name[len(prefix) + 1:]
                    player_updates.setdefault(pid, {})[attr] = val
                    break
        else:
            # Format 2: key is player ID, values are flat fields
            pid = key
            for field_name, attr in _COUNTER_FIELDS.items():
                val = _safe_int(cdata.get(field_name))
                if val is not None:
                    player_updates.setdefault(pid, {})[attr] = val

    for pid, updates in player_updates.items():
        ctx.player_states.setdefault(pid, TMPlayerState())
        st = ctx.player_states[pid]
        for attr, val in updates.items():
            setattr(st, attr, val)


def sync_workers(args: Dict, ctx: ParseContext):
    """Update each player's worker stock from the event's `workers` tokens.

    BGA has no workers counter: workers are 65 tokens, sent as
    {worker_id: {"player_id": owner-or-None}}. Build/upgrade/transform events
    carry all of them; income, bonus, conversion and power-action events carry
    only the tokens that moved. So keep an owner per token and count."""
    tokens = args.get("workers")
    if not isinstance(tokens, dict) or not tokens:
        return
    for tid, tok in tokens.items():
        if isinstance(tok, dict) and "player_id" in tok:
            owner = tok["player_id"]
            ctx.worker_tokens[str(tid)] = None if owner is None else str(owner)
    held: Dict[str, int] = {}
    for owner in ctx.worker_tokens.values():
        if owner is not None:
            held[owner] = held.get(owner, 0) + 1
    for pid, st in ctx.player_states.items():
        st.workers = held.get(pid, 0)


def sync_priests(args: Dict, ctx: ParseContext):
    """Set priests in hand from the event's `priests` tokens.

    Each player has 7 priest tokens. An event carries the acting player's
    seven (all 28 at setup). In hand = out of the supply, not on a cult
    order space, not in the Treasury."""
    tokens = args.get("priests")
    if not isinstance(tokens, dict) or not tokens:
        return
    held: Dict[str, int] = {}
    for tok in tokens.values():
        if not isinstance(tok, dict) or tok.get("player_id") is None:
            continue
        owner = str(tok["player_id"])
        in_hand = (str(tok.get("priest_in_supply")) == "0"
                   and tok.get("cos_id") is None
                   and str(tok.get("priest_in_treasury", "0")) != "1")
        held[owner] = held.get(owner, 0) + in_hand
    for pid, n in held.items():
        if pid in ctx.player_states:
            ctx.player_states[pid].priests = n


# ---------------------------------------------------------------------------
# Fan-faction handlers
# ---------------------------------------------------------------------------

def handle_advance_income_track(event, args, ctx):
    pid = str(args.get("player_id", ""))
    # Chash Dallah's income-track advancement grants VP (1/2/3/4 for levels 1-4).
    # The trailing updateScore has score_delta=0 (no double-count).
    vp = parse_resource_html(args.get("score_inc", "")).get("vp", 0)
    cost_w = parse_resource_html(args.get("workers_cost", "")).get("workers", 0)
    cost_c = parse_resource_html(args.get("coins_cost", "")).get("coins", 0)
    _spend(ctx, pid, workers=cost_w, coins=cost_c)
    if vp:
        inc_vp_source(ctx, pid, "vp_faction_ability", vp)
        _gen(ctx, pid, vp=vp)
    _sync_score(args, pid, ctx)
    return _make_move(ctx, pid, action_type="advance_income_track",
                      description="Advance income track",
                      cost_workers=cost_w, cost_coins=cost_c, gain_vp=vp)


def handle_swap_cult_track(event, args, ctx):
    pid = str(args.get("player_id", ""))
    return _make_move(ctx, pid, action_type="swap_cult_tracks", description="Swap cult tracks (Magic Lamp)")


def handle_favor_tile_lost(event, args, ctx):
    pid = str(args.get("player_id", ""))
    favor_type = str(args.get("favor_type", ""))
    tile_name = FAVOR_TYPE_NAMES.get(favor_type, f"favor_{favor_type}")
    tiles = ctx.player_favor_tiles.get(pid, [])
    if tile_name in tiles:
        tiles.remove(tile_name)
    return None


def handle_add_new_bonus_card(event, args, ctx):
    card = args.get("new_bonus_card", {})
    if isinstance(card, dict):
        bid = str(card.get("bonus_id", ""))
        btype = str(card.get("bonus_type", ""))
        if bid and btype:
            ctx.bonus_id_to_type[bid] = btype
            from .tm_constants import BONUS_TYPE_NAMES
            ctx.bonus_type_to_name[btype] = BONUS_TYPE_NAMES.get(
                btype, f"bonus_{btype}")
    return None


def handle_workers_income(event, args, ctx):
    """workersIncome: Swarmlings gain 3 workers on founding a town."""
    pid = str(args.get("player_id", ""))
    w = parse_resource_html(args.get("workers_income", "")).get("workers", 0)
    _gen(ctx, pid, workers=w)
    return None


def handle_workers_for_priests(event, args, ctx):
    """workersForPriests: Darklings stronghold trades up to 3 workers for priests."""
    pid = str(args.get("player_id", ""))
    w = parse_resource_html(args.get("workers_cost", "")).get("workers", 0)
    pr = parse_resource_html(args.get("priests_gain", "")).get("priests", 0)
    if not (w or pr):
        return None
    _convert(ctx, pid, workers=-w, priests=pr)
    return _make_move(ctx, pid,
        action_type="convert",
        description=f"Darklings: {w} workers -> {pr} priests",
        cost_workers=w, gain_priests=pr,
    )


def handle_gain_resources(event, args, ctx):
    """gainRessources: Goblins spend a Treasure token, as their action, for
    power/coins/workers per structure of a chosen type."""
    pid = str(args.get("player_id", ""))
    coins = parse_resource_html(args.get("coins_gain", "")).get("coins", 0)
    workers = parse_resource_html(args.get("workers_gain", "")).get("workers", 0)
    power = parse_resource_html(args.get("power_gain", "")).get("power", 0)
    _gen(ctx, pid, coins=coins, workers=workers, power=power)
    if power > 0:
        ctx.round_power_gained.setdefault(
            pid, {"structures": 0, "cults": 0, "other": 0})
        ctx.round_power_gained[pid]["other"] += power
    return _make_move(ctx, pid,
        action_type="faction_action",
        description="Goblins: spend Treasure token",
        gain_coins=coins, gain_workers=workers, gain_power=power)


def handle_gain_priests(event, args, ctx):
    """gainPriests: Dynion Geifr gain 2 priests on building the stronghold."""
    pid = str(args.get("player_id", ""))
    _gen(ctx, pid, priests=parse_resource_html(
        args.get("priests_gained", "")).get("priests", 0))
    return None


def handle_new_power_tokens(event, args, ctx):
    """newPowerTokens: The Enlightened buy new power tokens (bowl 1) with
    coins, 1:1. Children of the Wyrm use the same event with no coin cost."""
    pid = str(args.get("player_id", ""))
    coins = parse_resource_html(args.get("coins_spent", "")).get("coins", 0)
    tokens = parse_resource_html(args.get("power_earned", "")).get("power", 0)
    if coins <= 0:
        return None
    _convert(ctx, pid, coins=-coins)
    return _make_move(ctx, pid,
        action_type="convert",
        description=f"The Enlightened: {coins} coins -> {tokens} power tokens",
        cost_coins=coins)


def handle_update_treasury(event, args, ctx):
    """updateTreasury: Treasurers put resources into the Treasury.

    Only "(Conversion)" deposits come off the board. The others ("(Income)",
    "(Bonus card)", "(Town bonus)", "(Power action)") are withheld before the
    resources arrive, and the granting event already reports the net amount.
    The Treasury comes back doubled as a someIncome right after emptyTreasury."""
    addendum = str(args.get("addendum", ""))
    pid = str(args.get("player_id", ""))
    if "Power action" in addendum:
        return _treasury_power_action(args, pid, ctx)
    if "Conversion" not in addendum:
        return None
    for res in ("coins", "workers", "priests"):
        amt = parse_resource_html(args.get(f"{res}_income", "")).get(res, 0)
        if amt > 0:
            _convert(ctx, pid, **{res: -amt})
    return None


# Standard power actions: gained resource -> (label, power cost)
_POWER_ACTIONS = {"priests": ("priest", 3), "workers": ("workers", 4),
                  "coins": ("coins", 4)}


def _treasury_power_action(args, pid, ctx):
    """A Treasurers power action with proceeds going into the Treasury fires
    no powerActionConvert, only this deposit. Book the power action here.
    Nothing is generated: the deposit never reaches the board."""
    for res, (label, pw_cost) in _POWER_ACTIONS.items():
        dep = parse_resource_html(args.get(f"{res}_income", "")).get(res, 0)
        if dep <= 0:
            continue
        _spend(ctx, pid, power=pw_cost)
        inc_round_action(ctx, pid, "power_actions_used")
        ctx.round_power_actions.setdefault(pid, []).append(label)
        return _make_move(ctx, pid,
            action_type="power_action",
            description=f"Power action: {label} ({dep} to Treasury)",
            power_action_type=label, cost_power=pw_cost)
    return None


def handle_token_placed(event, args, ctx):
    """tokenPlaced: Children of the Wyrm stronghold action — sacrifice power
    tokens to place them on two board spaces."""
    pid = str(args.get("player_id", ""))
    hexes = [str(b) for b in (args.get("bts_id_1"), args.get("bts_id_2")) if b]
    return _make_move(ctx, pid,
        action_type="faction_action",
        description="Children of the Wyrm: place power tokens",
        hex_coord=hexes[0] if hexes else None,
        secondary_hex=hexes[1] if len(hexes) > 1 else None)


def handle_power_income(event, args, ctx):
    """Handle powerIncome events (e.g. Alchemists SH: 2pw per spade)."""
    pid = str(args.get("player_id", ""))
    pw = parse_resource_html(args.get("power_income", "")).get("power", 0)
    if pw > 0:
        ctx.round_power_gained.setdefault(
            pid, {"structures": 0, "cults": 0, "other": 0})
        ctx.round_power_gained[pid]["other"] += pw
        _gen(ctx, pid, power=pw)
    return None


def noop(event, args, ctx):
    return None


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

EVENT_HANDLERS = {
    # Setup
    "factionPositionSelected": handle_faction_selected,
    "factionBoardSwapped": handle_faction_board_swapped,
    "landscapePlaced": handle_landscape_placed,
    "updateScoreSmallDelay": handle_update_score_small_delay,
    # Core actions
    "dwellingPlaced": handle_dwelling_placed,
    "terrainTransformed": handle_terrain_transformed,
    "structureUpgraded": handle_structure_upgraded,
    "advanceCultTrack": handle_advance_cult,
    "orderAPriest": handle_order_priest,
    "powerActionConvert": handle_power_action,
    "powerActionBridge": handle_power_action_bridge,
    "specialActionUsed": handle_special_action,
    "advanceShippingTrack": handle_advance_shipping,
    "advanceExchangeTrack": handle_advance_exchange,
    # Towns & tiles
    "townFounded": handle_town_founded,
    "townBonus": handle_town_bonus,
    "favorTileChosen": handle_favor_tile,
    "bonusCardChosen": handle_bonus_card,
    # Passing & scoring
    "playerPassed": handle_player_passed,
    "updateScore": handle_update_score,
    "finalScoring": handle_final_scoring,
    # Income & conversions
    "someIncome": handle_some_income,
    "cultBonus": handle_cult_bonus,
    "conversionsApplied": handle_conversions,
    "conversionsAppliedWithDelay": handle_conversions,
    "powerViaStructures": handle_power_via_structures,
    # State tracking
    "updateCounters": handle_update_counters,
    # Fan-faction events
    "advanceIncomeTrack": handle_advance_income_track,
    "swapCultTrack": handle_swap_cult_track,
    "favorTileLost": handle_favor_tile_lost,
    "tokenPlaced": handle_token_placed,
    # Silently consumed events
    "updateTreasury": handle_update_treasury,
    "emptyTreasury": noop, "updateExchangeTrack": noop,
    "newPowerTokens": handle_new_power_tokens, "addNewBonusCard": handle_add_new_bonus_card, "startingTerrainChosen": noop,
    "terrainRingUpdated": noop, "someCost": noop,
    "gainRessources": handle_gain_resources,
    "gainPriests": handle_gain_priests, "workersForPriests": handle_workers_for_priests,
    "workersIncome": handle_workers_income,
    "createSomeWorkers": noop, "createLandBridges": noop, "simpleNote": noop,
    "wakeupPlayers": noop, "newCustomBoard": noop, "powerIncome": handle_power_income,
    "actionUsed": handle_action_used, "returnActionTokens": noop, "coinsOnBonusCards": noop,
    "firstPlayerChanged": handle_player_passed, "factionBoardChosen": noop,
    "timeJokerUsed": noop, "undoRestoreDISAB": noop,
    "tileScored": noop,
}
