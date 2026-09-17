"""Event handlers for Terra Mystica parser."""

import re
from typing import Dict, Optional

from .tm_constants import CULT_NAMES, FACTIONS, FAVOR_TYPE_NAMES
from .tm_models import ParseContext, TMMove, TMPlayerState


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
    """Extract hex coordinate from event args, translated to standard map labels.

    BGA stores coordinates in bts_id (most events) or new_struct.bts_id (upgrades).
    If ctx.hex_map is available, translates from BGA internal coords to standard
    map labels (rivers skipped, hexes numbered sequentially per row).
    """
    bts_id = args.get("bts_id")
    if not bts_id:
        new_struct = args.get("new_struct")
        if isinstance(new_struct, dict) and new_struct.get("bts_id"):
            bts_id = new_struct["bts_id"]
    if not bts_id:
        return None
    bts_id = str(bts_id)
    if ctx and ctx.hex_map:
        return ctx.hex_map.get(bts_id, bts_id)
    return bts_id


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
    return TMMove(
        move_number=ctx.move_counter,
        round_number=ctx.current_round,
        phase=ctx.current_phase,
        player_id=pid,
        player_name=ctx.player_map.get(pid, ""),
        faction=ctx.factions.get(pid, ""),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Setup handlers
# ---------------------------------------------------------------------------

def handle_faction_selected(event, args, ctx):
    pid = str(args.get("player_id", ""))
    name = args.get("player_name", "")
    ctx.player_map[pid] = name
    ctx.factions[pid] = args.get("faction_type", "")
    ctx.terrains[pid] = args.get("faction_terrain_type", "")
    ctx.player_states.setdefault(pid, TMPlayerState())
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
    _spend(ctx, pid, workers=cost_w, coins=cost_c)
    return _make_move(ctx, pid,
        action_type="place_initial_dwelling" if ctx.current_round == 0 else "build_dwelling",
        description=args.get("struct_name", "Dwelling"),
        hex_coord=hex_coord, structure_type="dwelling",
        cost_workers=cost_w, cost_coins=cost_c,
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
    # transform_cost = spades icon; other_cost = workers/priests spent
    spades = parse_resource_html(
        args.get("transform_cost", "")).get("spade", 0)
    other = parse_resource_html(args.get("other_cost", ""))
    w_cost = other.get("workers", 0)
    p_cost = other.get("priests", 0)
    # Workers/priests spent to generate spades
    _spend(ctx, pid, workers=w_cost, priests=p_cost)
    _gen(ctx, pid, spades=spades)
    inc_round_action(ctx, pid, "terrain_transforms")
    return _make_move(ctx, pid,
        action_type="transform_terrain",
        description=f"Transform {terrain_from} -> {terrain_to}",
        hex_coord=hex_coord,
        terrain_from=terrain_from, terrain_to=terrain_to,
        spades_used=spades or None,
        cost_workers=w_cost, cost_priests=p_cost,
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
    cost = parse_resource_html(args.get("resource_cost", ""))
    w, c = cost.get("workers", 0), cost.get("coins", 0)
    _spend(ctx, pid, workers=w, coins=c)
    inc_round_action(ctx, pid, "structures_upgraded")
    if new_type:
        inc_round_action(ctx, pid, f"{new_type}_built")
    return _make_move(ctx, pid,
        action_type="upgrade_structure",
        description=(f"Upgrade {args.get('old_struct_name', old_type)}"
                     f" to {args.get('new_struct_name', new_type)}"),
        hex_coord=hex_coord, structure_type=new_type,
        upgraded_from=old_type, cost_workers=w, cost_coins=c,
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
    _spend(ctx, pid, power=pw_cost)
    _gen(ctx, pid, workers=g_w, coins=g_c, priests=g_p)
    if spades > 0:
        _gen(ctx, pid, spades=spades)
    inc_round_action(ctx, pid, "power_actions_used")
    ctx.round_power_actions.setdefault(pid, []).append(label)
    return _make_move(ctx, pid,
        action_type="power_action",
        description=f"Power action: {label}",
        power_action_type=label,
        cost_power=pw_cost,
        gain_workers=g_w, gain_coins=g_c, gain_priests=g_p,
    )


def handle_power_action_bridge(event, args, ctx):
    pid = str(args.get("player_id", ""))
    cost = parse_resource_html(args.get("power_cost", ""))
    _spend(ctx, pid, power=cost.get("power", 0))
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
    # Bridge endpoints — two cases:
    #   Power action bridge: log has "[HEXA-HEXB]" using SEQUENTIAL labels already
    #   Engineers ability bridge: log has no [X-Y]; use bbs_id from args via ctx.bbs_map
    hex_a = hex_b = None
    log = event.get("log", "") if isinstance(event, dict) else ""
    import re as _re
    m = _re.search(r'\[([A-Z]\d+)-([A-Z]\d+)\]', log)
    if m:
        hex_a, hex_b = m.group(1), m.group(2)
    else:
        bbs_id = args.get("bbs_id")
        if bbs_id is not None and str(bbs_id) in ctx.bbs_map:
            hex_a, hex_b = ctx.bbs_map[str(bbs_id)]
    return _make_move(ctx, pid,
        action_type="power_action",
        description="Power action: bridge",
        power_action_type="bridge",
        hex_coord=hex_a, secondary_hex=hex_b,
        cost_power=cost.get("power", 0),
    )


def handle_special_action(event, args, ctx):
    pid = str(args.get("player_id", ""))
    source = ""
    if args.get("favor_id") and str(args["favor_id"]) != "0":
        source = "favor"
    elif args.get("bonus_id") and str(args["bonus_id"]) != "0":
        source = "bonus"
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
    return _make_move(ctx, pid,
        action_type="found_town", description="Found town",
        hex_coord=hex_coord, town_id=town_id,
    )


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
    pid = str(args.get("player_id", ""))
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


def handle_some_income(event, args, ctx):
    pid = str(args.get("player_id", ""))
    coins = parse_resource_html(args.get("coins_income", "")).get("coins", 0)
    workers = parse_resource_html(args.get("workers_income", "")).get("workers", 0)
    priests = parse_resource_html(args.get("priests_income", "")).get("priests", 0)
    power = parse_resource_html(args.get("power_income", "")).get("power", 0)

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
            if vp_delta < 0:
                inc_vp_source(ctx, pid, "vp_faction_ability", vp_delta)
                _spend(ctx, pid, vp=-vp_delta)
                ctx.round_vp_faction[pid] = ctx.round_vp_faction.get(pid, 0) + (-vp_delta)
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
    for res, field in [("power", "power_spent"),
                       ("workers", "workers_spent"),
                       ("priests", "priests_spent")]:
        amt = parse_resource_html(
            args.get(field, "")).get(res, 0)
        if amt > 0:
            _convert(ctx, pid, **{res: -amt})
    for res, field in [("coins", "coins_gained"),
                       ("workers", "workers_gained"),
                       ("priests", "priests_gained")]:
        amt = parse_resource_html(
            args.get(field, "")).get(res, 0)
        if amt > 0:
            _convert(ctx, pid, **{res: amt})
    return None


def handle_power_via_structures(event, args, ctx):
    pid = str(args.get("player_id", ""))
    hex_coord = extract_hex(args, ctx)
    pw = parse_resource_html(
        args.get("power_income", "")).get("power", 0)
    vp_cost = parse_resource_html(
        args.get("vp_price", "")).get("vp", 0)
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


# ---------------------------------------------------------------------------
# Fan-faction handlers
# ---------------------------------------------------------------------------

def handle_advance_income_track(event, args, ctx):
    pid = str(args.get("player_id", ""))
    # Chash Dallah's income-track advancement grants VP (1/2/3/4 for levels 1-4).
    # The trailing updateScore has score_delta=0 (no double-count).
    vp = parse_resource_html(args.get("score_inc", "")).get("vp", 0)
    if vp:
        inc_vp_source(ctx, pid, "vp_faction_ability", vp)
        _gen(ctx, pid, vp=vp)
    _sync_score(args, pid, ctx)
    return _make_move(ctx, pid, action_type="advance_income_track",
                      description="Advance income track", gain_vp=vp)


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
    "conversionsApplied": handle_conversions,
    "conversionsAppliedWithDelay": handle_conversions,
    "powerViaStructures": handle_power_via_structures,
    # State tracking
    "updateCounters": handle_update_counters,
    # Fan-faction events
    "advanceIncomeTrack": handle_advance_income_track,
    "swapCultTrack": handle_swap_cult_track,
    "favorTileLost": handle_favor_tile_lost,
    "tokenPlaced": noop,
    # Silently consumed events
    "updateTreasury": noop, "emptyTreasury": noop, "updateExchangeTrack": noop,
    "newPowerTokens": noop, "addNewBonusCard": handle_add_new_bonus_card, "startingTerrainChosen": noop,
    "terrainRingUpdated": noop, "someCost": noop, "gainRessources": noop,
    "gainPriests": noop, "workersForPriests": noop, "workersIncome": noop,
    "createSomeWorkers": noop, "createLandBridges": noop, "simpleNote": noop,
    "wakeupPlayers": noop, "newCustomBoard": noop, "powerIncome": handle_power_income,
    "actionUsed": noop, "returnActionTokens": noop, "coinsOnBonusCards": noop,
    "firstPlayerChanged": noop, "factionBoardChosen": noop,
    "timeJokerUsed": noop, "undoRestoreDISAB": noop,
    "tileScored": noop,
}
