"""
Wingspan BGA replay parser.

Consumes the JSON gamelogs format returned by the BGA archive API
(`/archive/archive/logs.html`: a flat list of packets). Yields
WingspanGameData with per-player, per-move, per-bird and per-round-goal rows.

Event dispatch is on `event.type`; the log template only separates sub-cases
(`noAction`, `gainFood`). See docs/wingspan/bga_replay_format.md.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from typing import Dict, List, Optional

from .wingspan_constants import (
    ACTION_BY_HABITAT,
    BIRD_NAMES,
    BONUS_NAMES,
    FOOD_NAMES,
    GOAL_NAMES,
    HABITAT_BY_ROW,
)
from .wingspan_models import (
    FOODS,
    WingspanBird,
    WingspanGameData,
    WingspanMove,
    WingspanPlayerResult,
    WingspanRoundGoal,
)

logger = logging.getLogger(__name__)

# noAction log template -> (row type, detail). Templates not listed here
# (player-level notes such as "chooses to stop drawing bird cards") emit no row.
NO_ACTION = {
    "${player_name} chooses not to use ${bird_name}'s power": ("power_declined", ""),
    "${bird_name}: ${player_name} has chosen not to draw a card": ("power_declined", ""),
    "${bird_name}: ${player_name} repeats ${repeated_name}'s power": ("repeat_power", ""),
    "${bird_name}: None of the rolled dice match ${food_log}": ("hunt", "fail"),
    "${bird_name}: There are no dice not in the birdfeeder": ("power_failed", "no_dice_outside_feeder"),
    "${bird_name} auto-activation failed": ("power_failed", "auto_activation_failed"),
    "${bird_name} is not the rightmost bird in the ${habitat_name}": ("power_failed", "not_rightmost"),
    "${bird_name}: ${player_name} has no ${food_type_name}": ("power_failed", "no_food"),
    "${bird_name}: ${player_name} has no birds in hand": ("power_failed", "no_cards"),
    "${bird_name}: ${player_name} has no birds in hand to discard": ("power_failed", "no_cards"),
    "${bird_name}: ${player_name} has no eggs on other birds": ("power_failed", "no_eggs"),
    "${bird_name}: ${player_name} has no other birds that can be activated in ${habitat_name}": ("power_failed", "nothing_to_repeat"),
    "${bird_name}: ${player_name} has no other predator birds that can be activated in ${habitat_name}": ("power_failed", "nothing_to_repeat"),
    "${bird_name}: ${player_name} has no more locations available in ${habitat_name}": ("power_failed", "habitat_full"),
    "${bird_name}: After rerolling, no ${food_type_name} available in the birdfeeder": ("power_failed", "food_not_in_feeder"),
    "${bird_name}: no ${food_type_name} available in the birdfeeder": ("power_failed", "food_not_in_feeder"),
    "${bird_name}: no available nests to lay eggs": ("power_failed", "no_nest_space"),
    "${bird_name}: no players can lay eggs!": ("power_failed", "no_nest_space"),
    "${bird_name}: no space in nest to lay eggs": ("power_failed", "no_nest_space"),
    "${bird_name}: no space to lay an egg": ("power_failed", "no_nest_space"),
}


def _slot(location) -> Optional[int]:
    """Board slot as an int. Accepts 9, "9" and "tableau_9"."""
    try:
        return int(str(location).rsplit("_", 1)[-1])
    except (TypeError, ValueError):
        return None


def _habitat(slot: Optional[int]) -> str:
    return HABITAT_BY_ROW.get(slot // 8, "") if slot else ""


def _label(location) -> str:
    """Slot -> "forest_2"."""
    slot = _slot(location)
    hab = _habitat(slot)
    return f"{hab}_{slot % 8}" if hab else ""


def _keyed(obj) -> Dict:
    """Id-keyed map. BGA's PHP serializes a map whose keys are 0..n-1 as a list,
    so a map holding only bonus card 0 arrives as a one-element list."""
    if isinstance(obj, list):
        return dict(enumerate(obj))
    return obj if isinstance(obj, dict) else {}


def _bird(type_arg) -> str:
    try:
        i = int(type_arg)
    except (TypeError, ValueError):
        return ""
    if i < 0:
        return ""
    return BIRD_NAMES.get(i, f"bird_{i}")


def _foods(values) -> Counter:
    """List of food ids -> Counter of names. Sentinels (-1/-2) are dropped."""
    out = Counter()
    for v in values or []:
        try:
            name = FOOD_NAMES.get(int(v))
        except (TypeError, ValueError):
            name = None
        if name:
            out[name] += 1
    return out


class _PlayerState:
    def __init__(self):
        self.food = Counter()
        self.eggs = Counter()      # slot -> eggs on the bird there
        self.tucked = Counter()
        self.cached = Counter()
        self.board: Dict[int, WingspanBird] = {}
        self.hand = 0
        self.drawn = set()         # bird names ever drawn into hand
        self.turns = 0
        self.goal_values: List[Optional[int]] = []   # latest private count per goal
        # Private halves of events, queued until the matching public half arrives.
        self.pending_tuck: List[str] = []         # card named by a hand tuck
        self.pending_draw: List[List[str]] = []   # cards named by a deck draw
        self.pending_bonus = ""    # bonus card kept from the last draw


class WingspanParser:

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def parse_packets(self, packets: List[Dict], table_id: str = "") -> Optional[WingspanGameData]:
        """Parse a flat list of BGA packets into WingspanGameData.

        Returns None if the replay should be skipped (conceded, no result).
        """
        skip = self.should_skip(packets)
        if skip:
            logger.debug(f"{table_id}: skipping ({skip})")
            return None

        result = self._extract_result(packets)
        entries = self._result_entries(result)

        game = WingspanGameData(table_id=str(table_id), num_players=len(entries))
        game.start_time = self._time(packets[0])
        game.end_time = self._time(packets[-1])
        tstats = result.get("table", {}).get("stats", {}) or {}
        for k in ("40", "41", "42", "43"):
            try:
                gid = int(tstats[k])
            except (KeyError, TypeError, ValueError):
                gid = None
            game.goal_ids.append(gid)
            game.goals.append(GOAL_NAMES.get(gid, "") if gid is not None else "")

        self._game = game
        self._st: Dict[str, _PlayerState] = {}
        for r in entries:
            pid = str(r["player"])
            game.players[pid] = WingspanPlayerResult(player_id=pid, player_name=r.get("name", ""))
            self._st[pid] = _PlayerState()

        self._round = 1
        self._turn_in_round = 0
        self._in_turn = False
        self._active = ""
        self._action = ""
        self._action_column: Optional[int] = None

        for packet in packets:
            channel = packet.get("channel", "")
            private_pid = channel[len("/player/p"):] if channel.startswith("/player/p") else ""
            for event in packet.get("data", []):
                if not isinstance(event, dict):
                    continue
                args = event.get("args")
                if not isinstance(args, dict):
                    args = {}
                if private_pid:
                    self._on_private(private_pid, event.get("type"), args)
                else:
                    self._on_public(event.get("type"), event.get("log") or "", args)

        self._finish(entries)
        return game

    def parse_json_file(self, path: str, table_id: str = "") -> Optional[WingspanGameData]:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        packets = self._normalize_to_packet_list(raw)
        return self.parse_packets(packets, table_id=table_id or self._table_id_from_path(path))

    # ------------------------------------------------------------------
    # Skip detection
    # ------------------------------------------------------------------

    def should_skip(self, packets: List[Dict]) -> Optional[str]:
        """Return reason string if this replay should be skipped, else None."""
        if not packets:
            return "empty"
        result = self._extract_result(packets)
        if not result or not self._result_entries(result):
            return "no_result"
        if result.get("table", {}).get("concede"):
            return "conceded"
        # Belt and braces: a concede/quit event without the table flag.
        for packet in packets:
            for event in packet.get("data", []):
                if isinstance(event, dict) and event.get("type") in (
                        "playerConcedeGame", "gameQuitWithNoPenalty", "gameResultNeutralized"):
                    return "conceded"
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_to_packet_list(raw) -> List[Dict]:
        """Accept a bare packet list or the dict-wrapped g_gamelogs form."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            inner = raw.get("data")
            if isinstance(inner, dict):
                inner = inner.get("data") or inner.get("logs")
            if isinstance(inner, list):
                return inner
        return []

    @staticmethod
    def _table_id_from_path(path: str) -> str:
        return os.path.splitext(os.path.basename(path))[0]

    @staticmethod
    def _time(packet: Dict) -> Optional[int]:
        try:
            return int(packet.get("time"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_result(packets: List[Dict]) -> Dict:
        """The end-of-game block (`args.args` of the last gameStateChange): {table, result}."""
        for packet in reversed(packets):
            for event in reversed(packet.get("data", [])):
                if not isinstance(event, dict):
                    continue
                args = event.get("args")
                if not isinstance(args, dict):
                    continue
                inner = args.get("args")
                if isinstance(inner, dict) and "result" in inner:
                    return inner
        return {}

    @staticmethod
    def _result_entries(result: Dict) -> List[Dict]:
        entries = result.get("result")
        if isinstance(entries, dict):
            return list(entries.values())
        return entries if isinstance(entries, list) else []

    def _owner_of(self, bird_name: str) -> str:
        """Player whose board holds `bird_name` (bird cards are unique)."""
        for pid, st in self._st.items():
            for b in st.board.values():
                if b.bird == bird_name:
                    return pid
        return ""

    def _row(self, type_: str, pid, source: str = "", **kw) -> WingspanMove:
        row = WingspanMove(
            move_number=len(self._game.moves) + 1,
            player_id=str(pid or ""),
            type=type_,
            source=source or "",
            **kw,
        )
        if self._in_turn:
            row.round_number = self._round
            row.turn_number = self._turn_in_round
            row.active_player_id = self._active
            row.player_turn = self._st[self._active].turns if self._active in self._st else None
            row.action = self._action
            row.action_column = self._action_column
        self._game.moves.append(row)
        return row

    def _food(self, row: WingspanMove, gained: Counter = None, spent: Counter = None) -> None:
        st = self._st.get(row.player_id)
        pr = self._game.players.get(row.player_id)
        for name, n in (gained or {}).items():
            setattr(row, f"gain_{name}", getattr(row, f"gain_{name}") + n)
            if st:
                st.food[name] += n
                pr.food_gained += n
        for name, n in (spent or {}).items():
            setattr(row, f"cost_{name}", getattr(row, f"cost_{name}") + n)
            if st:
                st.food[name] -= n
                pr.food_spent += n

    def _leave_hand(self, pid: str, names: List[str]) -> None:
        """Cards leaving a hand. Any never drawn must have been kept at setup."""
        st = self._st.get(pid)
        if not st:
            return
        pr = self._game.players[pid]
        for name in names:
            st.hand -= 1
            if name and name not in st.drawn and name not in pr.starting_birds_kept_known:
                pr.starting_birds_kept_known.append(name)

    # ------------------------------------------------------------------
    # Private channel: only the hidden half of events
    # ------------------------------------------------------------------

    def _on_private(self, pid: str, etype: str, args: Dict) -> None:
        st = self._st.get(pid)
        if st is None:
            return
        if etype in ("updateGoalData", "updateBonusData"):
            pr = self._game.players[pid]
            bonus = _keyed(args.get("bonus_data"))
            if bonus and not pr.starting_bonus and not pr.bonus_cards_drawn:
                if len(bonus) == 1:
                    pr.starting_bonus = BONUS_NAMES.get(_slot(next(iter(bonus))), "")
            goals = args.get("goal_data")
            if isinstance(goals, list):
                vals = []
                for g in goals:
                    try:
                        vals.append(int(g.get("value")))
                    except (AttributeError, TypeError, ValueError):
                        vals.append(None)
                st.goal_values = vals
        elif etype == "drawBirdsPrivate":
            if args.get("location") == "hand":
                st.pending_draw.append([_bird(x) for x in args.get("type_args") or []])
        elif etype == "tuckCardFromHandPrivate":
            st.pending_tuck.append(_bird(args.get("tucked_card")) or args.get("tucked_name", ""))
        elif etype == "moveBonusPrivate":
            if args.get("location") == "hand":
                ids = args.get("type_args") or []
                st.pending_bonus = BONUS_NAMES.get(_slot(ids[0]), "") if ids else ""

    # ------------------------------------------------------------------
    # Table channel
    # ------------------------------------------------------------------

    def _on_public(self, etype: str, log: str, args: Dict) -> None:
        handler = getattr(self, f"_ev_{etype}", None)
        if handler:
            handler(log, args)

    def _ev_initialDiscardPublic(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        pr = self._game.players[pid]
        discarded = [_bird(b) for b in a.get("bird_discard") or []]
        kept_food = Counter({name: 1 for name in FOODS}) - _foods(a.get("food_discard"))
        bonus = a.get("bonus_discard") or []
        if not isinstance(bonus, list):
            bonus = [bonus]
        pr.starting_birds_discarded = discarded
        pr.starting_birds_kept = 5 - len(discarded)
        pr.starting_food = [f for f in FOODS if kept_food[f]]
        pr.starting_bonus_discarded = BONUS_NAMES.get(_slot(bonus[0]), "") if bonus else ""
        st.hand = pr.starting_birds_kept
        row = self._row("setup", pid, birds=";".join(discarded), gain_cards=pr.starting_birds_kept)
        self._food(row, gained=kept_food)
        pr.food_gained -= sum(kept_food.values())   # starting food is not a gain

    def _ev_setCube(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        slot = _slot(a.get("location")) or 0
        st.turns += 1
        self._in_turn = True
        self._turn_in_round += 1
        self._active = pid
        self._action = ACTION_BY_HABITAT.get(_habitat(slot), "play_bird")
        self._action_column = slot % 8 if slot else None
        pr = self._game.players[pid]
        setattr(pr, f"turns_{self._action}", getattr(pr, f"turns_{self._action}") + 1)
        if not pr.seat_order:
            pr.seat_order = 1 + sum(1 for p in self._game.players.values() if p.seat_order)
            if pr.seat_order == 1:
                self._game.first_player_id = pid

    def _ev_moveCube(self, log, a):
        # The cube stopping on a bird activates its brown power.
        name = a.get("bird_name")
        st = self._st.get(str(a.get("player_id")))
        if name and st:
            bird = st.board.get(_slot(a.get("location")))
            if bird is not None:
                bird.activations += 1

    def _ev_resetPlayerCubes(self, log, a):
        self._in_turn = False

    def _ev_changeFirstPlayer(self, log, a):
        try:
            self._round = int(a.get("current_round"))
        except (TypeError, ValueError):
            self._round += 1
        self._turn_in_round = 0
        self._in_turn = False

    def _ev_setupFinalScoring(self, log, a):
        self._in_turn = False

    def _ev_playBird(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        slot = _slot(a.get("location"))
        name = _bird(a.get("bird_type")) or a.get("bird_name", "")
        food = _foods(a.get("food_paid"))
        egg_slots = [_slot(x) for x in a.get("eggs_paid") or []]
        row = self._row("play_bird", pid, location=_label(slot), birds=name,
                        cost_cards=1, cost_eggs=len(egg_slots))
        self._food(row, spent=food)
        for s in egg_slots:
            st.eggs[s] -= 1
        pr = self._game.players[pid]
        pr.eggs_spent += len(egg_slots)
        self._leave_hand(pid, [name])
        bird = WingspanBird(
            player_id=pid, bird_id=int(a.get("bird_type")), bird=name,
            play_order=len([b for b in self._game.birds if b.player_id == pid]) + 1,
            round_number=self._round, turn_number=self._turn_in_round, player_turn=st.turns,
            habitat=_habitat(slot), column=slot % 8, cost_eggs=len(egg_slots),
            final_habitat=_habitat(slot), final_column=slot % 8,
        )
        for f in FOODS:
            setattr(bird, f"cost_{f}", food[f])
        st.board[slot] = bird
        self._game.birds.append(bird)

    def _ev_gainFood(self, log, a):
        pid = str(a.get("player_id"))
        food = _foods(a.get("food_types"))
        discard = _bird(a.get("card_discard"))
        if not food and not discard:
            return   # "chooses not to take food"
        row = self._row("gain_food", pid, a.get("bird_name"), detail="birdfeeder", birds=discard)
        self._food(row, gained=food)
        if discard:   # forest bonus: discard a card for an extra food
            row.cost_cards = 1
            self._leave_hand(pid, [discard])
            self._game.players[pid].cards_discarded += 1

    def _ev_foodFromSupply(self, log, a):
        pid = str(a.get("player_id"))
        try:
            delta = int(a.get("delta"))
        except (TypeError, ValueError):
            return
        food = _foods([a.get("food_type")] * abs(delta))
        if delta > 0:
            self._food(self._row("gain_food", pid, a.get("bird_name"), detail="supply"), gained=food)
        elif delta < 0:
            self._food(self._row("pay_food", pid, a.get("bird_name")), spent=food)

    def _ev_layEggs(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        slots = [_slot(x) for x in a.get("locations") or []]
        row = self._row("lay_eggs", pid, a.get("bird_name"),
                        location=";".join(_label(s) for s in slots), gain_eggs=len(slots))
        for s in slots:
            st.eggs[s] += 1
            if s in st.board:
                st.board[s].eggs_laid += 1
        self._game.players[pid].eggs_laid += len(slots)
        # Grassland bonus: discard a food for an extra egg.
        self._food(row, spent=_foods([a.get("food_discard")]))

    def _ev_discardEgg(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        slot = _slot(a.get("location"))
        # Wetland bonus ("to draw another bird") has the egg's bird in bird_name;
        # power-driven discards have the power's bird there and the egg's in source_bird_name.
        source = a.get("bird_name") if a.get("source_bird_name") else ""
        self._row("discard_egg", pid, source, location=_label(slot), cost_eggs=1)
        st.eggs[slot] -= 1
        self._game.players[pid].eggs_spent += 1

    def _draw(self, pid: str, names: List[str], source: str, where: str, n: int = 0) -> None:
        st = self._st.get(pid)
        n = len(names) or n
        if st is None or not n:
            return
        self._row("draw_cards", pid, source, birds=";".join(names), detail=where, gain_cards=n)
        st.hand += n
        st.drawn.update(names)
        pr = self._game.players[pid]
        pr.cards_drawn += n
        if where == "tray":
            pr.cards_drawn_tray += n
        else:
            pr.cards_drawn_deck += n

    def _ev_drawBirdFromTray(self, log, a):
        # location "special" = moved to a shared display (American Oystercatcher), not a hand.
        if a.get("location") == "hand":
            self._draw(str(a.get("player_id")), [_bird(a.get("type_arg"))], a.get("bird_name"), "tray")

    def _ev_drawBirdsPublic(self, log, a):
        if a.get("location") != "hand":
            return
        # Card ids are on the public event until late 2024; after that only on
        # the private half, which arrives first.
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        private = st.pending_draw.pop(0) if st.pending_draw else []
        names = [_bird(x) for x in a.get("type_args") or []] or private
        where = "display" if a.get("prev_location") == "special" or log.endswith("draws a card") else "deck"
        self._draw(pid, names, a.get("bird_name"), where, n=int(a.get("nbr") or 0))

    def _ev_tuckCardFromHandPublic(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        slot = _slot(a.get("location"))
        name = st.pending_tuck.pop(0) if st.pending_tuck else ""
        self._row("tuck_card", pid, a.get("bird_name"), location=_label(slot), birds=name,
                  detail="hand", cost_cards=1, tucked=1)
        st.tucked[slot] += 1
        self._game.players[pid].cards_tucked += 1
        self._leave_hand(pid, [name])

    def _ev_tuckCardFromDeck(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        slot = _slot(a.get("location"))
        n = int(a.get("nbr") or 0)
        self._row("tuck_card", pid, a.get("bird_name"), location=_label(slot), detail="deck", tucked=n)
        st.tucked[slot] += n
        self._game.players[pid].cards_tucked += n

    def _ev_huntWingspan(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        slot = _slot(a.get("location"))
        ok = bool(a.get("success"))
        self._row("hunt", pid, a.get("bird_name"), location=_label(slot), birds=_bird(a.get("type_arg")),
                  detail="success" if ok else "fail", tucked=int(ok))
        if ok:
            st.tucked[slot] += 1
            self._game.players[pid].cards_tucked += 1

    def _ev_cacheFood(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        slot = _slot(a.get("location"))
        try:
            n = int(a.get("delta", 1))
        except (TypeError, ValueError):
            n = 1
        try:
            food = FOOD_NAMES.get(int(a.get("food_type")), "")
        except (TypeError, ValueError):
            food = ""
        self._row("cache_food", pid, a.get("bird_name"), location=_label(slot), detail=food, cached=n)
        st.cached[slot] += n
        self._game.players[pid].food_cached += n

    def _ev_discard(self, log, a):
        pid = str(a.get("player_id"))
        names = [_bird(b) for b in a.get("bird_discard") or []]
        if not names:
            return
        self._row("discard_cards", pid, birds=";".join(names), cost_cards=len(names))
        self._leave_hand(pid, names)
        self._game.players[pid].cards_discarded += len(names)

    def _ev_moveBonusPublic(self, log, a):
        # Only the discard half is public; it closes a "draw 2 bonus cards, keep 1".
        if a.get("location") != "discard":
            return
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        kept, st.pending_bonus = st.pending_bonus, ""
        ids = a.get("type_args") or []
        self._row("draw_bonus", pid, detail=kept)
        self._row("discard_bonus", pid, detail=BONUS_NAMES.get(_slot(ids[0]), "") if ids else "")
        self._game.players[pid].bonus_cards_drawn += 1

    def _ev_changeHabitat(self, log, a):
        pid = str(a.get("player_id"))
        st = self._st.get(pid)
        if st is None:
            return
        src, dst = _slot(a.get("from_location")), _slot(a.get("to_location"))
        name = _bird(a.get("type_arg")) or a.get("bird_name", "")
        self._row("move_bird", pid, name, location=_label(dst), birds=name, detail=_label(src))
        bird = st.board.pop(src, None)
        if bird is not None:
            st.board[dst] = bird
            bird.times_moved += 1
            bird.final_habitat, bird.final_column = _habitat(dst), dst % 8
        for counter in (st.eggs, st.tucked, st.cached):
            counter[dst] = counter.pop(src, 0)

    def _ev_noAction(self, log, a):
        kind = NO_ACTION.get(log)
        if not kind:
            return
        name = a.get("bird_name", "")
        pid = str(a.get("player_id") or self._owner_of(name) or self._active)
        detail = a.get("repeated_name", "") if kind[0] == "repeat_power" else kind[1]
        self._row(kind[0], pid, name, detail=detail)

    def _ev_scoreGoal(self, log, a):
        self._in_turn = False
        try:
            rnd = int(a.get("round")) + 1
        except (TypeError, ValueError):
            rnd = self._round
        gid = self._game.goal_ids[rnd - 1] if 0 < rnd <= len(self._game.goal_ids) else None
        goal = self._game.goals[rnd - 1] if 0 < rnd <= len(self._game.goals) else ""
        pids = [str(p) for p in a.get("player_ids") or []]
        for pid in pids:
            st = self._st.get(pid)
            if st is None:
                continue
            points = int(a.get("score_value") or 0)
            value = a.get("value")
            if value is None and len(st.goal_values) >= rnd:
                value = st.goal_values[rnd - 1]
            self._game.round_goals.append(WingspanRoundGoal(
                round_number=rnd, goal_id=gid, goal=goal, player_id=pid,
                value=int(value) if value is not None else None,
                position=int(a["position"]) if a.get("position") is not None else None,
                tied=len(pids) > 1, points=points,
            ))
            row = self._row("round_goal", pid, detail=goal or (f"goal_{gid}" if gid is not None else ""),
                            gain_vp=points)
            row.round_number = rnd

    def _ev_scoreBonus(self, log, a):
        pid = str(a.get("player_id"))
        if pid in self._st:
            self._row("bonus_score", pid, detail=a.get("bonus_name", ""), gain_vp=int(a.get("score") or 0))

    def _ev_finalScoringPlayerSetup(self, log, a):
        pr = self._game.players.get(str(a.get("player_id")))
        if pr is not None:
            pr.bonus_cards = [BONUS_NAMES.get(_slot(k), str(k)) for k in _keyed(a.get("scored_bonuses"))]

    def _ev_scoreBirds(self, log, a):
        pid = str(a.get("player_id"))
        st, pr = self._st.get(pid), self._game.players.get(pid)
        if st is None:
            return
        pr.vp_birds = int(a.get("score_birds") or 0)
        by_slot = a.get("bird_vp_by_location")
        by_slot = {_slot(k): int(v) for k, v in by_slot.items()} if isinstance(by_slot, dict) else {}
        if set(by_slot) != set(st.board):
            self._game.warnings.append(f"{pid}: board slots {sorted(st.board)} != scored {sorted(by_slot)}")
        for slot, vp in by_slot.items():
            if slot in st.board:
                st.board[slot].vp = vp

    def _ev_scoreGoals(self, log, a):
        pr = self._game.players.get(str(a.get("player_id")))
        if pr is None:
            return
        pr.vp_goals = int(a.get("score_goals") or 0)
        by_goal = a.get("score_by_goal")
        if isinstance(by_goal, dict):
            for k, v in by_goal.items():
                if str(k) in ("1", "2", "3", "4"):
                    setattr(pr, f"vp_goal_{k}", int(v or 0))

    def _ev_scoreEggs(self, log, a):
        pid = str(a.get("player_id"))
        st, pr = self._st.get(pid), self._game.players.get(pid)
        if st is None:
            return
        pr.vp_eggs = int(a.get("nbr") or 0)
        if sum(st.eggs.values()) != pr.vp_eggs or min(st.eggs.values(), default=0) < 0:
            self._game.warnings.append(f"{pid}: tracked eggs {sum(st.eggs.values())} != scored {pr.vp_eggs}")

    def _check_by_slot(self, pid: str, what: str, tracked: Counter, scored) -> None:
        scored = {_slot(k): int(v) for k, v in scored.items()} if isinstance(scored, dict) else {}
        if {k: v for k, v in tracked.items() if v} != {k: v for k, v in scored.items() if v}:
            self._game.warnings.append(f"{pid}: tracked {what} {dict(tracked)} != scored {scored}")

    def _ev_scoreCache(self, log, a):
        pid = str(a.get("player_id"))
        if pid in self._st:
            self._game.players[pid].vp_cached = int(a.get("score_cache") or 0)
            self._check_by_slot(pid, "cache", self._st[pid].cached, a.get("cache_by_location"))

    def _ev_scoreTucked(self, log, a):
        pid = str(a.get("player_id"))
        if pid in self._st:
            self._game.players[pid].vp_tucked = int(a.get("score_tucked") or 0)
            self._check_by_slot(pid, "tucked", self._st[pid].tucked, a.get("tucked_by_location"))

    # ------------------------------------------------------------------
    # End of game
    # ------------------------------------------------------------------

    def _finish(self, entries: List[Dict]) -> None:
        game = self._game
        for r in entries:
            pid = str(r["player"])
            pr, st = game.players[pid], self._st[pid]
            pr.final_score = int(r.get("score") or 0)
            pr.score_aux = int(r.get("score_aux") or 0)
            pr.final_rank = int(r.get("rank") or 0)
            if pr.final_rank == 1 and not r.get("tie", False):
                pr.is_winner = True
                game.winner_player_id = pid
                game.winner_player_name = pr.player_name

            pr.vp_bonus = sum(m.gain_vp for m in game.moves if m.type == "bonus_score" and m.player_id == pid)
            pr.num_birds = len(st.board)
            for bird in st.board.values():
                setattr(pr, f"birds_{bird.final_habitat}", getattr(pr, f"birds_{bird.final_habitat}") + 1)
            for slot, bird in st.board.items():
                bird.final_eggs = st.eggs[slot]
                bird.final_cached = st.cached[slot]
                bird.final_tucked = st.tucked[slot]
            pr.final_food = sum(st.food.values())
            pr.final_hand = st.hand

            total = pr.vp_birds + pr.vp_bonus + pr.vp_goals + pr.vp_eggs + pr.vp_cached + pr.vp_tucked
            if total != pr.final_score:
                game.warnings.append(f"{pid}: vp components {total} != final_score {pr.final_score}")
            if st.turns != 26:
                game.warnings.append(f"{pid}: {st.turns} turns, expected 26")
            if min(st.food.values(), default=0) < 0:
                game.warnings.append(f"{pid}: negative food stock {dict(st.food)}")
            if st.hand < 0:
                game.warnings.append(f"{pid}: negative hand size {st.hand}")
            if len(pr.starting_birds_kept_known) > pr.starting_birds_kept:
                game.warnings.append(f"{pid}: {len(pr.starting_birds_kept_known)} undrawn cards left the hand, kept {pr.starting_birds_kept}")
            if pr.score_aux != pr.final_food:
                game.warnings.append(f"{pid}: final food {pr.final_food} != score_aux {pr.score_aux}")
