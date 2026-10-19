"""Possession-based Markov match engine.

The engine walks the ball carrier through a chain of decisions. At each decision the
defending team may press (pressure, tackle, foul); then the carrier shoots, carries,
passes or crosses with probabilities that depend on pitch zone, pressure, ratings and
fatigue. Pass targets come from formation target positions (sim.formation), so the
ball lands where the tracking model has players standing.

Every event's coordinates are in the acting team's frame (attacking towards x=105).
Events with no team (period_end) use the home team's frame.
"""

from __future__ import annotations

import math
import random
from collections.abc import Generator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from contracts import Club, MatchEvent, Player, World
from sim.formation import (
    CENTRE,
    FORMATIONS,
    PITCH_LENGTH,
    PITCH_WIDTH,
    Slot,
    clamp,
    flip,
    target_position,
)
from sim.physics import PASS_DRAG, SHOT_DRAG, carry_speed_ms, flight_ms
from sim.ulid import UlidFactory
from sim.world import club as find_club

HALF_MS = 45 * 60_000
HALFTIME_BREAK_MS = 15 * 60_000
# A fixed synthetic kickoff instant keeps event ids reproducible for a given match id.
DEFAULT_KICKOFF_EPOCH_MS = int(datetime(2026, 10, 27, 18, 0, tzinfo=UTC).timestamp() * 1000)

BOX_X = 88.5
BOX_Y = (13.84, 54.16)
GOAL_HALF_WIDTH = 3.66
PENALTY_SPOT = (94.0, 34.0)

ROLE_GROUP = {
    "GK": "GK",
    "CB": "DEF",
    "RB": "DEF",
    "LB": "DEF",
    "RWB": "DEF",
    "LWB": "DEF",
    "DM": "MID",
    "CM": "MID",
    "AM": "MID",
    "RM": "MID",
    "LM": "MID",
    "RW": "FWD",
    "LW": "FWD",
    "ST": "FWD",
}
CROSS_TARGET_WEIGHT = {"ST": 3.0, "AM": 1.5, "RW": 1.2, "LW": 1.2, "RM": 1.0, "LM": 1.0, "CM": 0.8}

Restart = Literal["kickoff", "throw_in", "goal_kick", "corner", "free_kick", "penalty", "keeper"]
Events = Generator[MatchEvent, None, None]


@dataclass(frozen=True, slots=True)
class MatchConfig:
    home: str
    away: str
    seed: int
    scenario: str = "default"
    match_id: str | None = None
    kickoff_epoch_ms: int = DEFAULT_KICKOFF_EPOCH_MS

    def resolved_match_id(self) -> str:
        if self.match_id:
            return self.match_id
        return f"{self.home}-{self.away}-{self.scenario}-s{self.seed}".lower()


@dataclass
class TeamModifiers:
    """Multipliers that scenario scripts can change mid-match. 1.0 is neutral."""

    attack: float = 1.0  # shot frequency and finishing
    press: float = 1.0  # pressing frequency and tackling
    fatigue: float = 1.0  # stamina drain rate
    composure: float = 1.0  # pass completion


@dataclass(eq=False)
class PlayerState:
    info: Player
    slot: Slot
    on_since_ms: int = 0
    yellow: bool = False

    @property
    def id(self) -> str:
        return self.info.player_id


@dataclass(eq=False)
class TeamState:
    club: Club
    lineup: list[PlayerState]
    bench: list[PlayerState]
    sub_times_ms: list[int]
    score: int = 0
    subs_left: int = 5
    mods: TeamModifiers = field(default_factory=TeamModifiers)
    _press: float | None = None

    @property
    def id(self) -> str:
        return self.club.team_id

    def press_rating(self) -> float:
        if self._press is None:
            outfield = [p.info.attributes.pressing for p in self.lineup if p.slot.role != "GK"]
            self._press = sum(outfield) / (100 * max(len(outfield), 1))
        return self._press

    def lineup_changed(self) -> None:
        self._press = None

    def keeper(self) -> PlayerState:
        return next(p for p in self.lineup if p.slot.role == "GK")


def _round(value: float, hi: float) -> float:
    return round(clamp(value, 0.0, hi), 2)


def expected_goal_probability(x: float, y: float) -> float:
    """Distance + angle logistic model, in the shooting team's frame."""
    dx, dy = PITCH_LENGTH - x, abs(y - CENTRE[1])
    dist = math.hypot(dx, dy)
    angle = math.atan2(2 * GOAL_HALF_WIDTH * dx, dx * dx + dy * dy - GOAL_HALF_WIDTH**2)
    if angle < 0:
        angle += math.pi
    return 1 / (1 + math.exp(-(-0.6 - 0.16 * dist + 1.0 * angle)))


def in_box(x: float, y: float) -> bool:
    return x >= BOX_X and BOX_Y[0] <= y <= BOX_Y[1]


class MatchEngine:
    """Generates one match as a lazy stream of MatchEvents in clock order."""

    def __init__(self, world: World, config: MatchConfig) -> None:
        if config.home == config.away:
            raise ValueError("home and away must be different clubs")
        self.config = config
        self.match_id = config.resolved_match_id()
        self.rng = random.Random(config.seed)
        self._ulids = UlidFactory(self.match_id)
        self.home = self._make_team(find_club(world, config.home))
        self.away = self._make_team(find_club(world, config.away))

        self.seq = 0
        self.period: Literal[1, 2] = 1
        self.clock = 0
        self._p1_end = HALF_MS
        # Possession state. Ball coordinates are in the possessing team's frame.
        self.team = self.home
        self.carrier = self.home.lineup[0]
        self.bx, self.by = CENTRE
        self.pressured = False
        self.restart: Restart | None = None
        self._header_chance = False

    # ------------------------------------------------------------------ setup

    def _make_team(self, club: Club) -> TeamState:
        slots = FORMATIONS[club.formation]
        by_id = {p.player_id: p for p in club.players}
        lineup = [
            PlayerState(by_id[pid], slot) for pid, slot in zip(club.starting_xi, slots, strict=True)
        ]
        starters = set(club.starting_xi)
        bench = [PlayerState(p, slots[0]) for p in club.players if p.player_id not in starters]
        n_subs = self.rng.choice((3, 4, 4, 5, 5))
        sub_times = sorted(self.rng.randint(56, 86) * 60_000 for _ in range(n_subs))
        return TeamState(club=club, lineup=lineup, bench=bench, sub_times_ms=sub_times)

    # --------------------------------------------------------------- top level

    def events(self) -> Iterator[MatchEvent]:
        first = self.rng.choice((self.home, self.away))
        yield from self._play_period(1, first)
        yield from self._play_period(2, self._other(first))

    def _play_period(self, period: Literal[1, 2], kicking: TeamState) -> Events:
        self.period = period
        start = 0 if period == 1 else HALF_MS
        stoppage_s = self.rng.randint(60, 180) if period == 1 else self.rng.randint(180, 360)
        end = start + HALF_MS + stoppage_s * 1000
        self.clock = start
        yield from self._kickoff(kicking)
        while self.clock < end:
            yield from self._step()
        ax, ay = self._ball_in_frame(self.home)
        yield self._emit("period_end", None, None, ax, ay)
        if period == 1:
            self._p1_end = self.clock

    # ---------------------------------------------------------------- helpers

    def _other(self, team: TeamState) -> TeamState:
        return self.away if team is self.home else self.home

    def _opp(self) -> TeamState:
        return self._other(self.team)

    def _ball_in_frame(self, team: TeamState) -> tuple[float, float]:
        return (self.bx, self.by) if team is self.team else flip(self.bx, self.by)

    def _wait(self, lo_ms: float, hi_ms: float) -> None:
        self.clock += int(self.rng.uniform(lo_ms, hi_ms))

    def _emit(
        self,
        etype: str,
        team: TeamState | None,
        player: PlayerState | None,
        x: float,
        y: float,
        *,
        end: tuple[float, float] | None = None,
        **extra: Any,
    ) -> MatchEvent:
        if self.period == 1:
            elapsed = self.clock
        else:
            elapsed = self._p1_end + HALFTIME_BREAK_MS + (self.clock - HALF_MS)
        fields: dict[str, Any] = {
            "event_id": self._ulids.new(self.config.kickoff_epoch_ms + elapsed),
            "match_id": self.match_id,
            "seq": self.seq,
            "clock_ms": self.clock,
            "period": self.period,
            "type": etype,
            "x": _round(x, PITCH_LENGTH),
            "y": _round(y, PITCH_WIDTH),
            "under_pressure": False,
        }
        if team is not None:
            fields["team_id"] = team.id
        if player is not None:
            fields["player_id"] = player.id
        if end is not None:
            fields["end_x"] = _round(end[0], PITCH_LENGTH)
            fields["end_y"] = _round(end[1], PITCH_WIDTH)
        if "ball_speed_kmh" in extra:
            extra["ball_speed_kmh"] = round(extra["ball_speed_kmh"], 1)
        fields.update(extra)
        self.seq += 1
        return MatchEvent(**fields)

    def _energy(self, team: TeamState, player: PlayerState) -> float:
        played_min = max(0, self.clock - player.on_since_ms) / 60_000
        stamina = player.info.attributes.stamina
        drain = (0.40 - 0.28 * (stamina - 50) / 49) * team.mods.fatigue
        drain *= 0.8 + 0.4 * team.press_rating()
        return clamp(1 - drain * played_min / 90, 0.3, 1.0)

    def _targets(
        self, team: TeamState, in_possession: bool
    ) -> list[tuple[PlayerState, float, float]]:
        """Formation targets for `team`, expressed in the possessing team's frame."""
        bx, by = self._ball_in_frame(team)
        out = []
        for p in team.lineup:
            tx, ty = target_position(p.slot, bx, by, in_possession)
            if team is not self.team:
                tx, ty = flip(tx, ty)
            out.append((p, tx, ty))
        return out

    def _nearest_opponent(self, x: float, y: float) -> PlayerState:
        targets = self._targets(self._opp(), in_possession=False)
        return min(targets, key=lambda t: math.hypot(t[1] - x, t[2] - y))[0]

    def _nearest_mate(self, x: float, y: float, exclude: PlayerState | None) -> PlayerState:
        targets = [t for t in self._targets(self.team, True) if t[0] is not exclude]
        return min(targets, key=lambda t: math.hypot(t[1] - x, t[2] - y))[0]

    def _turnover(self, new_team: TeamState, player: PlayerState, x: float, y: float) -> Events:
        """Hand the ball to `new_team` at (x, y) in its own frame."""
        self.team, self.carrier = new_team, player
        self.bx, self.by = x, y
        self.pressured = False
        self._header_chance = False
        yield self._emit("possession_change", new_team, player, x, y)

    # -------------------------------------------------------------- the chain

    def _kickoff(self, team: TeamState) -> Events:
        self.team = team
        self.bx, self.by = CENTRE
        self.carrier = max((p for p in team.lineup if p.slot.role != "GK"), key=lambda p: p.slot.x)
        self.pressured = False
        self._header_chance = False
        self.restart = "kickoff"
        yield self._emit("kickoff", team, self.carrier, *CENTRE)

    def _step(self) -> Events:
        restart, self.restart = self.restart, None
        if restart not in (None, "keeper", "penalty"):
            yield from self._substitutions()

        if restart == "penalty":
            self.carrier = max(self.team.lineup, key=lambda p: p.info.attributes.finishing)
            self._wait(800, 1500)
            yield from self._shot(penalty=True)
            return
        if self._header_chance:
            if self.rng.random() < 0.7:
                self._wait(150, 400)
                yield from self._shot()
                return
            self._header_chance = False  # cushioned down instead of a first-time header

        self._wait(650, 1300 if self.pressured else 2000)
        if restart is None:
            stopped = yield from self._defend()
            if stopped:
                return

        if restart == "corner":
            yield from self._pass(restart, cross=True)
        elif restart in ("kickoff", "throw_in", "goal_kick", "keeper"):
            yield from self._pass(restart)
        elif restart == "free_kick":
            dist = math.hypot(PITCH_LENGTH - self.bx, CENTRE[1] - self.by)
            if dist < 30 and abs(self.by - CENTRE[1]) < 16 and self.rng.random() < 0.35:
                yield from self._shot(free_kick=True)
            elif self.bx > 72 and self.rng.random() < 0.6:
                yield from self._pass(restart, cross=True)
            else:
                yield from self._pass(restart)
        else:
            yield from self._open_play_action()

    def _open_play_action(self) -> Events:
        x, y = self.bx, self.by
        p_shot = self._shot_probability(x, y)
        p_carry = 0.11 if self.pressured else 0.22
        if x > 95:
            p_carry *= 0.3
        wide = y < 16 or y > 52
        r = self.rng.random()
        if r < p_shot:
            yield from self._shot()
        elif r < p_shot + p_carry:
            yield from self._carry()
        elif x > 76 and wide and self.rng.random() < 0.45:
            yield from self._pass(None, cross=True)
        else:
            yield from self._pass(None)

    def _shot_probability(self, x: float, y: float) -> float:
        dist = math.hypot(PITCH_LENGTH - x, CENTRE[1] - y)
        if in_box(x, y):
            p = 0.27 * math.exp(-(dist - 6) / 8)
        elif dist < 30:
            p = 0.065
        else:
            return 0.0
        return min(0.9, p * self.team.mods.attack)

    def _defend(self) -> Generator[MatchEvent, None, bool]:
        """Opponent pressure, tackles and fouls. Returns True if the chain stopped."""
        opp = self._opp()
        presser = self._nearest_opponent(self.bx, self.by)
        energy = self._energy(opp, presser)
        p_press = 0.30 * (opp.press_rating() / 0.72) * (0.6 + 0.4 * energy) * opp.mods.press
        if self.bx > 70:
            p_press *= 1.25
        if self.rng.random() >= p_press:
            self.pressured = False
            return False

        self.pressured = True
        fx, fy = flip(self.bx, self.by)
        yield self._emit("pressure", opp, presser, fx, fy)
        box_factor = 0.35 if in_box(self.bx, self.by) else 1.0

        if self.rng.random() < 0.04 * box_factor:
            self._wait(200, 600)
            yield from self._foul(opp, presser)
            return True
        if self.rng.random() >= 0.13 * opp.mods.press:
            return False

        self._wait(200, 600)
        if self.rng.random() < 0.2 * box_factor:
            yield from self._foul(opp, presser)
            return True
        attrs, carrier_attrs = presser.info.attributes, self.carrier.info.attributes
        p_win = clamp(0.5 + (attrs.pressing - carrier_attrs.pace) / 250, 0.25, 0.75)
        if self.rng.random() < p_win * (0.7 + 0.3 * energy):
            yield self._emit("tackle", opp, presser, fx, fy, outcome="won")
            self._wait(300, 900)
            yield from self._turnover(opp, presser, fx, fy)
            return True
        yield self._emit("tackle", opp, presser, fx, fy, outcome="lost")
        self.pressured = False
        return False

    def _foul(self, fouling: TeamState, fouler: PlayerState) -> Events:
        fx, fy = flip(self.bx, self.by)
        yield self._emit("foul", fouling, fouler, fx, fy)
        r = self.rng.random()
        p_yellow = 0.14 + (0.04 if self.clock > 70 * 60_000 else 0.0)
        if fouler.yellow:
            p_yellow *= 0.4  # booked players hold back
        card: str | None = None
        if r < 0.006:
            card = "red"
        elif r < 0.006 + p_yellow:
            card = "second_yellow" if fouler.yellow else "yellow"
        dead_extra = 0
        if card is not None:
            self._wait(800, 2000)
            yield self._emit("card", fouling, fouler, fx, fy, card_color=card)
            fouler.yellow = True
            if card != "yellow":
                yield from self._send_off(fouling, fouler)
            dead_extra = 15_000
        self.pressured = False
        if in_box(self.bx, self.by):
            self.restart = "penalty"
            self._wait(45_000 + dead_extra, 75_000 + dead_extra)
        else:
            self.restart = "free_kick"
            self._wait(12_000 + dead_extra, 28_000 + dead_extra)

    def _send_off(self, team: TeamState, player: PlayerState) -> Events:
        team.lineup.remove(player)
        team.lineup_changed()
        if player.slot.role != "GK":
            return
        backup = next(
            (p for p in team.bench if p.slot.role == "GK" or p.info.position == "GK"), None
        )
        outfield = [p for p in team.lineup if p.slot.role != "GK"]
        if backup is not None and team.subs_left > 0 and outfield:
            off = min(outfield, key=lambda p: self._energy(team, p))
            yield from self._swap(team, off, backup, slot=player.slot)
        else:
            # An outfield player goes in goal.
            stand_in = max(outfield, key=lambda p: p.info.attributes.pace)
            stand_in.slot = player.slot

    def _swap(
        self, team: TeamState, off: PlayerState, on: PlayerState, slot: Slot | None = None
    ) -> Events:
        on.slot = slot or off.slot
        on.on_since_ms = self.clock
        team.lineup[team.lineup.index(off)] = on
        team.lineup_changed()
        team.bench.remove(on)
        team.subs_left -= 1
        if self.carrier is off:
            self.carrier = on
        ox, oy = (CENTRE[0], 0.0)
        yield self._emit("substitution", team, off, ox, oy, recipient_id=on.id)
        self._wait(10_000, 20_000)

    def _substitutions(self) -> Events:
        if self.period != 2:
            return
        for team in (self.team, self._opp()):
            made = 0
            while (
                team.sub_times_ms
                and self.clock >= team.sub_times_ms[0]
                and team.subs_left > 0
                and made < 2
            ):
                team.sub_times_ms.pop(0)
                outfield = [p for p in team.lineup if p.slot.role != "GK"]
                candidates = [p for p in team.bench if p.info.position != "GK"]
                if not outfield or not candidates:
                    break
                off = min(outfield, key=lambda p: self._energy(team, p) - 0.1 * p.yellow)
                group = ROLE_GROUP[off.slot.role]
                same = [p for p in candidates if ROLE_GROUP[p.info.position] == group]
                on = (same or candidates)[0]
                yield from self._swap(team, off, on)
                made += 1

    # ------------------------------------------------------------- on-ball

    def _carry(self) -> Events:
        pace = self.carrier.info.attributes.pace
        dist = self.rng.uniform(3, 11) * (1.25 if pace > 82 else 1.0)
        angle = self.rng.gauss(0, 0.5)
        # Drift back inside when hugging a touchline.
        angle += 0.4 * (CENTRE[1] - self.by) / CENTRE[1]
        ex = clamp(self.bx + dist * math.cos(angle), 0.5, 103.0)
        ey = clamp(self.by + dist * math.sin(angle), 0.5, PITCH_WIDTH - 0.5)
        yield self._emit(
            "carry", self.team, self.carrier, self.bx, self.by,
            end=(ex, ey), under_pressure=self.pressured,
        )  # fmt: skip
        travelled = math.hypot(ex - self.bx, ey - self.by)
        self.clock += int(1000 * travelled / carry_speed_ms(pace))
        self.bx, self.by = ex, ey
        self.pressured = False

    def _choose_recipient(
        self, restart: Restart | None, cross: bool
    ) -> tuple[PlayerState, float, float]:
        x, y = self.bx, self.by
        mates = [t for t in self._targets(self.team, True) if t[0] is not self.carrier]
        if cross:
            weights = [CROSS_TARGET_WEIGHT.get(p.slot.role, 0.0) for p, _, _ in mates]
            if restart == "corner":
                weights = [w + (0.8 if p.slot.role == "CB" else 0.0)
                           for w, (p, _, _) in zip(weights, mates, strict=True)]  # fmt: skip
            if sum(weights) <= 0:
                weights = [0.0 if p.slot.role == "GK" else 1.0 for p, _, _ in mates]
            player = self.rng.choices([m[0] for m in mates], weights=weights)[0]
            return player, self.rng.uniform(91, 100), self.rng.uniform(26, 42)

        long_ball = (restart == "goal_kick" and self.rng.random() < 0.5) or (
            self.carrier.slot.role in ("GK", "CB") and self.rng.random() < 0.12
        )
        weights = []
        for p, tx, ty in mates:
            dx = tx - x
            d = math.hypot(dx, ty - y)
            if d < 4:
                weights.append(0.0)
                continue
            if long_ball:
                w = 1.0 if dx > 25 else 0.02
            elif restart == "throw_in":
                w = math.exp(-(((d - 12) / 7) ** 2))
            elif restart == "kickoff":
                w = 1.0 if p.slot.role in ("CM", "DM", "AM") else 0.05
            else:
                w = math.exp(-(((d - 16) / 13) ** 2))
                w *= 1 + 0.045 * max(dx, 0.0)
                if dx < -8:
                    w *= 0.55
            if p.slot.role == "GK":
                w *= 0.25 if x < 40 and restart is None else 0.0
            weights.append(w)
        if sum(weights) <= 0:
            weights = [1.0 if m[0].slot.role != "GK" else 0.0 for m in mates]
        player, tx, ty = self.rng.choices(mates, weights=weights)[0]
        spread = 3.5 if long_ball else 2.2
        return player, tx + self.rng.gauss(0, spread), ty + self.rng.gauss(0, spread)

    def _pass(self, restart: Restart | None, cross: bool = False) -> Events:
        team, passer = self.team, self.carrier
        sx, sy = self.bx, self.by
        recipient, ex, ey = self._choose_recipient(restart, cross)
        ex, ey = clamp(ex, 0.5, PITCH_LENGTH - 0.5), clamp(ey, 0.5, PITCH_WIDTH - 0.5)
        dist = math.hypot(ex - sx, ey - sy)
        if restart == "throw_in":
            speed = self.rng.uniform(25, 45)
        else:
            speed = clamp(26 + 1.2 * dist + self.rng.gauss(0, 5), 12, 110)

        attrs = passer.info.attributes
        line_break = ex - sx > 15 and ex > 40
        if cross:
            p = 0.22 + 0.004 * (attrs.passing - 72)
        else:
            p = 0.94 - 0.0045 * max(0.0, dist - 12)
            p -= 0.10 * self.pressured + 0.06 * line_break + (0.07 if ex > 80 else 0.0)
            if in_box(ex, ey):
                p -= 0.18
            p += 0.004 * (attrs.passing - 72)
            if restart is not None:
                p += 0.05
        p -= 0.12 * (1 - self._energy(team, passer))
        p = clamp(p * team.mods.composure, 0.12, 0.98)
        flight = flight_ms(dist, speed, PASS_DRAG)
        common: dict[str, Any] = {
            "ball_speed_kmh": speed,
            "recipient_id": recipient.id,
            "under_pressure": self.pressured,
        }

        if self.rng.random() < p:
            yield self._emit(
                "pass", team, passer, sx, sy, end=(ex, ey), outcome="complete", **common
            )
            self.clock += int(flight)
            self.carrier, self.bx, self.by = recipient, ex, ey
            self.pressured = False
            self._header_chance = cross
            return

        opp = self._opp()
        r = self.rng.random()
        if r < 0.22:
            yield from self._pass_out_of_play(passer, sx, sy, ex, ey, speed, common)
        elif r < 0.55:
            u = self.rng.uniform(0.35, 0.95)
            ix, iy = sx + u * (ex - sx), sy + u * (ey - sy)
            interceptor = self._nearest_opponent(ix, iy)
            yield self._emit(
                "pass", team, passer, sx, sy, end=(ix, iy), outcome="incomplete", **common
            )
            self.clock += int(flight * u)
            fx, fy = flip(ix, iy)
            yield self._emit("interception", opp, interceptor, fx, fy, outcome="won")
            self._wait(200, 600)
            yield from self._turnover(opp, interceptor, fx, fy)
        else:
            yield self._emit(
                "pass", team, passer, sx, sy, end=(ex, ey), outcome="incomplete", **common
            )
            self.clock += int(flight)
            self._wait(300, 1200)
            if self.rng.random() < 0.8:
                winner = self._nearest_opponent(ex, ey)
                yield from self._turnover(opp, winner, *flip(ex, ey))
            else:
                self.carrier = self._nearest_mate(ex, ey, exclude=None)
                self.bx, self.by = ex, ey
                self.pressured = False

    def _pass_out_of_play(
        self,
        passer: PlayerState,
        sx: float,
        sy: float,
        ex: float,
        ey: float,
        speed: float,
        common: dict[str, Any],
    ) -> Events:
        team, opp = self.team, self._opp()
        if ex > 92 and self.rng.random() < 0.55:
            ox, oy = PITCH_LENGTH, ey
        else:
            ox = clamp(ex + self.rng.gauss(0, 3), 1.0, PITCH_LENGTH - 1.0)
            oy = 0.0 if ey < CENTRE[1] else PITCH_WIDTH
        yield self._emit("pass", team, passer, sx, sy, end=(ox, oy), outcome="incomplete", **common)
        self.clock += int(flight_ms(math.hypot(ox - sx, oy - sy), speed, PASS_DRAG))

        if ox < PITCH_LENGTH:
            yield self._emit("out_of_play", team, passer, ox, oy)
            fx, fy = flip(ox, oy)
            thrower = self._nearest_opponent(ox, oy)
            yield from self._turnover(opp, thrower, fx, fy)
            self.restart = "throw_in"
            self._wait(10_000, 20_000)
        elif self.rng.random() < 0.5:
            # Attacker's ball over the line: goal kick.
            yield self._emit("out_of_play", team, passer, ox, oy)
            yield from self._goal_kick(opp)
        else:
            # Deflected out by a defender: corner.
            defender = self._nearest_opponent(ox, oy)
            yield self._emit("out_of_play", opp, defender, *flip(ox, oy))
            self._corner(oy)

    def _goal_kick(self, team: TeamState) -> Events:
        keeper = team.keeper()
        yield from self._turnover(team, keeper, 5.5, CENTRE[1] + self.rng.choice((-9.0, 9.0)))
        self.restart = "goal_kick"
        self._wait(14_000, 26_000)

    def _corner(self, side_y: float) -> None:
        """Corner for the team in possession, on the side nearest side_y."""
        cy = 0.5 if side_y < CENTRE[1] else PITCH_WIDTH - 0.5
        creative = [p for p in self.team.lineup if ROLE_GROUP[p.slot.role] in ("MID", "FWD")]
        self.carrier = max(creative or self.team.lineup, key=lambda p: p.info.attributes.passing)
        self.bx, self.by = PITCH_LENGTH - 0.5, cy
        self.pressured = False
        self._header_chance = False
        self.restart = "corner"
        self._wait(18_000, 32_000)

    def _shot(self, penalty: bool = False, free_kick: bool = False) -> Events:
        team, opp, shooter = self.team, self._opp(), self.carrier
        header = self._header_chance and self.rng.random() < 0.65
        self._header_chance = False
        if penalty:
            self.bx, self.by = PENALTY_SPOT
        x, y = self.bx, self.by
        dist = math.hypot(PITCH_LENGTH - x, CENTRE[1] - y)
        finishing = shooter.info.attributes.finishing

        if penalty:
            p_goal = 0.72 + (finishing - 70) / 300
        else:
            p_goal = expected_goal_probability(x, y) * (1 + (finishing - 70) / 80)
            p_goal *= team.mods.attack
            if self.pressured:
                p_goal *= 0.75
            if header:
                p_goal *= 0.5
            if free_kick:
                p_goal *= 0.6
        p_goal = clamp(p_goal, 0.01, 0.95)

        if header:
            body = "head"
            speed = self.rng.uniform(30, 60)
        else:
            body = "left_foot" if self.rng.random() < 0.3 else "right_foot"
            speed = clamp(68 + 1.0 * dist + self.rng.gauss(0, 10), 40, 130)

        r = self.rng.random()
        if r < p_goal:
            outcome = "complete"
            end = (PITCH_LENGTH, CENTRE[1] + self.rng.uniform(-3.4, 3.4))
        else:
            q = self.rng.random()
            if q < 0.28 and not (penalty or free_kick):
                outcome = "blocked"
                step = self.rng.uniform(1.0, 4.0) / max(dist, 1.0)
                end = (x + (PITCH_LENGTH - x) * step, y + (CENTRE[1] - y) * step)
            elif q < 0.62:
                outcome = "saved"
                end = (PITCH_LENGTH - 0.5, CENTRE[1] + self.rng.uniform(-3.3, 3.3))
            else:
                outcome = "off_target"
                miss = self.rng.uniform(4.2, 11.0) * self.rng.choice((-1, 1))
                # A third of misses go over the bar, which this 2D model shows inside the posts.
                if self.rng.random() < 0.33:
                    miss = self.rng.uniform(-3.4, 3.4)
                end = (PITCH_LENGTH, CENTRE[1] + miss)

        yield self._emit(
            "shot", team, shooter, x, y, end=end, outcome=outcome,
            ball_speed_kmh=speed, body_part=body, under_pressure=self.pressured,
        )  # fmt: skip
        self.clock += int(flight_ms(math.hypot(end[0] - x, end[1] - y), speed, SHOT_DRAG))
        self.pressured = False

        if outcome == "complete":
            yield self._emit("goal", team, shooter, x, y, end=end, body_part=body)
            team.score += 1
            self._wait(45_000, 75_000)
            yield from self._kickoff(opp)
        elif outcome == "saved":
            keeper = opp.keeper()
            if self.rng.random() < 0.65:
                self._wait(1_000, 3_000)
                yield from self._turnover(opp, keeper, 4.5, CENTRE[1] + self.rng.gauss(0, 3))
                self.restart = "keeper"
                self._wait(3_000, 8_000)
            else:
                yield self._emit("out_of_play", opp, keeper, *flip(PITCH_LENGTH, end[1]))
                self._corner(end[1] + self.rng.choice((-20.0, 20.0)))
        elif outcome == "blocked":
            blocker = self._nearest_opponent(*end)
            r = self.rng.random()
            if r < 0.35:
                yield self._emit("out_of_play", opp, blocker, *flip(PITCH_LENGTH, end[1]))
                self._corner(end[1])
            elif r < 0.7:
                self._wait(300, 900)
                yield from self._turnover(opp, blocker, *flip(*end))
            else:
                self._wait(300, 900)
                self.carrier = self._nearest_mate(*end, exclude=shooter)
                self.bx, self.by = end
        else:
            yield self._emit("out_of_play", team, shooter, *end)
            yield from self._goal_kick(opp)
