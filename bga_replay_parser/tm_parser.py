"""
Terra Mystica BGA Replay Parser

Parses raw BGA replay HTML into CSV-ready data:
  - Player results: one row per player per game
  - Move log: one row per action
  - Round summaries: one row per round per player
"""

import csv
import json
import logging
import os
import re
from dataclasses import asdict, fields
from typing import Dict, List, Optional, Tuple

from .tm_constants import (
    BONUS_TYPE_NAMES, EXCLUDED_FACTIONS, FACTIONS, FAVOR_TYPE_NAMES,
    SCORING_TYPE_NAMES,
)
from .tm_handlers import (
    EVENT_HANDLERS, _ZERO_RES, _gen, parse_resource_html, update_counters,
)
from .tm_models import (
    EloData, ParseContext, TMAuctionBid, TMGameData, TMMove, TMPlayerResult,
    TMPlayerState, TMRoundSummary,
)

logger = logging.getLogger(__name__)

_STATE_ATTR_RENAMES = {
    "score": "vp_at_round_end",
    "coins": "coins_at_round_end",
    "workers": "workers_at_round_end",
}


class TerraMysticaParser:

    # -------------------------------------------------------------------
    # Skip detection
    # -------------------------------------------------------------------

    def should_skip_replay(self, replay_html: str) -> Optional[str]:
        """Return a reason string if this replay should be skipped, else None."""
        # Check factions that were actually played, not just listed in gamedatas
        played = set(re.findall(
            r'"type":"factionPositionSelected"[^{]*\{[^}]*?"faction_type":"([^"]+)"',
            replay_html))
        if not played:
            # Fallback regex: tolerate nested objects before faction_type
            for m in re.finditer(r'"type":"factionPositionSelected"', replay_html):
                start = replay_html.rfind("{", 0, m.start())
                depth = 0
                for j, c in enumerate(replay_html[start:], start):
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            fm = re.search(r'"faction_type":"([^"]+)"',
                                           replay_html[start:j + 1])
                            if fm:
                                played.add(fm.group(1))
                            break
        # Old-format / fan-faction replays assign factions via factionBoardSwapped
        # (players may swap several times during setup; only each player's final
        # board counts as played).
        final_swap = {}
        for m in re.finditer(
                r'"type":"factionBoardSwapped".{0,600}?"player_id":"?(\d+)"?'
                r'.{0,600}?"new_faction":"([^"]+)"',
                replay_html, re.DOTALL):
            final_swap[m.group(1)] = m.group(2)
        played |= set(final_swap.values())

        excluded = played & EXCLUDED_FACTIONS
        if excluded:
            return f"excluded faction: {sorted(excluded)[0]}"

        # Conceded / abandoned games (none exist in the current corpus — BGA
        # doesn't surface them in player game histories — but guard future
        # scrapes anyway).
        if re.search(r'"concede":"?(true|[1-9])|"zombie":"?[1-9]|"neutralized":"?[1-9]', replay_html):
            return "conceded/abandoned game"
        return None

    # -------------------------------------------------------------------
    # HTML / JSON extraction
    # -------------------------------------------------------------------

    def _extract_brace_balanced_json(self, text: str, start_pos: int) -> Optional[Dict]:
        depth = 0
        in_string = False
        escape = False
        for i, char in enumerate(text[start_pos:], start_pos):
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        return json.loads(text[start_pos:i + 1])
                elif char == ';' and depth == 0:
                    break
        return None

    def _extract_g_gamelogs(self, html: str) -> Dict:
        match = re.search(r'g_gamelogs\s*=\s*', html)
        if not match:
            logger.warning("g_gamelogs not found in HTML")
            return {}
        try:
            return self._extract_brace_balanced_json(html, match.end()) or {}
        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Error extracting g_gamelogs: {e}")
            return {}

    def _extract_gamedatas(self, html: str) -> Dict:
        match = re.search(r'gameui\.completesetup\s*\(', html)
        if not match:
            logger.warning("completesetup not found in HTML")
            return {}
        brace_pos = html.find('{', match.end())
        if brace_pos == -1:
            return {}
        try:
            return self._extract_brace_balanced_json(html, brace_pos) or {}
        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Error extracting gamedatas: {e}")
            return {}

    # -------------------------------------------------------------------
    # Lookup tables from gamedatas
    # -------------------------------------------------------------------

    def _build_lookups(self, gamedatas: Dict, ctx: ParseContext):
        for bid, bdata in gamedatas.get("bonus_cards", {}).items():
            btype = str(bdata.get("bonus_type", ""))
            ctx.bonus_id_to_type[str(bid)] = btype
            ctx.bonus_type_to_name[btype] = BONUS_TYPE_NAMES.get(btype, f"bonus_{btype}")
        for sid, sdata in gamedatas.get("scoring_tiles", {}).items():
            stype = str(sdata.get("scoring_type", ""))
            ctx.scoring_round_to_type[str(sid)] = stype
            ctx.scoring_type_to_name[stype] = SCORING_TYPE_NAMES.get(stype, f"scoring_{stype}")
        for ftype in gamedatas.get("favor_tile_types", {}):
            ctx.favor_type_to_name[str(ftype)] = FAVOR_TYPE_NAMES.get(str(ftype), f"favor_{ftype}")
        # Build BGA bts_id -> standard hex label (skip rivers, renumber per row)
        bts = gamedatas.get("board_terrain_spaces", {})
        if bts:
            from collections import defaultdict
            rows = defaultdict(list)
            for bts_id, s in bts.items():
                rows[bts_id[0]].append((int(s["bts_x"]), bts_id, s["bts_terrain"]))
            for row in rows:
                num = 1
                for _, bts_id, terrain in sorted(rows[row]):
                    if terrain != "river":
                        ctx.hex_map[bts_id] = f"{row}{num}"
                        num += 1
        # Build bbs_id -> (sequential_a, sequential_b) for bridge slots.
        # board_bridge_spaces uses RAW bts_id labels; convert via hex_map.
        bbs = gamedatas.get("board_bridge_spaces", {})
        for slot_id, slot in bbs.items():
            up = slot.get("bts_id_up")
            down = slot.get("bts_id_down")
            if up and down and up in ctx.hex_map and down in ctx.hex_map:
                ctx.bbs_map[str(slot_id)] = (ctx.hex_map[up], ctx.hex_map[down])

    # -------------------------------------------------------------------
    # Main parse entry point
    # -------------------------------------------------------------------

    def parse_complete_game(self, replay_html: str, game_metadata: Dict = None,
                            table_id: str = "", player_perspective: str = "") -> TMGameData:
        gamelogs_data = self._extract_g_gamelogs(replay_html)
        gamedatas = self._extract_gamedatas(replay_html)

        packets = self._get_packets(gamelogs_data)
        ctx = ParseContext()

        if gamedatas:
            self._build_lookups(gamedatas, ctx)
            gd_factions = gamedatas.get("factions", {})
            for pid, pdata in gamedatas.get("players", {}).items():
                pid = str(pid)
                ctx.player_map[pid] = pdata.get("name", pid)
                color = pdata.get("color", "")
                if color:
                    ctx.colors[pid] = color
                turn_order = pdata.get("player_turn_order")
                if turn_order not in (None, "", "0"):
                    try:
                        ctx.seat_order[pid] = int(turn_order)
                    except (TypeError, ValueError):
                        pass
                # Seed faction + terrain from gamedatas for older games that
                # lack factionPositionSelected events. Skip 'not_chosen'
                # (present before selection in newer games — filled in by events).
                faction = pdata.get("faction", "")
                if faction and faction != "not_chosen":
                    ctx.factions[pid] = faction
                    fdata = gd_factions.get(faction, {})
                    terrain = fdata.get("home_terrain", "")
                    if terrain:
                        ctx.terrains[pid] = terrain
        if game_metadata and "players" in game_metadata:
            ctx.elo_metadata = game_metadata["players"]

        moves = self._walk_gamelogs(packets, ctx)
        # Apply metadata names only AFTER the walk: old-format events (e.g. the
        # "${player_name} is playing the ..." starting-VP message) are matched by
        # the name used in the replay log, which differs from the metadata name
        # when a player renamed their BGA account after the game.
        if game_metadata and "players" in game_metadata:
            for pid, pdata in game_metadata["players"].items():
                ctx.player_map[str(pid)] = pdata.get("name", str(pid))
        # Normalize faction column on all moves to the player's final faction.
        # Handles factionBoardSwapped: select_faction moves capture the initial
        # pick, but later moves use the post-swap faction — rewrite earlier
        # moves so the column is consistent with player_results.
        for m in moves:
            if m.player_id and ctx.factions.get(m.player_id):
                m.faction = ctx.factions[m.player_id]
                m.player_name = ctx.player_map.get(m.player_id, m.player_name)
        return self._assemble_game_data(ctx, moves, table_id, player_perspective,
                                        game_metadata, gamedatas)

    def _get_packets(self, gamelogs_data: Dict) -> List:
        if not gamelogs_data:
            return []
        inner = gamelogs_data.get("data", gamelogs_data)
        if isinstance(inner, dict):
            inner = inner.get("data", [])
        return inner if isinstance(inner, list) else []

    # -------------------------------------------------------------------
    # Event walker
    # -------------------------------------------------------------------

    def _walk_gamelogs(self, packets: List[Dict], ctx: ParseContext) -> List[TMMove]:
        moves = []
        for packet in packets:
            events = packet.get("data", [])
            if not isinstance(events, list):
                continue
            for event in events:
                etype = event.get("type", "")
                args = event.get("args", {})
                if not isinstance(args, dict):
                    continue

                # Phase/round detection via incomePhase
                if etype == "incomePhase" or (etype == "justAMessage" and "Income phase" in event.get("log", "")):
                    self._handle_income_phase(args, ctx)
                    continue

                # Phase transitions via justAMessage
                if etype == "justAMessage":
                    log_text = event.get("log", "")
                    # Auction bid: "${player_name} bids on the ${faction_name}
                    # with ${starting_vp} Starting VP(s)". Two formats:
                    #   fast (simultaneous): starting_vp is HTML (vp_amount div)
                    #   slow (turn-based):   starting_vp is a plain integer
                    # Try the HTML form first (reliable), then a plain integer.
                    if "bids on the" in log_text:
                        bid_pid = str(args.get("player_id", ""))
                        fac = args.get("faction_type", "")
                        sv_raw = str(args.get("starting_vp", ""))
                        bid_m = re.search(r"vp_amount'?>(-?\d+)", sv_raw)
                        if bid_m:
                            ctx.auction_type = "fast"
                        else:
                            bid_m = re.search(r"(-?\d+)", sv_raw)
                            if bid_m:
                                ctx.auction_type = "slow"
                        if bid_pid and fac and bid_m:
                            ctx.auction_bids.append((bid_pid, fac, int(bid_m.group(1))))
                        continue
                    # Old-format faction assignment (pre-factionPositionSelected):
                    # "${player_name} is playing the ${faction_name} Faction..."
                    if "is playing the" in log_text and "Faction" in log_text:
                        p_name = args.get("player_name", "")
                        pid = next((pid for pid, name in ctx.player_map.items()
                                    if name == p_name), None)
                        if pid:
                            svp_m = re.search(r"vp_amount'?>(\d+)",
                                              str(args.get("starting_vp", "")))
                            if svp_m:
                                svp = int(svp_m.group(1))
                                ctx.starting_vp[pid] = svp
                                if pid in ctx.player_states:
                                    ctx.player_states[pid].score = svp
                    if "Action phase" in log_text:
                        ctx.current_phase = "action"
                        continue
                    elif "Cleanup phase" in log_text:
                        ctx.current_phase = "cleanup"
                        # End-of-action-phase state snapshot
                        ctx.round_end_states[ctx.current_round] = {
                            pid: TMPlayerState(**st.__dict__)
                            for pid, st in ctx.player_states.items()
                        }
                        # Save round data and take resource snapshot HERE,
                        # before cult bonuses fire. Cult bonus resources will
                        # accumulate after the snapshot and carry into the
                        # next round's summary (when they're first usable).
                        if ctx.current_round > 0:
                            self._save_round_data(ctx)
                        continue
                    elif "final scoring" in log_text.lower():
                        if ctx.current_round > 0:
                            if ctx.current_round not in ctx.round_end_states:
                                ctx.round_end_states[ctx.current_round] = {
                                    pid: TMPlayerState(**st.__dict__)
                                    for pid, st in ctx.player_states.items()
                                }
                            if ctx.current_round not in ctx.all_round_income:
                                self._save_round_data(ctx)
                        ctx.current_phase = "final_scoring"
                        continue

                # Cult bonus spades (updateCounters with "Cult bonus" in log)
                if etype == "updateCounters" and "Cult bonus" in event.get("log", ""):
                    pid = str(args.get("player_id", ""))
                    counters = args.get("counters", {})
                    # Counter keys are "spades_count_PLAYERID"
                    spade_key = f"spades_count_{pid}"
                    sc_data = counters.get(spade_key, {})
                    spades = 0
                    if isinstance(sc_data, dict):
                        sc = sc_data.get("counter_value")
                        if sc is not None and sc != "0" and sc != 0:
                            try:
                                spades = int(sc)
                            except (ValueError, TypeError):
                                pass
                    if spades > 0:
                        cb = ctx.round_cult_bonus.setdefault(
                            pid, {"coins": 0, "workers": 0, "priests": 0,
                                  "power": 0, "spades": 0})
                        cb["spades"] += spades
                        _gen(ctx, pid, spades=spades)

                # Dispatch to handler
                handler = EVENT_HANDLERS.get(etype)
                if handler:
                    move = handler(event, args, ctx)
                    if move:
                        moves.append(move)

                # Always sync counters
                if "counters" in args and isinstance(args["counters"], dict):
                    update_counters(args["counters"], ctx)

        if ctx.current_round > 0 and ctx.current_round not in ctx.all_round_income:
            self._save_round_data(ctx)
        return moves

    def _handle_income_phase(self, args: Dict, ctx: ParseContext):
        pid = args.get("player_id")
        if not pid:
            # Round data is saved at cleanup phase, not here.
            ctx.current_round += 1
            ctx.current_phase = "income"
            ctx.pass_counter = 0
            ctx.pass_order = {}
            ctx.round_income = {}
            ctx.round_scoring_vp = {}
            ctx.round_actions = {}
            ctx.round_power_actions = {}
            ctx.round_power_gained = {}
            ctx.round_vp_leach = {}
            ctx.round_vp_faction = {}
            # DON'T reset round_cult_bonus — it carries cult bonus data from
            # the previous round's cleanup into this round's summary.
            # Snapshot bonus cards held this round
            ctx.bonus_card_by_round[ctx.current_round] = dict(ctx.player_bonus_card)
            for p in ctx.player_map:
                ctx.round_income[p] = {"coins": 0, "workers": 0, "priests": 0, "power": 0}
                ctx.round_scoring_vp[p] = 0
                ctx.round_actions[p] = {}
                ctx.round_power_actions[p] = []
                ctx.round_power_gained[p] = {"structures": 0, "cults": 0, "other": 0}
        else:
            ipid = str(pid)
            for res_key, arg_key in [
                ("coins", "coins_income"),
                ("workers", "workers_income"),
                ("priests", "priests_income"),
                ("power", "power_income"),
            ]:
                amount = parse_resource_html(
                    args.get(arg_key, "")).get(res_key, 0)
                ctx.round_income.setdefault(
                    ipid, {"coins": 0, "workers": 0,
                           "priests": 0, "power": 0})
                ctx.round_income[ipid][res_key] += amount
                if amount > 0:
                    _gen(ctx, ipid, **{res_key: amount})
            if "counters" in args and isinstance(args["counters"], dict):
                update_counters(args["counters"], ctx)

    def _save_round_data(self, ctx: ParseContext):
        rnd = ctx.current_round
        ctx.all_round_income[rnd] = {pid: dict(inc) for pid, inc in ctx.round_income.items()}
        ctx.all_round_scoring_vp[rnd] = dict(ctx.round_scoring_vp)
        ctx.all_round_actions[rnd] = {pid: dict(acts) for pid, acts in ctx.round_actions.items()}
        ctx.all_pass_order[rnd] = dict(ctx.pass_order)
        ctx.all_round_power_actions[rnd] = {pid: list(pa) for pid, pa in ctx.round_power_actions.items()}
        ctx.all_round_cult_bonus[rnd] = {pid: dict(cb) for pid, cb in ctx.round_cult_bonus.items()}
        ctx.all_round_power_gained[rnd] = {pid: dict(pg) for pid, pg in ctx.round_power_gained.items()}
        ctx.all_round_vp_leach[rnd] = dict(ctx.round_vp_leach)
        ctx.all_round_vp_faction[rnd] = dict(ctx.round_vp_faction)

        # Compute per-round resource flow deltas (current cumulative - snapshot)
        for cumulative, snapshot, dest in [
            (ctx.res_generated, ctx.res_generated_snapshot, ctx.all_round_res_generated),
            (ctx.res_spent, ctx.res_spent_snapshot, ctx.all_round_res_spent),
            (ctx.res_converted, ctx.res_converted_snapshot, ctx.all_round_res_converted),
        ]:
            dest[rnd] = {}
            for pid in ctx.player_map:
                cur = cumulative.get(pid, _ZERO_RES)
                snap = snapshot.get(pid, _ZERO_RES)
                dest[rnd][pid] = {
                    k: cur.get(k, 0) - snap.get(k, 0)
                    for k in _ZERO_RES
                }

        # Take resource flow snapshot AFTER save — cult bonus events that fire
        # after cleanup will appear in the NEXT round's delta.
        ctx.res_generated_snapshot = {
            pid: dict(d) for pid, d in ctx.res_generated.items()
        }
        ctx.res_spent_snapshot = {
            pid: dict(d) for pid, d in ctx.res_spent.items()
        }
        ctx.res_converted_snapshot = {
            pid: dict(d) for pid, d in ctx.res_converted.items()
        }
        # Reset cult bonus accumulator — next round will start fresh,
        # then cult bonus events from this cleanup will fill it.
        ctx.round_cult_bonus = {}

    # -------------------------------------------------------------------
    # Result assembly
    # -------------------------------------------------------------------

    def _assemble_game_data(self, ctx, moves, table_id, player_perspective,
                            game_metadata, gamedatas) -> TMGameData:
        round_summaries = self._build_round_summaries(ctx)
        player_results = self._build_player_results(ctx, gamedatas)
        winner_id, winner_name = self._determine_winner(ctx)

        scoring_tiles = []
        for r in range(1, 7):
            stype = ctx.scoring_round_to_type.get(str(r), "")
            scoring_tiles.append(ctx.scoring_type_to_name.get(stype, stype))

        bonus_cards = [ctx.bonus_type_to_name.get(btype, btype)
                       for _, btype in sorted(ctx.bonus_id_to_type.items())]

        # Auction bids: collapse to the LAST bid each player made on each
        # faction (fast auction has one bid per pair, so this is a no-op there;
        # slow/turn-based keeps each player's final offer per faction). Mark
        # the (player, faction) pair that the auction actually assigned.
        last_bid = {}  # (pid, faction) -> bid, last write wins (log order)
        for pid, fac, bid in ctx.auction_bids:
            last_bid[(pid, fac)] = bid
        auction_bids = [
            TMAuctionBid(
                player_id=pid,
                player_name=ctx.player_map.get(pid, ""),
                faction=fac,
                bid_starting_vp=bid,
                is_winning_bid=(ctx.factions.get(pid, "") == fac),
            )
            for (pid, fac), bid in last_bid.items()
        ]

        gd = gamedatas or {}
        game_data = TMGameData(
            table_id=str(table_id),
            player_perspective=str(player_perspective),
            num_players=len(ctx.player_map),
            board=gd.get("game_board", ""),
            total_rounds=max((rs.round_number for rs in round_summaries), default=0),
            # gamedatas `with_auction` is only set on newer-client games; older
            # slow-auction games lack the key. Presence of bids is authoritative,
            # so OR the two (auction_bids is computed above).
            with_auction=bool(auction_bids) or bool(gd.get("with_auction", False)),
            landscape_active=bool(gd.get("landscape_active", False)),
            custom_map=bool(gd.get("custom_map", False)),
            variable_turn_order=str(gd.get("turn_order", "")) not in ("", "0", "1"),
            fire_ice_scoring=bool(gd.get("fire_ice_final_scoring_active", False)),
            auction_type=ctx.auction_type,
            game_version=str(gd.get("game_version", "")),
            winner_player_id=winner_id,
            winner_player_name=winner_name,
            players=player_results,
            moves=moves,
            round_summaries=round_summaries,
            auction_bids=auction_bids,
            scoring_tiles=scoring_tiles,
            bonus_cards=bonus_cards,
        )

        if game_metadata:
            game_data.game_date = game_metadata.get("game_date", "")
            game_data.game_speed = game_metadata.get("game_speed", "")
            game_data.game_mode = game_metadata.get("game_mode", "")
            game_data.starting_vp_setting = game_metadata.get("starting_vp_setting", "")
            game_data.metadata = {k: v for k, v in game_metadata.items() if k != "players"}

        self._finalize_resource_totals(game_data, ctx)
        return game_data

    def _build_round_summaries(self, ctx: ParseContext) -> List[TMRoundSummary]:
        summaries = []
        for rnd in range(1, ctx.current_round + 1):
            scoring_type = ctx.scoring_round_to_type.get(str(rnd), "")
            scoring_name = ctx.scoring_type_to_name.get(scoring_type, scoring_type)
            rnd_income = ctx.all_round_income.get(rnd, {})
            rnd_scoring = ctx.all_round_scoring_vp.get(rnd, {})
            rnd_actions = ctx.all_round_actions.get(rnd, {})
            rnd_pass = ctx.all_pass_order.get(rnd, {})
            rnd_pa = ctx.all_round_power_actions.get(rnd, {})
            rnd_pg = ctx.all_round_power_gained.get(rnd, {})
            rnd_cb = ctx.all_round_cult_bonus.get(rnd, {})
            rnd_gen = ctx.all_round_res_generated.get(rnd, {})
            rnd_spent = ctx.all_round_res_spent.get(rnd, {})
            rnd_vp_leach = ctx.all_round_vp_leach.get(rnd, {})
            rnd_vp_faction = ctx.all_round_vp_faction.get(rnd, {})

            for pid, name in ctx.player_map.items():
                end_state = ctx.round_end_states.get(rnd, {}).get(pid)
                income = rnd_income.get(pid, {})
                actions = rnd_actions.get(pid, {})
                pass_ord = rnd_pass.get(pid)
                bonus = ctx.bonus_card_by_round.get(rnd, {}).get(pid, "")
                pg = rnd_pg.get(pid, {})
                cb = rnd_cb.get(pid, {})
                gen = rnd_gen.get(pid, {})
                spent = rnd_spent.get(pid, {})

                s = TMRoundSummary(
                    round_number=rnd, player_id=pid, player_name=name,
                    faction=ctx.factions.get(pid, ""),
                    scoring_tile=scoring_name, bonus_card=bonus,
                    scoring_vp_gained=rnd_scoring.get(pid, 0),
                    income_coins=income.get("coins", 0),
                    income_workers=income.get("workers", 0),
                    income_priests=income.get("priests", 0),
                    income_power=income.get("power", 0),
                    cult_bonus_coins=cb.get("coins", 0),
                    cult_bonus_workers=cb.get("workers", 0),
                    cult_bonus_priests=cb.get("priests", 0),
                    cult_bonus_power=cb.get("power", 0),
                    cult_bonus_spades=cb.get("spades", 0),
                    num_actions=sum(actions.values()),
                    spades_used=actions.get("terrain_transforms", 0),
                    dwellings_built=actions.get("dwellings_built", 0),
                    structures_upgraded=actions.get("structures_upgraded", 0),
                    cult_advances=actions.get("cult_advances", 0),
                    power_actions_used=actions.get("power_actions_used", 0),
                    towns_founded=actions.get("towns_founded", 0),
                    power_actions=rnd_pa.get(pid, []),
                    power_gained_via_structures=pg.get("structures", 0),
                    power_gained_via_cults=pg.get("cults", 0),
                    power_gained_via_other=pg.get("other", 0),
                    coins_generated=gen.get("coins", 0),
                    coins_spent=spent.get("coins", 0),
                    workers_generated=gen.get("workers", 0),
                    workers_spent=spent.get("workers", 0),
                    priests_generated=gen.get("priests", 0),
                    priests_spent=spent.get("priests", 0),
                    spades_generated=gen.get("spades", 0),
                    power_generated=gen.get("power", 0),
                    power_spent=spent.get("power", 0),
                    vp_generated=gen.get("vp", 0),
                    vp_leach_cost=rnd_vp_leach.get(pid, 0),
                    vp_faction_spent=rnd_vp_faction.get(pid, 0),
                    pass_order=pass_ord,
                )
                if end_state:
                    for attr in ("score", "coins", "workers", "power_bowl1", "power_bowl2",
                                 "power_bowl3", "cult_fire", "cult_water", "cult_earth", "cult_air"):
                        target = _STATE_ATTR_RENAMES.get(attr, attr)
                        setattr(s, target, getattr(end_state, attr))
                summaries.append(s)
        return summaries

    def _build_player_results(self, ctx: ParseContext,
                              gamedatas: Optional[Dict] = None
                              ) -> Dict[str, TMPlayerResult]:
        landscape_types = (gamedatas or {}).get("landscape_types", {}) or {}
        results = {}
        for pid, name in ctx.player_map.items():
            state = ctx.player_states.get(pid, TMPlayerState())
            vps = ctx.vp_sources.get(pid, {})
            # Sum structure counts from round actions (total built, not final board state)
            def _sum_round_action(key):
                return sum(
                    ctx.all_round_actions.get(r, {}).get(pid, {}).get(key, 0)
                    for r in range(0, ctx.current_round + 1))

            results[pid] = TMPlayerResult(
                player_id=pid, player_name=name,
                faction=ctx.factions.get(pid, ""),
                terrain=ctx.terrains.get(pid, FACTIONS.get(ctx.factions.get(pid, ""), "")),
                color=ctx.colors.get(pid, ""),
                seat_order=ctx.seat_order.get(pid, 0),
                starting_vp=ctx.starting_vp.get(pid, 0),
                final_vp=state.score,
                vp_round_scoring=vps.get("vp_round_scoring", 0),
                vp_favor_tiles=vps.get("vp_favor_tiles", 0),
                vp_bonus_cards=vps.get("vp_bonus_cards", 0),
                vp_towns=vps.get("vp_towns", 0),
                vp_faction_ability=vps.get("vp_faction_ability", 0),
                vp_power_leaching=vps.get("vp_power_leaching", 0),
                vp_conversions=vps.get("vp_conversions", 0),
                vp_track_advances=vps.get("vp_track_advances", 0),
                vp_cult_final=vps.get("vp_cult_final", 0),
                vp_network_final=vps.get("vp_area_final", 0),
                vp_resources_final=vps.get("vp_resources_final", 0),
                dwellings_built=_sum_round_action("dwellings_built"),
                trading_houses_built=_sum_round_action("tradinghouse_built"),
                temples_built=_sum_round_action("temple_built"),
                strongholds_built=_sum_round_action("stronghold_built"),
                sanctuaries_built=_sum_round_action("sanctuary_built"),
                bridges_built=_sum_round_action("bridges_built"),
                towns_formed=len(ctx.player_town_tiles.get(pid, [])),
                cult_fire=state.cult_fire, cult_water=state.cult_water,
                cult_earth=state.cult_earth, cult_air=state.cult_air,
                shipping_level=state.shipping_level,
                exchange_level=state.exchange_level,
                network_size=vps.get("_largest_connected", 0),
                favor_tiles=ctx.player_favor_tiles.get(pid, []),
                town_tiles=ctx.player_town_tiles.get(pid, []),
                bonus_cards=[
                    ctx.bonus_card_by_round.get(rnd, {}).get(pid, "")
                    for rnd in range(1, 7)
                ],
                landscape_hex=ctx.player_landscape_hex.get(pid, ""),
                landscape_placed=(
                    landscape_types.get(ctx.factions.get(pid, ""), {}).get("name", "")
                    if pid in ctx.player_landscape_hex else ""
                ),
            )
            elo = ctx.elo_metadata.get(pid, {})
            if elo:
                results[pid].elo_data = EloData(
                    elo_before=elo.get("elo_before"),
                    elo_after=elo.get("elo_after"),
                    arena_before=elo.get("arena_before"),
                    arena_after=elo.get("arena_after"),
                )
        return results

    def _finalize_resource_totals(
        self, game_data: TMGameData, ctx: ParseContext
    ):
        """Write generated/spent/converted from context into results."""
        for pid, result in game_data.players.items():
            g = ctx.res_generated.get(pid, {})
            s = ctx.res_spent.get(pid, {})
            c = ctx.res_converted.get(pid, {})
            for res in ("coins", "workers", "priests",
                        "spades", "power", "vp"):
                setattr(result, f"{res}_generated",
                        g.get(res, 0))
                setattr(result, f"{res}_spent",
                        s.get(res, 0))
                setattr(result, f"{res}_converted",
                        c.get(res, 0))

    def _determine_winner(self, ctx: ParseContext) -> Tuple[str, str]:
        best_pid, best_name, best_score = "", "", -1
        for pid, state in ctx.player_states.items():
            if state.score > best_score:
                best_score = state.score
                best_pid = pid
                best_name = ctx.player_map.get(pid, "")
        return best_pid, best_name

    # -------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------

    def export_to_json(self, game_data: TMGameData, output_path: str,
                       player_perspective: str = None):
        if player_perspective:
            dir_path = os.path.dirname(output_path)
            output_path = os.path.join(dir_path, player_perspective, os.path.basename(output_path))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(game_data), f, indent=2, ensure_ascii=False)
        return output_path

    def export_batch_csv(self, games: List[TMGameData], output_dir: str):
        """Write setup.csv, player_results.csv, moves.csv, round_summaries.csv."""
        os.makedirs(output_dir, exist_ok=True)
        setup_rows, player_rows, move_rows, round_rows = [], [], [], []

        def _elo(p, key):
            if p.elo_data is None:
                return ""
            val = getattr(p.elo_data, key, None)
            return "" if val is None else val

        for g in games:
            ordered = sorted(g.players.values(), key=lambda p: p.seat_order)
            setup_rows.append({
                "table_id": g.table_id,
                "num_players": g.num_players,
                "board": g.board,
                "total_rounds": g.total_rounds,
                "with_auction": g.with_auction,
                "landscape_active": g.landscape_active,
                "custom_map": g.custom_map,
                "variable_turn_order": g.variable_turn_order,
                "fire_ice_scoring": g.fire_ice_scoring,
                "game_version": g.game_version,
                "scoring_tiles": ";".join(g.scoring_tiles),
                "bonus_cards": ";".join(g.bonus_cards),
                "winner_player_id": g.winner_player_id,
                "winner_player_name": g.winner_player_name,
                "player_ids": ";".join(p.player_id for p in ordered),
                "player_names": ";".join(p.player_name for p in ordered),
                "factions": ";".join(p.faction for p in ordered),
                "terrains": ";".join(p.terrain for p in ordered),
                "elo_before": ";".join(str(_elo(p, "elo_before")) for p in ordered),
                "elo_after": ";".join(str(_elo(p, "elo_after")) for p in ordered),
                "starting_vp": ";".join(str(p.starting_vp) for p in ordered),
                "final_vp": ";".join(str(p.final_vp) for p in ordered),
            })
            for pr in g.players.values():
                row = {"table_id": g.table_id, "num_players": g.num_players,
                       "board": g.board, "is_winner": pr.player_id == g.winner_player_id}
                for f in fields(pr):
                    val = getattr(pr, f.name)
                    if f.name in ("favor_tiles", "town_tiles", "bonus_cards"):
                        row[f.name] = ";".join(val) if val else ""
                    elif f.name == "elo_data":
                        pass  # Skip nested elo for CSV
                    else:
                        row[f.name] = val
                player_rows.append(row)
            for m in g.moves:
                row = {"table_id": g.table_id}
                for f in fields(m):
                    if f.name != "state_after":
                        row[f.name] = getattr(m, f.name)
                move_rows.append(row)
            for rs in g.round_summaries:
                row = {"table_id": g.table_id}
                for f in fields(rs):
                    val = getattr(rs, f.name)
                    if f.name == "power_actions":
                        row[f.name] = ";".join(val) if val else ""
                    else:
                        row[f.name] = val
                round_rows.append(row)

        def write_csv(path, rows):
            if not rows:
                return
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            logger.info(f"Wrote {len(rows)} rows to {path}")

        write_csv(os.path.join(output_dir, "setup.csv"), setup_rows)
        write_csv(os.path.join(output_dir, "player_results.csv"), player_rows)
        write_csv(os.path.join(output_dir, "moves.csv"), move_rows)
        write_csv(os.path.join(output_dir, "round_summaries.csv"), round_rows)
        return len(setup_rows), len(player_rows), len(move_rows), len(round_rows)
