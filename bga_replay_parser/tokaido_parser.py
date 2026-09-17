"""
Tokaido BGA replay parser.

Consumes the JSON gamelogs format returned by the BGA archive API
(`/archive/archive/logs.html`: a flat list of packets) — also accepts the
dict-wrapped form found inside `g_gamelogs = ...;` in HTML replays.
Yields TokaidoGameData with per-move and per-player rows.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from .tokaido_constants import (
    AMULET_TYPE,
    CALLIGRAPHY_TYPE_ARG_TO_NAME,
    LEGENDARY_OBJECT_TYPE,
    POSITION_TO_SPACE,
    SOUVENIR_TYPE_ARG_TO_CATEGORY,
)
from .tokaido_models import TokaidoGameData, TokaidoMove, TokaidoPlayerResult

logger = logging.getLogger(__name__)


class TokaidoParser:

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def parse_packets(self, packets: List[Dict], table_id: str = "") -> Optional[TokaidoGameData]:
        """Parse a flat list of BGA packets into TokaidoGameData.

        Returns None if the replay should be skipped (e.g. 2-player, missing result).
        """
        skip = self.should_skip(packets)
        if skip:
            logger.debug(f"{table_id}: skipping ({skip})")
            return None

        starts = self._extract_traveler_starts(packets)
        if len(starts) < 3:
            return None  # 2-player games not supported

        result_entries = self._extract_final_result(packets)
        if not result_entries:
            return None

        game = TokaidoGameData(table_id=str(table_id), num_players=len(starts))
        for pid, info in starts.items():
            game.players[pid] = TokaidoPlayerResult(
                player_id=pid,
                player_name=info["player_name"],
                player_color=info["player_color"],
                traveler=info["traveler"],
                starting_position=info["starting_position"],
                starting_coins=info["starting_coins"],
            )

        # Walk events, building moves and accumulating player totals.
        # Also detect Crossroads (presence of expansion-specific move types)
        # and Preparations (presence of any log mentioning "Preparation").
        travelers = {pid: info["traveler"] for pid, info in starts.items()}
        move_no = 0
        for packet in packets:
            for event in packet.get("data", []):
                if not isinstance(event, dict):
                    continue
                if not game.preparations:
                    log = event.get("log") or ""
                    if "Preparation" in log and "${player_name}" in log:
                        game.preparations = True
                row = self._parse_event(event, travelers)
                if row is None:
                    continue
                move_no += 1
                row.move_number = move_no
                game.moves.append(row)
                self._apply_move_to_player(row, game.players.get(str(row.player_id)))
                if row.type in {"CherryTree", "BathHouse", "Calligraphy",
                                "CalligraphyScored", "LegendaryObject",
                                "Amulet", "AmuletUsed"}:
                    game.has_crossroads = True

        # Final scores and ranks from the BGA result block.
        for r in result_entries:
            pid = str(r["player"])
            pr = game.players.get(pid)
            if pr is None:
                continue
            try:
                pr.final_score = int(r.get("score", 0))
            except (TypeError, ValueError):
                pr.final_score = 0
            try:
                pr.score_aux = int(r.get("score_aux", 0))
            except (TypeError, ValueError):
                pr.score_aux = 0
            try:
                pr.final_rank = int(r.get("rank", 0))
            except (TypeError, ValueError):
                pr.final_rank = 0
            if pr.final_rank == 1 and not r.get("tie", False):
                pr.is_winner = True
                game.winner_player_id = pid
                game.winner_player_name = pr.player_name
        # If everyone tied for rank 1, leave winner_player_id blank.
        return game

    def parse_json_file(self, path: str, table_id: str = "") -> Optional[TokaidoGameData]:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        packets = self._normalize_to_packet_list(raw)
        return self.parse_packets(packets, table_id=table_id or self._table_id_from_path(path))

    # ------------------------------------------------------------------
    # Skip detection
    # ------------------------------------------------------------------

    def should_skip(self, packets: List[Dict]) -> Optional[str]:
        """Return reason string if this replay should be skipped, else None."""
        # Detect 2p quickly: number of distinct travelerChosen events.
        travelers = 0
        for packet in packets:
            for event in packet.get("data", []):
                if isinstance(event, dict) and event.get("type") == "travelerChosen":
                    travelers += 1
        if travelers and travelers < 3:
            return "fewer than 3 players"
        # Preparations expansion is supported: it only redistributes starting
        # coins by position; player_coins on travelerChosen already reflects
        # the post-allocation value, so `starting_coins` captures it.
        # `preparations` is set during the move walk.
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_to_packet_list(raw) -> List[Dict]:
        """Accept a list (bga-replays JSON) or a dict (g_gamelogs from HTML)."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            inner = raw.get("data", raw)
            if isinstance(inner, dict):
                inner = inner.get("data", [])
            return inner if isinstance(inner, list) else []
        return []

    @staticmethod
    def _table_id_from_path(path: str) -> str:
        # Strip leading "invalid." if present, then drop extension.
        import os
        base = os.path.basename(path)
        for prefix in ("invalid.",):
            if base.startswith(prefix):
                base = base[len(prefix):]
        stem, _ = os.path.splitext(base)
        return stem

    def _extract_traveler_starts(self, packets: List[Dict]) -> Dict[str, Dict]:
        starts: Dict[str, Dict] = {}
        for packet in packets:
            for event in packet.get("data", []):
                if not isinstance(event, dict):
                    continue
                if event.get("type") != "travelerChosen":
                    continue
                args = event.get("args", {})
                if not isinstance(args, dict):
                    continue
                pid = str(args.get("player_id", ""))
                if not pid:
                    continue
                try:
                    seat = int(args.get("player_position_order", 0) or 0)
                except (TypeError, ValueError):
                    seat = 0
                # Starting coins: the player_coins counter snapshot in this
                # event reflects the player's starting purse (different per
                # traveler — Tokaido characters print their starting coins).
                starting_coins = 0
                counters = args.get("counters", {})
                if isinstance(counters, dict):
                    cd = counters.get(f"player_coins_{pid}")
                    if isinstance(cd, dict):
                        try:
                            starting_coins = int(cd.get("counter_value", 0))
                        except (TypeError, ValueError):
                            pass
                starts[pid] = {
                    "player_name": args.get("player_name", ""),
                    "player_color": args.get("player_color", "") or "",
                    "traveler": args.get("traveler", "") or "",
                    "starting_position": seat,
                    "starting_coins": starting_coins,
                }
        return starts

    def _extract_final_result(self, packets: List[Dict]) -> List[Dict]:
        """Find the result list. It's nested in args.args.result on a late event."""
        for packet in reversed(packets):
            for event in reversed(packet.get("data", [])):
                if not isinstance(event, dict):
                    continue
                args = event.get("args", {})
                if not isinstance(args, dict):
                    continue
                inner = args.get("args")
                if not isinstance(inner, dict):
                    continue
                result = inner.get("result")
                if isinstance(result, dict):
                    return list(result.values())
                if isinstance(result, list):
                    return result
        return []

    # ------------------------------------------------------------------
    # Event parsing
    # ------------------------------------------------------------------

    def _parse_event(self, event: Dict, travelers: Dict[str, str]) -> Optional[TokaidoMove]:
        log = event.get("log", "")
        args = event.get("args", {}) if isinstance(event.get("args"), dict) else {}
        pid = args.get("player_id")
        if pid is None:
            return None
        pid = str(pid)

        row = TokaidoMove(player_id=pid, traveler=travelers.get(pid, ""))

        # Default extraction of points/coins from args.
        try:
            base_points = int(args.get("points", 0) or 0)
        except (TypeError, ValueError):
            base_points = 0
        try:
            base_coins = int(args.get("coins", 0) or 0)
        except (TypeError, ValueError):
            base_coins = 0

        matched = self._match_event(log, row, args, base_points, base_coins)
        if not matched:
            return None
        return row

    def _match_event(self, log: str, row: TokaidoMove, args: Dict,
                     points: int, coins: int) -> bool:
        # Travel
        if log == "${player_name} travels and gets to a new stop (${name})":
            row.type = "Traveled"
            row.subtype = self._space_label(args)
            row.space = self._space_label(args)
            return True

        # Village souvenirs
        if log == ("${player_name} buys ${count} souvenir(s) for ${coins} coin(s) "
                   "and scores ${points} point(s)"):
            row.type = "Village"
            row.coins_spent = coins
            row.points_gained = points
            self._add_souvenirs(row, args)
            return True
        if log == "${player_name} doesn`t buy any Souvenir":
            row.type = "Village"
            row.subtype = "skipped"
            return True

        # Temple
        if log == "${player_name} gives ${coins} coin(s) to the Temple and earns ${points} point(s)":
            row.type = "Temple"
            row.coins_spent = coins
            row.coins_donated = coins
            row.points_gained = points
            return True
        if log == "${player_name} earns ${points} points for his donations to the Temple":
            row.type = "TempleRank"
            row.points_gained = points
            return True

        # Hot Spring
        if log == "${player_name} scores ${points} points (Hot spring)":
            row.type = "HotSpring"
            row.points_gained = points
            return True

        # Panorama
        if log == "${player_name} scores ${points} points (Panorama)":
            row.type = "Panorama"
            row.points_gained = points
            row.subtype = self._panorama_card(args)
            return True
        if log == "${player_name} is the first to finish the ${panorama_type} and scores ${points} points (Achievement)":
            row.type = "Achievement"
            row.subtype = args.get("panorama_type", "")
            row.points_gained = points
            return True

        # Farm
        if log == "${player_name} earns 3 coins (Farm)":
            row.type = "Farm"
            row.coins_gained = 3
            return True

        # Encounters
        if log == "${player_name} earns 3 coins (Kuge)":
            row.type = "Encounter"
            row.subtype = "Kuge"
            row.coins_gained = 3
            return True
        if log == "${player_name} earns 3 points (Samourai)":
            row.type = "Encounter"
            row.subtype = "Samourai"
            row.points_gained = 3
            return True
        if log == "${player_name} gives 1 coin (from the bank) to the Temple and earns 1 point (Miko)":
            row.type = "Encounter"
            row.subtype = "Miko"
            row.points_gained = 1
            # Bank-funded donation: pair coins_gained with coins_donated so
            # purse model `gained - spent - donated` nets to 0 (no change to
            # the player's actual purse — the coin came from the bank).
            row.coins_gained = 1
            row.coins_donated = 1
            return True
        if log == "${player_name} gets a panorama card and scores ${points} points (Annaibito)":
            row.type = "Encounter"
            cards = args.get("cards") or []
            color = (cards[0].get("type") or "").capitalize() if cards else ""
            row.subtype = f"Annaibito_{color}" if color else "Annaibito"
            row.points_gained = points
            return True
        if log == "${player_name} gets a souvenir card and earns ${points} points (Shokunin)":
            row.type = "Encounter"
            row.subtype = "Shokunin"
            row.points_gained = points
            self._add_souvenirs(row, args)
            return True

        # Inn
        if log == "${player_name} pays ${coins} coins for a meal (${name}) and scores ${points} points":
            row.type = "Inn"
            row.subtype = args.get("name", "") or ""
            row.coins_spent = coins
            row.points_gained = points
            return True
        if log == "${player_name} skips a meal":
            row.type = "Inn"
            row.subtype = "skipped"
            return True

        # Achievements (souvenir-set-based, hot-spring-based, etc.)
        if log == "${player_name} earns an achievement card (${achievement}) and scores 3 points":
            row.type = "Achievement"
            row.subtype = args.get("achievement", "")
            row.points_gained = 3
            return True

        # Crossroads — Cherry Tree
        if log == "${player_name} earns 1 coin and scores 2 points (Cherry Tree)":
            row.type = "CherryTree"
            row.coins_gained = 1
            row.points_gained = 2
            return True

        # Crossroads — Bath House
        if log == "${player_name} pays ${coins} coin and scores ${points} points (Bath House)":
            row.type = "BathHouse"
            row.coins_spent = coins
            row.points_gained = points
            return True

        # Crossroads — Legendary Object
        if log == ("${player_name} buys a Legendary Object (${name}) for ${coins} coin(s) "
                   "and scores ${points} point(s)"):
            row.type = "LegendaryObject"
            row.coins_spent = coins
            row.points_gained = points
            row.subtype = self._legendary_kind(args)
            return True
        if log == "${player_name} buys a Legendary Object (${name}) for ${coins} coin(s)":
            row.type = "LegendaryObject"
            row.coins_spent = coins
            row.subtype = self._legendary_kind(args)
            return True
        if log == "${player_name} doesn`t buy any Legendary Object":
            row.type = "LegendaryObject"
            row.subtype = "skipped"
            return True

        # Crossroads — Gaming Room. The args.coins field is NET (won - bet),
        # so we use args.won as the gross winnings and pair it with coins_spent
        # = bet for a correct purse model (gained - spent = net).
        if log == "${player_name} bets 2 coins and wins ${won}, and so earns ${coins} coins (Gaming Room)":
            row.type = "Gaming"
            row.subtype = "won"
            try:
                row.coins_gained = int(args.get("won", 0) or 0)
            except (TypeError, ValueError):
                row.coins_gained = max(coins, 0)
            row.coins_spent = 2
            return True
        if log == "${player_name} bets 2 coins and loses the money (Gaming Room)":
            row.type = "Gaming"
            row.subtype = "lost"
            row.coins_spent = 2
            return True

        # Crossroads — Amulet purchase / unbought. Like Calligraphy, the
        # specific amulet is in cards.<id>.type_arg, not at args top level.
        if log == "${player_name} buys an Amulet for ${coins} coin(s)":
            row.type = "Amulet"
            row.coins_spent = coins
            row.subtype = self._amulet_name(args)
            return True
        if log == "${player_name} doesn`t buy any Amulet":
            row.type = "Amulet"
            row.subtype = "skipped"
            return True

        # Crossroads — Calligraphy. The buy event tells us which calligraphy
        # via cards.<id>.type_arg; we store the name in subtype so the writer
        # can mark per-name ownership bools later.
        if log == "${player_name} buys a Calligraphy for ${coins} coin(s)":
            row.type = "Calligraphy"
            row.coins_spent = coins
            row.subtype = self._calligraphy_name(args)
            return True
        if log == "${player_name} doesn`t buy any Calligraphy":
            row.type = "Calligraphy"
            row.subtype = "skipped"
            return True
        if log == "${player_name} scores ${points} points (${calligraphy_name})":
            row.type = "CalligraphyScored"
            # Prefer calligraphy_card_type ("calligraphy_<n>") to derive type_arg,
            # so subtype matches the bool field name (e.g. "patience"). Fallback to
            # first word of calligraphy_name lowercased.
            ctype = args.get("calligraphy_card_type", "") or ""
            if ctype.startswith("calligraphy_"):
                ta = ctype[len("calligraphy_"):]
                row.subtype = CALLIGRAPHY_TYPE_ARG_TO_NAME.get(ta, ta)
            else:
                row.subtype = (args.get("calligraphy_name", "") or "").split()[0].lower()
            row.points_gained = points
            return True

        # Crossroads — Amulet effects.
        # Devotion redirects already-spent coins from bank to temple. Net change
        # to player purse is 0 (the Inn meal event already deducted these coins),
        # so we pair coins_gained with coins_donated to keep the purse model
        # `gained - spent - donated` consistent.
        if log == ("Devotion Amulet: ${player_name} gives ${amount} spent coin(s) to "
                   "the Temple (instead of the bank) and earns ${points} point(s)"):
            row.type = "AmuletUsed"
            row.subtype = "devotion"
            row.points_gained = points
            try:
                amount = int(args.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amount = 0
            row.coins_gained = amount
            row.coins_donated = amount
            return True
        if log == "Friendship Amulet: ${player_name} shares a single space with another Traveler":
            row.type = "AmuletUsed"
            row.subtype = "friendship"
            return True
        if log == "Health Amulet: ${player_name} can use both actions on this stop":
            row.type = "AmuletUsed"
            row.subtype = "health"
            return True
        if log == "Hospitality Amulet: ${player_name} enjoys today's meal for free":
            row.type = "AmuletUsed"
            row.subtype = "hospitality"
            return True
        if log == "Vitality Amulet: ${player_name} plays again":
            row.type = "AmuletUsed"
            row.subtype = "vitality"
            return True
        if log == "Fortune Amulet: ${player_name} earns ${coins} coin(s)":
            row.type = "AmuletUsed"
            row.subtype = "fortune"
            row.coins_gained = coins
            return True

        # Crossroads — Jirocho's gambling ability. Same convention as Gaming Room:
        # args.coins is NET; use args.won for gross gain.
        if log == "Jirocho: ${player_name} bets 1 coin and wins ${won}, and so earns ${coins} coin(s)":
            row.type = "JirochoGaming"
            row.subtype = "won"
            try:
                row.coins_gained = int(args.get("won", 0) or 0)
            except (TypeError, ValueError):
                row.coins_gained = max(coins, 0)
            row.coins_spent = 1
            return True
        if log == "Jirocho: ${player_name} bets 1 coin and loses the money":
            row.type = "JirochoGaming"
            row.subtype = "lost"
            row.coins_spent = 1
            return True
        if log == "Daigoro: ${player_name} gets a souvenir card and earns ${points} points":
            row.type = "DaigoroSouvenir"
            row.points_gained = points
            self._add_souvenirs(row, args)
            return True

        # Generic legendary/legend bonus VP (e.g. Murasame triggers on certain spaces)
        if log == "${legend_name}: ${player_name} earns ${points} bonus point(s)":
            row.type = "LegendBonus"
            row.subtype = (args.get("legend_name") or "")
            row.points_gained = points
            return True

        # Other traveler ability bonus log lines (not directly produced by the
        # "main" action). These are explicit scored points so we keep them.
        if log == "Nampo: ${player_name} scores ${points} bonus point(s)":
            row.type = "TravelerAbility"
            row.subtype = "Nampo"
            row.points_gained = points
            return True
        if log == "Mitsukuni: ${player_name} earns 1 bonus point":
            row.type = "TravelerAbility"
            row.subtype = "Mitsukuni"
            row.points_gained = 1
            return True
        if log == "Hirotada: ${player_name} gives 1 more coin to the temple (from the bank) and earns 1 more point":
            row.type = "TravelerAbility"
            row.subtype = "Hirotada"
            row.points_gained = 1
            # Bank-funded donation: pair coins_gained with coins_donated so
            # purse model nets to 0 (the coin came from the bank, not player).
            row.coins_gained = 1
            row.coins_donated = 1
            return True
        if log == "Umegae: ${player_name} earns 1 point and 1 coin":
            row.type = "TravelerAbility"
            row.subtype = "Umegae"
            row.points_gained = 1
            row.coins_gained = 1
            return True
        if log == "Gotozaemon: ${player_name} earns 1 coin":
            row.type = "TravelerAbility"
            row.subtype = "Gotozaemon"
            row.coins_gained = 1
            return True

        return False

    # ------------------------------------------------------------------
    # Accumulation
    # ------------------------------------------------------------------

    def _apply_move_to_player(self, row: TokaidoMove, pr: Optional[TokaidoPlayerResult]) -> None:
        if pr is None:
            return
        pr.num_actions += 1
        pr.coins_gained_total += row.coins_gained
        pr.coins_spent_total += row.coins_spent
        pr.coins_donated_total += row.coins_donated
        pr.num_souvenirs_food += row.souvenirs_food
        pr.num_souvenirs_clothing += row.souvenirs_clothing
        pr.num_souvenirs_art += row.souvenirs_art
        pr.num_souvenirs_trinket += row.souvenirs_trinket

        t = row.type
        pts = row.points_gained
        sub = (row.subtype or "").lower()
        if t == "Panorama":
            # subtype is "Mountain" / "Sea" / "Field" (capitalized — first word
            # of "Mountain panorama"). Route to per-color fields.
            if sub == "mountain":
                pr.vp_panorama_mountain += pts
                pr.num_panorama_cards_mountain += 1
            elif sub == "sea":
                pr.vp_panorama_sea += pts
                pr.num_panorama_cards_sea += 1
            elif sub == "field":
                pr.vp_panorama_field += pts
                pr.num_panorama_cards_field += 1
        elif t == "Temple":
            pr.vp_temple += pts
            pr.num_donations += 1
        elif t == "TempleRank":
            pr.vp_temple_rank += pts
        elif t == "HotSpring":
            pr.vp_hot_spring += pts
        elif t == "Encounter":
            pr.num_encounters += 1
            # Miko encounter is a temple donation — route VP to vp_temple and
            # count as a donation, mirroring the Devotion amulet treatment.
            if sub == "miko":
                pr.vp_temple += pts
                pr.num_donations += 1
            elif sub.startswith("annaibito"):
                # Annaibito places a panorama card in the player's collection
                # and scores it inline — no follow-up Panorama event fires.
                # Attribute VP and card count to the panorama color (parsed
                # into subtype suffix at handler time).
                color = sub[len("annaibito_"):] if "_" in sub else ""
                if color == "mountain":
                    pr.vp_panorama_mountain += pts
                    pr.num_panorama_cards_mountain += 1
                elif color == "sea":
                    pr.vp_panorama_sea += pts
                    pr.num_panorama_cards_sea += 1
                elif color == "field":
                    pr.vp_panorama_field += pts
                    pr.num_panorama_cards_field += 1
                else:
                    pr.vp_encounter += pts
            else:
                pr.vp_encounter += pts
        elif t == "Inn":
            pr.vp_inn += pts
            if sub != "skipped":
                pr.num_meals += 1
        elif t == "Village":
            pr.vp_village += pts
            if sub != "skipped":
                pr.num_villages_visited += 1
        elif t == "Achievement":
            pr.vp_achievement += pts
            # subtype for first-to-finish events is "Mountain panorama" /
            # "Sea panorama" / "Field panorama" (case from BGA log args).
            if sub == "mountain panorama":
                pr.first_to_finish_mountain = True
            elif sub == "sea panorama":
                pr.first_to_finish_sea = True
            elif sub == "field panorama":
                pr.first_to_finish_field = True
        elif t == "CalligraphyScored":
            pr.vp_calligraphy += pts
        elif t == "Calligraphy":
            if sub != "skipped":
                pr.num_calligraphies += 1
                # Mark per-name ownership if subtype is a known calligraphy name.
                attr = f"has_calligraphy_{sub}"
                if hasattr(pr, attr):
                    setattr(pr, attr, True)
        elif t == "LegendaryObject":
            # subtype is the category from LEGENDARY_OBJECT_TYPE: script /
            # offering / sword (lowercase via `sub`). "skipped" goes nowhere.
            if sub == "script":
                pr.vp_legendary_script += pts
                pr.num_legendary_script += 1
            elif sub == "offering":
                pr.vp_legendary_offering += pts
                pr.num_legendary_offering += 1
            elif sub == "sword":
                pr.vp_legendary_sword += pts
                pr.num_legendary_sword += 1
        elif t == "Amulet":
            if sub != "skipped":
                pr.num_amulets_purchased += 1
        elif t == "AmuletUsed":
            pr.num_amulets_used += 1
            # Devotion amulet is a temple donation — route its VP to vp_temple
            # and count as a donation. Other amulets give 0 VP here.
            if sub == "devotion":
                pr.vp_temple += pts
                pr.num_donations += 1
        elif t == "BathHouse":
            pr.vp_bath_house += pts
        elif t == "CherryTree":
            pr.vp_cherry_tree += pts
        elif t == "LegendBonus":
            pr.vp_legend_bonus += pts
        elif t == "TravelerAbility":
            pr.vp_other += pts
        elif t in {"Traveled", "Farm", "Gaming", "JirochoGaming", "DaigoroSouvenir"}:
            pr.vp_other += pts

    # ------------------------------------------------------------------
    # Tiny helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _space_label(args: Dict) -> str:
        pos = str(args.get("position", ""))
        space = POSITION_TO_SPACE.get(pos, f"unknown_{pos}")
        spot = args.get("position_order", "")
        return f"{space}_{spot}" if spot != "" else space

    @staticmethod
    def _panorama_card(args: Dict) -> str:
        cards = args.get("cards", [])
        if isinstance(cards, dict):
            cards = list(cards.values())
        if not cards:
            return ""
        try:
            return str(cards[0].get("type", "")).capitalize()
        except (AttributeError, KeyError):
            return ""

    @staticmethod
    def _legendary_kind(args: Dict) -> str:
        cards = args.get("cards", {})
        if isinstance(cards, dict):
            cards = list(cards.values())
        if not cards:
            return ""
        try:
            return LEGENDARY_OBJECT_TYPE.get(str(cards[0].get("type_arg", "")), "")
        except (AttributeError, KeyError):
            return ""

    @staticmethod
    def _calligraphy_name(args: Dict) -> str:
        """Extract calligraphy name (e.g. 'patience') from a buy event's cards."""
        cards = args.get("cards", {})
        if isinstance(cards, dict):
            cards = list(cards.values())
        for c in cards:
            if isinstance(c, dict) and c.get("type") == "calligraphy":
                return CALLIGRAPHY_TYPE_ARG_TO_NAME.get(str(c.get("type_arg", "")), "")
        return ""

    @staticmethod
    def _amulet_name(args: Dict) -> str:
        """Extract amulet name (e.g. 'devotion') from a buy event's cards."""
        cards = args.get("cards", {})
        if isinstance(cards, dict):
            cards = list(cards.values())
        for c in cards:
            if isinstance(c, dict) and c.get("type") == "amulet":
                return AMULET_TYPE.get(str(c.get("type_arg", "")), "")
        return ""

    @staticmethod
    def _add_souvenirs(row: TokaidoMove, args: Dict) -> None:
        cards = args.get("cards", [])
        if isinstance(cards, dict):
            cards = list(cards.values())
        for card in cards:
            try:
                if card.get("type") != "souvenir":
                    continue
                cat = SOUVENIR_TYPE_ARG_TO_CATEGORY.get(str(card.get("type_arg", "")))
            except AttributeError:
                continue
            if cat == "food":
                row.souvenirs_food += 1
            elif cat == "clothing":
                row.souvenirs_clothing += 1
            elif cat == "art":
                row.souvenirs_art += 1
            elif cat == "trinket":
                row.souvenirs_trinket += 1
