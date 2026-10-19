"""5 Hz tracking frames derived from a match event stream.

Works from events alone (plus the world file), so it can rebuild tracking for any
exported match. The ball follows piecewise-linear keyframes taken from event
locations and flight times. Players steer towards their formation target, with
speed and acceleration limits from their ratings, a little smooth wander, and an
urgent run to the ball when they are the actor of the next event.

Output coordinates are absolute: the home team attacks towards x=105 all match.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal

from contracts import BallPosition, MatchEvent, PlayerPosition, TrackingFrame, World
from sim.formation import (
    CENTRE,
    FORMATIONS,
    PITCH_LENGTH,
    PITCH_WIDTH,
    Slot,
    flip,
    kickoff_position,
    target_position,
)
from sim.physics import PASS_DRAG, SHOT_DRAG, carry_speed_ms, flight_ms, top_speed_ms
from sim.world import club as find_club
from sim.world import players_by_id

FRAME_MS = 200
DT = FRAME_MS / 1000
ACCEL = 4.5  # m/s^2
GAIN_SHAPE = 0.8  # 1/s: relaxed drift towards a formation target
GAIN_URGENT = 2.5  # 1/s: running to the ball or the next event's location
SHAPE_SPEED_SHARE = 0.8  # players do not sprint just to hold shape
LOOKAHEAD_MS = 2500
NOISE_SIGMA = 1.5  # m: stationary spread of each player's wander
NOISE_THETA = 0.25  # 1/s
# Uniform increments on [-1, 1] have variance 1/3, so scale by sqrt(3) to match sigma.
NOISE_STEP = NOISE_SIGMA * math.sqrt(2 * NOISE_THETA * DT) * math.sqrt(3)
VMAX_REFRESH_MS = 1000

# Events whose x, y is where the ball is at that moment.
BALL_ANCHORED = {
    "pass",
    "carry",
    "shot",
    "tackle",
    "interception",
    "pressure",
    "foul",
    "card",
    "possession_change",
    "out_of_play",
    "kickoff",
    "period_end",
}
FLIGHT_EVENTS = {"pass", "carry", "shot"}

StreamItem = MatchEvent | TrackingFrame


@dataclass(eq=False)
class Body:
    player_id: str
    home: bool
    slot: Slot
    pace: int
    stamina: int
    on_since_ms: int = 0
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    nx: float = 0.0  # wander offset
    ny: float = 0.0
    vmax: float = 0.0
    vmax_at: int = -VMAX_REFRESH_MS


class TrackingGenerator:
    def __init__(self, world: World, match_id: str, home: str, away: str, seed: int) -> None:
        self.match_id = match_id
        self.home_id = home
        self.rng = random.Random(f"tracking:{seed}")
        self._players = players_by_id(world)
        self.bodies: dict[str, Body] = {}
        for team_id, is_home in ((home, True), (away, False)):
            club = find_club(world, team_id)
            for pid, slot in zip(club.starting_xi, FORMATIONS[club.formation], strict=True):
                self.bodies[pid] = self._body(pid, is_home, slot)

        self.period: Literal[1, 2] = 1
        self.live = False
        self.next_t = 0
        self.poss_home = True
        self.carrier: str | None = None
        self.celebrating = False
        self.keyframes: list[tuple[int, float, float]] = [(0, *CENTRE)]
        self._keeper_lost: set[bool] = set()

    def _body(self, player_id: str, home: bool, slot: Slot) -> Body:
        attrs = self._players[player_id].attributes
        return Body(player_id, home, slot, attrs.pace, attrs.stamina)

    # -------------------------------------------------------------- public

    def stream(self, events: Iterable[MatchEvent]) -> Iterator[StreamItem]:
        """Interleave events with tracking frames, in match-clock order."""
        it = iter(events)
        current = next(it, None)
        if current is None:
            return
        self._apply(current)
        yield current
        for upcoming in it:
            if self.live and upcoming.period == self.period:
                yield from self._frames_until(upcoming)
            self._apply(upcoming)
            yield upcoming

    # ------------------------------------------------------------- helpers

    def _abs(self, event: MatchEvent, x: float, y: float) -> tuple[float, float]:
        """Event coordinates (acting team's frame) to absolute (home's frame)."""
        if event.team_id is None or event.team_id == self.home_id:
            return x, y
        return flip(x, y)

    def _ball_at(self, t: float, upcoming: tuple[int, float, float] | None) -> tuple[float, float]:
        frames = self.keyframes + ([upcoming] if upcoming else [])
        prev = frames[0]
        for kf in frames[1:]:
            if t <= kf[0]:
                span = kf[0] - prev[0]
                u = 1.0 if span <= 0 else max(0.0, (t - prev[0]) / span)
                return prev[1] + u * (kf[1] - prev[1]), prev[2] + u * (kf[2] - prev[2])
            prev = kf
        return prev[1], prev[2]

    def _energy(self, body: Body, t: int) -> float:
        played_min = max(0, t - body.on_since_ms) / 60_000
        drain = 0.40 - 0.28 * (body.stamina - 50) / 49
        return max(0.3, 1 - drain * played_min / 90)

    def _reset_to_kickoff(self) -> None:
        for body in self.bodies.values():
            kx, ky = kickoff_position(body.slot)
            body.x, body.y = (kx, ky) if body.home else flip(kx, ky)
            body.vx = body.vy = body.nx = body.ny = 0.0

    def _keeper_check(self) -> None:
        """A side whose keeper was sent off with no replacement puts an outfielder in goal.

        Runs before the next frame rather than on the card, because a substitute keeper
        may come on at the same clock tick.
        """
        for home in self._keeper_lost:
            side = [b for b in self.bodies.values() if b.home == home]
            if side and not any(b.slot.role == "GK" for b in side):
                stand_in = max(side, key=lambda b: b.pace)
                stand_in.slot = FORMATIONS["4-3-3"][0]
        self._keeper_lost.clear()

    # ---------------------------------------------------------- event state

    def _apply(self, event: MatchEvent) -> None:
        etype = event.type
        if etype == "kickoff":
            if event.period != self.period or not self.live:
                self.period = event.period
                self.next_t = event.clock_ms
                self.keyframes = []
                self._reset_to_kickoff()
                kicker = self.bodies.get(event.player_id or "")
                if kicker is not None:
                    kicker.x, kicker.y = CENTRE
            self.live = True
            self.celebrating = False
        elif etype == "period_end":
            self.live = False
        elif etype == "goal":
            self.celebrating = True
        elif etype == "substitution" and event.player_id and event.recipient_id:
            off = self.bodies.pop(event.player_id)
            info = self._players[event.recipient_id]
            slot = FORMATIONS["4-3-3"][0] if info.position == "GK" else off.slot
            on = self._body(event.recipient_id, off.home, slot)
            on.on_since_ms = event.clock_ms
            on.x, on.y = CENTRE[0], 0.0
            self.bodies[on.player_id] = on
        elif etype == "card" and event.card_color in ("red", "second_yellow") and event.player_id:
            gone = self.bodies.pop(event.player_id, None)
            if gone is not None and gone.slot.role == "GK":
                self._keeper_lost.add(gone.home)

        if event.team_id is not None and etype in ("kickoff", "possession_change", "pass", "carry"):
            self.poss_home = event.team_id == self.home_id
        if etype in ("kickoff", "possession_change", "carry"):
            self.carrier = event.player_id
        elif etype == "pass":
            self.carrier = event.recipient_id if event.outcome == "complete" else None
        elif etype in ("shot", "out_of_play"):
            self.carrier = None

        if etype in BALL_ANCHORED:
            ax, ay = self._abs(event, event.x, event.y)
            self.keyframes = [*self.keyframes[-1:], (event.clock_ms, ax, ay)]
            if etype in FLIGHT_EVENTS and event.end_x is not None and event.end_y is not None:
                ex, ey = self._abs(event, event.end_x, event.end_y)
                dist = math.hypot(ex - ax, ey - ay)
                if etype == "carry":
                    pace = self._players[event.player_id or ""].attributes.pace
                    duration = 1000 * dist / carry_speed_ms(pace)
                else:
                    drag = SHOT_DRAG if etype == "shot" else PASS_DRAG
                    duration = flight_ms(dist, event.ball_speed_kmh or 50.0, drag)
                self.keyframes.append((event.clock_ms + int(duration), ex, ey))

    # -------------------------------------------------------------- frames

    def _frames_until(self, upcoming: MatchEvent) -> Iterator[TrackingFrame]:
        anchor = None
        if upcoming.type in BALL_ANCHORED:
            anchor = (upcoming.clock_ms, *self._abs(upcoming, upcoming.x, upcoming.y))
        actor = upcoming.player_id if upcoming.type in BALL_ANCHORED else None
        if self._keeper_lost:
            self._keeper_check()
        while self.next_t < upcoming.clock_ms:
            t = self.next_t
            bx, by = self._ball_at(t, anchor)
            chase = None
            if actor is not None and anchor is not None and upcoming.clock_ms - t <= LOOKAHEAD_MS:
                chase = (actor, anchor[1], anchor[2])
            self._move_players(t, bx, by, chase)
            yield self._frame(t, bx, by)
            self.next_t += FRAME_MS

    def _move_players(
        self, t: int, bx: float, by: float, chase: tuple[str, float, float] | None
    ) -> None:
        rand = self.rng.random
        # The carrier (or a pass recipient) heads for where the ball will be, not where it is.
        _, dest_x, dest_y = self.keyframes[-1]
        for body in self.bodies.values():
            if t - body.vmax_at >= VMAX_REFRESH_MS:
                body.vmax = top_speed_ms(body.pace) * (0.85 + 0.15 * self._energy(body, t))
                body.vmax_at = t
            urgent = True
            if chase is not None and body.player_id == chase[0]:
                tx, ty = chase[1], chase[2]
            elif body.player_id == self.carrier and not self.celebrating:
                tx, ty = dest_x, dest_y
            else:
                urgent = False
                if self.celebrating:
                    tx, ty = kickoff_position(body.slot)
                else:
                    in_poss = body.home == self.poss_home
                    fx, fy = (bx, by) if body.home else flip(bx, by)
                    tx, ty = target_position(body.slot, fx, fy, in_poss)
                body.nx += -NOISE_THETA * body.nx * DT + NOISE_STEP * (2 * rand() - 1)
                body.ny += -NOISE_THETA * body.ny * DT + NOISE_STEP * (2 * rand() - 1)
                tx, ty = tx + body.nx, ty + body.ny
                if not body.home:
                    tx, ty = flip(tx, ty)

            vmax = body.vmax
            gain = GAIN_URGENT
            if not urgent:
                vmax *= SHAPE_SPEED_SHARE
                gain = GAIN_SHAPE
            dvx, dvy = (tx - body.x) * gain, (ty - body.y) * gain
            speed = math.hypot(dvx, dvy)
            if speed > vmax:
                dvx, dvy = dvx * vmax / speed, dvy * vmax / speed
            ax, ay = dvx - body.vx, dvy - body.vy
            accel = math.hypot(ax, ay)
            if accel > ACCEL * DT:
                ax, ay = ax * ACCEL * DT / accel, ay * ACCEL * DT / accel
            body.vx += ax
            body.vy += ay
            x, y = body.x + body.vx * DT, body.y + body.vy * DT
            body.x = 0.0 if x < 0.0 else PITCH_LENGTH if x > PITCH_LENGTH else x
            body.y = 0.0 if y < 0.0 else PITCH_WIDTH if y > PITCH_WIDTH else y

    def _frame(self, t: int, bx: float, by: float) -> TrackingFrame:
        # Built without validation for speed (~29k frames per match); tests validate
        # every frame against schemas/tracking.schema.json.
        construct = PlayerPosition.model_construct
        return TrackingFrame.model_construct(
            match_id=self.match_id,
            clock_ms=t,
            period=self.period,
            players=[
                construct(player_id=b.player_id, x=round(b.x, 2), y=round(b.y, 2))
                for b in self.bodies.values()
            ],
            ball=BallPosition.model_construct(x=round(bx, 2), y=round(by, 2)),
        )
