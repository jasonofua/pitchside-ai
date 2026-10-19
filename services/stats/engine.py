"""Rolling match statistics from the event and tracking streams.

The StatsEngine is the only place numbers are computed. It ingests MatchEvents and
TrackingFrames for one match, keeps match-level totals incrementally, answers windowed
queries by replaying its event records, computes the Control vs Chaos index every 30 s
of match time, and raises Triggers.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from contracts import (
    Club,
    MatchEvent,
    MatchInfo,
    Player,
    TrackingFrame,
    Trigger,
    World,
)
from contracts.stats import (
    AnalystReport,
    CardItem,
    DifficultyHistogram,
    GoalItem,
    Heatmap,
    MatchState,
    Momentum,
    MomentumComponents,
    MomentumNow,
    MomentumPoint,
    NetworkEdge,
    NetworkNode,
    PassNetwork,
    PeriodComparison,
    PlayerLine,
    PlayerStats,
    ShotMapItem,
    StatsSnapshot,
    TeamLine,
    TeamStats,
    TeamStatsReport,
)
from stats import metrics as m

Window = Literal["match", "first_half", "second_half", "last_5", "last_10", "last_15"]
WINDOWS: tuple[Window, ...] = ("match", "first_half", "second_half", "last_5", "last_10", "last_15")
Status = Literal["scheduled", "live", "half_time", "full_time", "aborted"]

SPEED_TRIGGER_KMH = 32.0
SPEED_REARM_KMH = 26.0
SPEED_COOLDOWN_MS = 5 * 60_000  # per player
PASS_DIFFICULTY_TRIGGER = 80.0
XG_TRIGGER = 0.3
MOMENTUM_SWING_TRIGGER = 30.0
MOMENTUM_SWING_COOLDOWN_MS = 180_000
TICK_MS = 30_000
MOMENTUM_WINDOW_MS = 5 * 60_000
MAX_LIVE_GAP_MS = 8_000  # cap on ball-in-play time credited between two events
BUCKET_MS = 10_000
HEAT_COLS, HEAT_ROWS = 12, 8
FRAME_MS = 200
NETWORK_MIN_PASSES = 3

ON_BALL = frozenset({"pass", "carry", "shot"})
STOPS_PLAY = frozenset({"out_of_play", "foul", "goal", "period_end"})
STARTS_PLAY = frozenset({"kickoff", "pass", "carry", "shot", "pressure", "tackle", "interception"})


@dataclass(slots=True)
class EventRecord:
    """An event plus everything the Stats Engine derived from it."""

    ev: MatchEvent
    t: int  # playing time since kickoff, ms
    poss_team: str | None  # team in possession after this event
    live: bool  # ball in play after this event
    poss_seq: int  # possession sequence number
    poss_ms: int = 0  # ball-in-play time credited to poss_team until the next event
    xg: float | None = None
    difficulty: float | None = None
    distance_m: float | None = None
    forward_m: float = 0.0
    turnover_by: str | None = None  # team that lost the ball (possession_change only)
    assist_from: str | None = None  # shots: the player whose pass set it up
    corner: bool = False
    penalty: bool = False


@dataclass(slots=True)
class TeamCounters:
    goals: int = 0
    shots: int = 0
    on_target: int = 0
    xg: float = 0.0
    max_shot_speed: float | None = None
    passes: int = 0
    completed: int = 0
    pass_distance: float = 0.0
    pass_speed: float = 0.0
    difficulty: float = 0.0
    difficult_completed: int = 0
    poss_ms: int = 0
    pressures: int = 0
    tackles: int = 0
    tackles_won: int = 0
    interceptions: int = 0
    fouls: int = 0
    yellows: int = 0
    reds: int = 0
    corners: int = 0
    turnovers: int = 0
    ppda_passes: int = 0
    ppda_actions: int = 0


@dataclass(slots=True)
class PlayerCounters:
    touches: int = 0
    passes: int = 0
    completed: int = 0
    difficulty: float = 0.0
    max_difficulty: float | None = None
    key_passes: int = 0
    shots: int = 0
    on_target: int = 0
    goals: int = 0
    xg: float = 0.0
    max_shot_speed: float | None = None
    pressures: int = 0
    tackles_won: int = 0
    interceptions: int = 0
    fouls: int = 0
    yellows: int = 0
    reds: int = 0


def _max(a: float | None, b: float) -> float:
    return b if a is None or b > a else a


class Accumulator:
    """Event-derived counters for both teams and every player.

    The match-level accumulator is fed incrementally; windowed queries build a fresh one
    from the records in the window, so both paths share this code.
    """

    def __init__(self, team_ids: Iterable[str]) -> None:
        self.teams = {t: TeamCounters() for t in team_ids}
        self.players: dict[str, PlayerCounters] = {}

    def _p(self, player_id: str) -> PlayerCounters:
        pc = self.players.get(player_id)
        if pc is None:
            pc = self.players[player_id] = PlayerCounters()
        return pc

    def _other(self, team_id: str) -> str:
        return next(t for t in self.teams if t != team_id)

    def add_possession(self, team_id: str | None, ms: int) -> None:
        if team_id is not None and ms > 0:
            self.teams[team_id].poss_ms += ms

    def add(self, rec: EventRecord) -> None:
        ev = rec.ev
        if ev.team_id is None or ev.player_id is None:
            return
        tc, pc = self.teams[ev.team_id], self._p(ev.player_id)
        kind = ev.type
        self.add_possession(rec.poss_team, rec.poss_ms)

        if kind == "pass":
            tc.passes += 1
            pc.passes += 1
            pc.touches += 1
            tc.pass_distance += rec.distance_m or 0.0
            tc.pass_speed += ev.ball_speed_kmh or 0.0
            diff = rec.difficulty or 0.0
            tc.difficulty += diff
            pc.difficulty += diff
            pc.max_difficulty = _max(pc.max_difficulty, diff)
            if rec.corner:
                tc.corners += 1
            if ev.outcome == "complete":
                tc.completed += 1
                pc.completed += 1
                if diff > PASS_DIFFICULTY_TRIGGER:
                    tc.difficult_completed += 1
                if ev.recipient_id:
                    self._p(ev.recipient_id).touches += 1
            if ev.x <= m.PITCH_LENGTH - m.PPDA_ZONE_X:
                self.teams[self._other(ev.team_id)].ppda_passes += 1
        elif kind == "carry":
            pc.touches += 1
        elif kind == "shot":
            tc.shots += 1
            pc.shots += 1
            pc.touches += 1
            shot_xg = rec.xg or 0.0
            tc.xg += shot_xg
            pc.xg += shot_xg
            speed = ev.ball_speed_kmh or 0.0
            tc.max_shot_speed = _max(tc.max_shot_speed, speed)
            pc.max_shot_speed = _max(pc.max_shot_speed, speed)
            if ev.outcome in ("complete", "saved"):
                tc.on_target += 1
                pc.on_target += 1
            if rec.assist_from:
                self._p(rec.assist_from).key_passes += 1
        elif kind == "goal":
            tc.goals += 1
            pc.goals += 1
        elif kind == "pressure":
            tc.pressures += 1
            pc.pressures += 1
        elif kind == "tackle":
            tc.tackles += 1
            pc.touches += 1
            if ev.outcome == "won":
                tc.tackles_won += 1
                pc.tackles_won += 1
            if m.in_ppda_zone(ev.x):
                tc.ppda_actions += 1
        elif kind == "interception":
            tc.interceptions += 1
            pc.interceptions += 1
            pc.touches += 1
            if m.in_ppda_zone(ev.x):
                tc.ppda_actions += 1
        elif kind == "foul":
            tc.fouls += 1
            pc.fouls += 1
            if m.in_ppda_zone(ev.x):
                tc.ppda_actions += 1
        elif kind == "card":
            if ev.card_color == "yellow":
                tc.yellows += 1
                pc.yellows += 1
            else:
                tc.reds += 1
                pc.reds += 1
                if ev.card_color == "second_yellow":
                    tc.yellows += 1
                    pc.yellows += 1
        elif kind == "possession_change" and rec.turnover_by is not None:
            self.teams[rec.turnover_by].turnovers += 1


@dataclass(slots=True)
class Runner:
    """Tracking-derived state for one player."""

    team_id: str
    period: int = 0
    clock_ms: int = -1
    x: float = 0.0
    y: float = 0.0
    recent: deque[float] = field(default_factory=lambda: deque(maxlen=3))
    speed: float = 0.0
    top: float | None = None
    distance_m: float = 0.0
    sprints: int = 0
    run_ms: int = 0
    run_counted: bool = False
    armed: bool = True
    last_trigger_t: int = -SPEED_COOLDOWN_MS
    # bucket index -> [distance m, sprints, top speed]
    buckets: dict[int, list[float]] = field(default_factory=dict)
    heat: list[int] = field(default_factory=lambda: [0] * (HEAT_COLS * HEAT_ROWS))


@dataclass(slots=True)
class Stint:
    on_t: int
    off_t: int | None = None


class StatsEngine:
    """All statistics for one match. Feed it events and frames in stream order."""

    def __init__(self, world: World, info: MatchInfo) -> None:
        self.info = info
        self.match_id = info.match_id
        clubs = {c.team_id: c for c in world.clubs}
        self.home: Club = clubs[info.home]
        self.away: Club = clubs[info.away]
        self.team_ids = (self.home.team_id, self.away.team_id)
        self.players: dict[str, Player] = {}
        self.player_team: dict[str, str] = {}
        for club in (self.home, self.away):
            for p in club.players:
                self.players[p.player_id] = p
                self.player_team[p.player_id] = club.team_id

        self.records: list[EventRecord] = []
        self._seen: set[str] = set()
        self.acc = Accumulator(self.team_ids)
        self.status: Status = "scheduled"
        self.period: Literal[1, 2] = 1
        self.clock_ms = 0
        self.t = 0
        self.seq = -1
        self.first_half_end_ms = 45 * 60_000
        self.score = {t: 0 for t in self.team_ids}
        self.goals: list[GoalItem] = []
        self.cards: list[CardItem] = []
        self.stints: dict[str, list[Stint]] = {
            pid: [Stint(0)] for c in (self.home, self.away) for pid in c.starting_xi
        }

        self._poss_team: str | None = None
        self._live = False
        self._poss_seq = 0
        self._last_on_ball: EventRecord | None = None
        self._after_foul = False
        self._last_event_id: str | None = None
        self._last_event_by_player: dict[str, tuple[int, str]] = {}
        self._last_shot: EventRecord | None = None

        self.runners: dict[str, Runner] = {
            pid: Runner(team) for pid, team in self.player_team.items()
        }
        self._positions: dict[str, tuple[float, float]] = {}  # absolute frame
        self._frame_period = 0

        self.momentum_points: list[MomentumPoint] = []
        self._next_tick_t = TICK_MS
        self._ticks = 0
        self._last_swing_t = -MOMENTUM_SWING_COOLDOWN_MS

    # ------------------------------------------------------------------ helpers

    def _other(self, team_id: str) -> str:
        return self.away.team_id if team_id == self.home.team_id else self.home.team_id

    def _to_team_frame(self, team_id: str, x: float, y: float) -> tuple[float, float]:
        """Absolute (home-attacks-right) coordinates into a team's frame."""
        return (x, y) if team_id == self.home.team_id else m.flip(x, y)

    def _trigger(
        self,
        kind: str,
        suffix: str,
        *,
        team_id: str | None = None,
        player_id: str | None = None,
        value: float | None = None,
        threshold: float | None = None,
        unit: str | None = None,
        event_ids: list[str] | None = None,
        clock_ms: int | None = None,
        period: int | None = None,
    ) -> Trigger:
        ids = (
            event_ids
            if event_ids is not None
            else ([self._last_event_id] if self._last_event_id else [])
        )
        optional = {
            "team_id": team_id, "player_id": player_id, "value": value,
            "threshold": threshold, "unit": unit,
        }  # fmt: skip
        return Trigger(
            trigger_id=f"{self.match_id}:{kind}:{suffix}",
            match_id=self.match_id,
            kind=kind,
            seq=max(self.seq, 0),
            clock_ms=self.clock_ms if clock_ms is None else clock_ms,
            period=self.period if period is None else period,
            event_ids=ids,
            **{k: v for k, v in optional.items() if v is not None},  # unset, not null
        )

    def _elapsed(self, period: int, clock_ms: int) -> int:
        return m.elapsed_ms(period, clock_ms, self.first_half_end_ms)

    # ------------------------------------------------------------------- events

    def on_event(self, ev: MatchEvent) -> list[Trigger]:
        """Ingest one event. Duplicates (same event_id) are ignored."""
        if ev.match_id != self.match_id or ev.event_id in self._seen:
            return []
        self._seen.add(ev.event_id)
        triggers: list[Trigger] = []
        t = self._elapsed(ev.period, ev.clock_ms)

        if self.records:
            prev = self.records[-1]
            if prev.live and prev.poss_team is not None:
                credit = min(max(t - prev.t, 0), MAX_LIVE_GAP_MS)
                prev.poss_ms = credit
                self.acc.add_possession(prev.poss_team, credit)

        self.period, self.clock_ms, self.t, self.seq = ev.period, ev.clock_ms, t, ev.seq
        triggers.extend(self._ticks_until(t))

        kind = ev.type
        team = ev.team_id
        poss, live = self._poss_team, self._live
        turnover_by: str | None = None
        if kind == "kickoff":
            poss, live = team, True
            self.status = "live"
        elif kind in ON_BALL or kind == "possession_change":
            # Tackles and interceptions are always followed by a possession_change, which
            # is where the switch (and any turnover) is recorded.
            if kind == "possession_change" and poss is not None and poss != team:
                last = self._last_on_ball
                if last is None or last.ev.type != "shot" or last.ev.team_id != poss:
                    turnover_by = poss
            poss = team
        if kind in STARTS_PLAY:
            live = True
        elif kind in STOPS_PLAY:
            live = False
        if poss != self._poss_team:
            self._poss_seq += 1
        self._poss_team, self._live = poss, live

        rec = EventRecord(
            ev=ev, t=t, poss_team=poss, live=live, poss_seq=self._poss_seq,
            turnover_by=turnover_by,
        )  # fmt: skip
        if kind == "pass":
            self._annotate_pass(rec)
        elif kind == "shot":
            self._annotate_shot(rec)
        if kind in ON_BALL:
            self._after_foul = False
            self._last_on_ball = rec
        elif kind == "foul":
            self._after_foul = True

        self.records.append(rec)
        self.acc.add(rec)
        self._last_event_id = ev.event_id
        if ev.player_id:
            self._last_event_by_player[ev.player_id] = (t, ev.event_id)
        triggers.extend(self._event_triggers(rec))
        return triggers

    def _annotate_pass(self, rec: EventRecord) -> None:
        ev = rec.ev
        assert ev.team_id is not None and ev.end_x is not None and ev.end_y is not None
        rec.distance_m = round(math.hypot(ev.end_x - ev.x, ev.end_y - ev.y), 2)
        rec.forward_m = ev.end_x - ev.x
        rec.corner = ev.x >= 104 and (ev.y <= 1 or ev.y >= 67)
        bypassed: int | None = None
        space: float | None = None
        opponents = [
            self._to_team_frame(ev.team_id, *pos)
            for pid, pos in self._positions.items()
            if self.player_team[pid] != ev.team_id
        ]
        if opponents:
            bypassed = m.opponents_bypassed(ev.x, ev.end_x, (ox for ox, _ in opponents))
            space = min(math.hypot(ox - ev.end_x, oy - ev.end_y) for ox, oy in opponents)
        rec.difficulty = m.pass_difficulty(
            rec.distance_m, ev.under_pressure, bypassed, rec.forward_m, space
        )

    def _annotate_shot(self, rec: EventRecord) -> None:
        ev = rec.ev
        rec.penalty = self._after_foul and (ev.x, ev.y) == m.PENALTY_SPOT
        free_kick = self._after_foul and not rec.penalty
        rec.xg = round(
            m.xg(
                ev.x, ev.y, header=ev.body_part == "head", under_pressure=ev.under_pressure,
                free_kick=free_kick, penalty=rec.penalty,
            ),
            3,
        )  # fmt: skip
        last = self._last_on_ball
        if (
            last is not None
            and last.ev.type == "pass"
            and last.ev.outcome == "complete"
            and last.ev.team_id == ev.team_id
            and last.ev.recipient_id == ev.player_id
            and last.poss_seq == rec.poss_seq
        ):
            rec.assist_from = last.ev.player_id
        self._last_shot = rec

    def _event_triggers(self, rec: EventRecord) -> list[Trigger]:
        ev = rec.ev
        out: list[Trigger] = []
        suffix = str(ev.seq)
        if ev.type == "shot" and rec.xg is not None and rec.xg > XG_TRIGGER:
            out.append(self._trigger(
                "xg", suffix, team_id=ev.team_id, player_id=ev.player_id, value=round(rec.xg, 2),
                threshold=XG_TRIGGER, unit="xG", event_ids=[ev.event_id],
            ))  # fmt: skip
        elif (
            ev.type == "pass"
            and ev.outcome == "complete"
            and rec.difficulty is not None
            and rec.difficulty > PASS_DIFFICULTY_TRIGGER
        ):
            out.append(self._trigger(
                "pass_difficulty", suffix, team_id=ev.team_id, player_id=ev.player_id,
                value=rec.difficulty, threshold=PASS_DIFFICULTY_TRIGGER, unit="/100",
                event_ids=[ev.event_id],
            ))  # fmt: skip
        elif ev.type == "goal" and ev.team_id is not None and ev.player_id is not None:
            self.score[ev.team_id] += 1
            shot = self._last_shot
            ids = [shot.ev.event_id, ev.event_id] if shot is not None else [ev.event_id]
            home, away = self.team_ids
            self.goals.append(GoalItem(
                event_id=ev.event_id, team_id=ev.team_id, player_id=ev.player_id,
                player_name=self.players[ev.player_id].name,
                minute=m.minute_label(ev.period, ev.clock_ms), period=ev.period,
                clock_ms=ev.clock_ms, xg=shot.xg if shot is not None else None,
                shot_speed_kmh=shot.ev.ball_speed_kmh if shot is not None else None,
                score_after=f"{self.score[home]}-{self.score[away]}",
            ))  # fmt: skip
            out.append(self._trigger(
                "goal", suffix, team_id=ev.team_id, player_id=ev.player_id,
                value=shot.xg if shot is not None else None, unit="xG", event_ids=ids,
            ))  # fmt: skip
        elif ev.type == "card" and ev.team_id is not None and ev.player_id is not None:
            assert ev.card_color is not None
            self.cards.append(CardItem(
                event_id=ev.event_id, team_id=ev.team_id, player_id=ev.player_id,
                player_name=self.players[ev.player_id].name,
                minute=m.minute_label(ev.period, ev.clock_ms), card_color=ev.card_color,
            ))  # fmt: skip
            if ev.card_color != "yellow":
                self._leave(ev.player_id, rec.t)
            out.append(self._trigger(
                "card", suffix, team_id=ev.team_id, player_id=ev.player_id,
                event_ids=[ev.event_id],
            ))  # fmt: skip
        elif ev.type == "substitution" and ev.player_id and ev.recipient_id:
            self._leave(ev.player_id, rec.t)
            self.stints.setdefault(ev.recipient_id, []).append(Stint(rec.t))
        elif ev.type == "period_end":
            if ev.period == 1:
                self.first_half_end_ms = ev.clock_ms
                self.status = "half_time"
                out.append(self._trigger("half_time", suffix, event_ids=[ev.event_id]))
            else:
                self.status = "full_time"
                for stints in self.stints.values():
                    if stints[-1].off_t is None:
                        stints[-1].off_t = rec.t
                out.append(self._trigger("full_time", suffix, event_ids=[ev.event_id]))
        return out

    def _leave(self, player_id: str, t: int) -> None:
        stints = self.stints.get(player_id)
        if stints and stints[-1].off_t is None:
            stints[-1].off_t = t
        self._positions.pop(player_id, None)

    # ----------------------------------------------------------------- momentum

    def _ticks_until(self, t: int) -> list[Trigger]:
        out: list[Trigger] = []
        while t >= self._next_tick_t:
            self._next_tick_t += TICK_MS
            self._ticks += 1
            point = self._momentum_point(t)
            self.momentum_points.append(point)
            out.append(self._trigger("tick", str(self._ticks)))
            swing = self._swing()
            if (
                abs(swing) >= MOMENTUM_SWING_TRIGGER
                and t - self._last_swing_t >= MOMENTUM_SWING_COOLDOWN_MS
            ):
                self._last_swing_t = t
                out.append(self._trigger(
                    "momentum_swing", str(self._ticks), value=swing,
                    threshold=MOMENTUM_SWING_TRIGGER, unit="index points",
                ))  # fmt: skip
        return out

    def _window_records(self, lo_t: int, hi_t: int) -> list[EventRecord]:
        out = []
        for rec in reversed(self.records):
            if rec.t <= lo_t:
                break
            if rec.t <= hi_t:
                out.append(rec)
        out.reverse()
        return out

    def momentum_inputs(self, t: int) -> tuple[float, float, dict[str, float] | None]:
        """Raw Control vs Chaos inputs for the 5 minutes up to t.

        Returns (ball-in-play minutes, home possession share, raw values or None when
        there is too little play to judge).
        """
        recs = self._window_records(t - MOMENTUM_WINDOW_MS, t)
        live_ms = home_ms = turnovers = pressures = 0
        progress = 0.0
        completed_by_seq: dict[int, int] = {}
        for rec in recs:
            live_ms += rec.poss_ms
            if rec.poss_team == self.home.team_id:
                home_ms += rec.poss_ms
            ev = rec.ev
            if rec.poss_team is not None and rec.live:
                completed_by_seq.setdefault(rec.poss_seq, 0)
            if ev.type == "pass" and ev.outcome == "complete":
                completed_by_seq[rec.poss_seq] = completed_by_seq.get(rec.poss_seq, 0) + 1
                progress += max(rec.forward_m, 0.0)
            elif ev.type == "carry" and ev.end_x is not None:
                progress += max(ev.end_x - ev.x, 0.0)
            elif ev.type == "pressure":
                pressures += 1
            elif rec.turnover_by is not None:
                turnovers += 1
        minutes = live_ms / 60_000
        share = home_ms / live_ms if live_ms else 0.5
        if minutes < 0.5 or not completed_by_seq:
            return minutes, share, None
        return (
            minutes,
            share,
            {
                "passes_per_possession": sum(completed_by_seq.values()) / len(completed_by_seq),
                "turnovers_per_min": turnovers / minutes,
                "pressures_per_min": pressures / minutes,
                "progress_m_per_min": progress / minutes,
            },
        )

    def _momentum_point(self, t: int) -> MomentumPoint:
        _, share, raw = self.momentum_inputs(t)
        if raw is None:
            comps = {"stability": 0.0, "turnovers": 0.0, "pressure": 0.0, "tempo": 0.0}
        else:
            comps = m.momentum_components(**raw)
        return MomentumPoint(
            period=self.period,
            clock_ms=self.clock_ms,
            minute=m.minute_label(self.period, self.clock_ms),
            index=m.control_chaos_index(comps),
            home_share=round(share, 3),
            components=MomentumComponents(**comps),
        )

    def _swing(self) -> float:
        pts = self.momentum_points
        back = MOMENTUM_WINDOW_MS // TICK_MS
        if len(pts) <= back:
            return 0.0
        return round(pts[-1].index - pts[-1 - back].index, 1)

    def momentum_now(self) -> MomentumNow:
        if not self.momentum_points:
            return MomentumNow(index=0.0, swing=0.0, dominant_team_id=None)
        last = self.momentum_points[-1]
        dominant = None
        if last.home_share > 0.55:
            dominant = self.home.team_id
        elif last.home_share < 0.45:
            dominant = self.away.team_id
        return MomentumNow(index=last.index, swing=self._swing(), dominant_team_id=dominant)

    # ----------------------------------------------------------------- tracking

    def on_frame(self, frame: TrackingFrame) -> list[Trigger]:
        if frame.match_id != self.match_id:
            return []
        triggers: list[Trigger] = []
        period, clock = frame.period, frame.clock_ms
        t = self._elapsed(period, clock)
        bucket = t // BUCKET_MS
        heat_sample = clock % 1000 == 0
        home_id = self.home.team_id
        positions: dict[str, tuple[float, float]] = {}
        for p in frame.players:
            pid, x, y = p.player_id, p.x, p.y
            positions[pid] = (x, y)
            r = self.runners.get(pid)
            if r is None:
                continue
            if r.period == period and clock - r.clock_ms == FRAME_MS:
                step = math.hypot(x - r.x, y - r.y)
                r.recent.append(step / (FRAME_MS / 1000) * 3.6)
                speed = sum(r.recent) / len(r.recent)
                r.speed = speed
                r.distance_m += step
                b = r.buckets.get(bucket)
                if b is None:
                    b = r.buckets[bucket] = [0.0, 0.0, 0.0]
                b[0] += step
                if speed > b[2]:
                    b[2] = speed
                if r.top is None or speed > r.top:
                    r.top = speed
                if speed >= m.SPRINT_KMH:
                    r.run_ms += FRAME_MS
                    if r.run_ms >= m.SPRINT_MIN_MS and not r.run_counted:
                        r.sprints += 1
                        b[1] += 1
                        r.run_counted = True
                else:
                    r.run_ms, r.run_counted = 0, False
                if (
                    round(speed, 1) > SPEED_TRIGGER_KMH
                    and r.armed
                    and t - r.last_trigger_t >= SPEED_COOLDOWN_MS
                ):
                    r.armed = False
                    r.last_trigger_t = t
                    seen = self._last_event_by_player.get(pid)
                    ids = [seen[1]] if seen is not None and t - seen[0] < 10_000 else None
                    triggers.append(self._trigger(
                        "speed", f"{pid}:{period}:{clock}", team_id=r.team_id, player_id=pid,
                        value=round(speed, 1), threshold=SPEED_TRIGGER_KMH, unit="km/h",
                        event_ids=ids, clock_ms=clock, period=period,
                    ))  # fmt: skip
                elif speed < SPEED_REARM_KMH:
                    r.armed = True
            else:
                r.recent.clear()
                r.speed = 0.0
            r.period, r.clock_ms, r.x, r.y = period, clock, x, y
            if heat_sample:
                hx, hy = (x, y) if r.team_id == home_id else m.flip(x, y)
                col = min(int(hx / m.PITCH_LENGTH * HEAT_COLS), HEAT_COLS - 1)
                row = min(int(hy / m.PITCH_WIDTH * HEAT_ROWS), HEAT_ROWS - 1)
                r.heat[row * HEAT_COLS + col] += 1
        self._positions = positions
        self._frame_period = period
        return triggers

    # ------------------------------------------------------------------ queries

    def _window_bounds(self, window: Window) -> tuple[int, int, int | None]:
        """(lo_t exclusive, hi_t inclusive, period filter)."""
        if window == "match":
            return -1, self.t, None
        if window == "first_half":
            return -1, self.t, 1
        if window == "second_half":
            return -1, self.t, 2
        minutes = int(window.split("_")[1])
        return self.t - minutes * 60_000, self.t, None

    def _accumulate(self, window: Window) -> Accumulator:
        if window == "match":
            return self.acc
        lo, hi, period = self._window_bounds(window)
        acc = Accumulator(self.team_ids)
        for rec in self.records:
            if lo < rec.t <= hi and (period is None or rec.ev.period == period):
                acc.add(rec)
        return acc

    def _bucket_range(self, window: Window) -> tuple[int, int]:
        """Inclusive bucket range for tracking aggregates."""
        if window == "match":
            return -1, 1 << 40
        if window == "first_half":
            return -1, self.first_half_end_ms // BUCKET_MS
        if window == "second_half":
            if self.period == 1:
                return 1 << 40, 1 << 40
            return self.first_half_end_ms // BUCKET_MS + 1, 1 << 40
        lo, _, _ = self._window_bounds(window)
        return lo // BUCKET_MS + 1, 1 << 40

    def _physical(self, player_id: str, window: Window) -> tuple[float, int, float | None]:
        """(distance m, sprints, top speed km/h) for a player in a window."""
        r = self.runners[player_id]
        if window == "match":
            return r.distance_m, r.sprints, r.top
        lo, hi = self._bucket_range(window)
        dist, sprints, top = 0.0, 0, None
        for b, (d, s, v) in r.buckets.items():
            if lo <= b <= hi:
                dist += d
                sprints += int(s)
                top = _max(top, v)
        return dist, sprints, top

    def _team_stats(self, acc: Accumulator, team_id: str, window: Window) -> TeamStats:
        tc = acc.teams[team_id]
        club = self.home if team_id == self.home.team_id else self.away
        other = acc.teams[self._other(team_id)]
        dist, sprints, top = 0.0, 0, None
        for pid, team in self.player_team.items():
            if team == team_id:
                d, s, v = self._physical(pid, window)
                dist += d
                sprints += s
                if v is not None:
                    top = _max(top, v)
        return TeamStats(
            team_id=team_id,
            name=club.name,
            short_name=club.short_name,
            goals=tc.goals,
            shots=tc.shots,
            shots_on_target=tc.on_target,
            xg=round(tc.xg, 2),
            max_shot_speed_kmh=_r1(tc.max_shot_speed),
            passes=tc.passes,
            passes_completed=tc.completed,
            pass_accuracy_pct=m.pass_accuracy_pct(tc.completed, tc.passes),
            avg_pass_distance_m=_avg(tc.pass_distance, tc.passes),
            avg_pass_speed_kmh=_avg(tc.pass_speed, tc.passes),
            avg_pass_difficulty=_avg(tc.difficulty, tc.passes),
            difficult_passes_completed=tc.difficult_completed,
            possession_pct=m.possession_pct(tc.poss_ms, other.poss_ms),
            pressures=tc.pressures,
            tackles=tc.tackles,
            tackles_won=tc.tackles_won,
            interceptions=tc.interceptions,
            fouls=tc.fouls,
            yellow_cards=tc.yellows,
            red_cards=tc.reds,
            corners=tc.corners,
            turnovers=tc.turnovers,
            ppda=m.ppda(tc.ppda_passes, tc.ppda_actions),
            distance_km=round(dist / 1000, 2),
            sprints=sprints,
            top_speed_kmh=_r1(top),
        )

    def team_stats(self, window: Window = "match") -> TeamStatsReport:
        acc = self._accumulate(window)
        return TeamStatsReport(
            match_id=self.match_id,
            window=window,
            minute=self.minute(),
            teams=[self._team_stats(acc, t, window) for t in self.team_ids],
        )

    def minutes_played(self, player_id: str) -> int:
        total = 0
        for stint in self.stints.get(player_id, []):
            end = stint.off_t if stint.off_t is not None else self.t
            total += max(0, end - stint.on_t)
        return total // 60_000

    def on_pitch(self, player_id: str) -> bool:
        stints = self.stints.get(player_id)
        if not stints:
            return False
        return stints[-1].off_t is None and self.status != "full_time"

    def player_stats(self, player_id: str, window: Window = "match") -> PlayerStats:
        if player_id not in self.players:
            raise KeyError(f"unknown player {player_id!r}")
        acc = self._accumulate(window)
        pc = acc.players.get(player_id, PlayerCounters())
        p = self.players[player_id]
        dist, sprints, top = self._physical(player_id, window)
        heat = self.runners[player_id].heat
        total = sum(heat)
        return PlayerStats(
            player_id=player_id,
            name=p.name,
            short_name=p.short_name,
            team_id=self.player_team[player_id],
            shirt_number=p.shirt_number,
            position=p.position,
            on_pitch=self.on_pitch(player_id),
            minutes_played=self.minutes_played(player_id),
            touches=pc.touches,
            passes=pc.passes,
            passes_completed=pc.completed,
            pass_accuracy_pct=m.pass_accuracy_pct(pc.completed, pc.passes),
            avg_pass_difficulty=_avg(pc.difficulty, pc.passes),
            max_pass_difficulty=pc.max_difficulty,
            key_passes=pc.key_passes,
            shots=pc.shots,
            shots_on_target=pc.on_target,
            goals=pc.goals,
            xg=round(pc.xg, 2),
            max_shot_speed_kmh=_r1(pc.max_shot_speed),
            pressures=pc.pressures,
            tackles_won=pc.tackles_won,
            interceptions=pc.interceptions,
            fouls=pc.fouls,
            yellow_cards=pc.yellows,
            red_cards=pc.reds,
            distance_km=round(dist / 1000, 2),
            sprints=sprints,
            top_speed_kmh=_r1(top),
            heatmap=Heatmap(
                cols=HEAT_COLS,
                rows=HEAT_ROWS,
                cells=[round(c / total, 4) if total else 0.0 for c in heat],
            ),
        )

    def events(
        self, since_seq: int = -1, types: Iterable[str] | None = None, limit: int = 50
    ) -> list[MatchEvent]:
        """Events with seq > since_seq, optionally filtered by type; the most recent `limit`."""
        wanted = set(types) if types else None
        out = [
            r.ev
            for r in self.records
            if r.ev.seq > since_seq and (wanted is None or r.ev.type in wanted)
        ]
        return out[-limit:] if limit > 0 else out

    def momentum(self, window: Window = "last_15") -> Momentum:
        lo, hi, period = self._window_bounds(window)
        pts = []
        for p in self.momentum_points:
            t = self._elapsed(p.period, p.clock_ms)
            if lo < t <= hi and (period is None or p.period == period):
                pts.append(p)
        return Momentum(match_id=self.match_id, window=window, now=self.momentum_now(), points=pts)

    def compare_periods(self) -> PeriodComparison:
        first = self._accumulate("first_half")
        second = self._accumulate("second_half")
        return PeriodComparison(
            match_id=self.match_id,
            first_half=[self._team_stats(first, t, "first_half") for t in self.team_ids],
            second_half=[self._team_stats(second, t, "second_half") for t in self.team_ids],
        )

    def shot_map(self) -> list[ShotMapItem]:
        out = []
        for rec in self.records:
            ev = rec.ev
            if ev.type != "shot" or ev.team_id is None or ev.player_id is None:
                continue
            out.append(ShotMapItem(
                event_id=ev.event_id, team_id=ev.team_id, player_id=ev.player_id,
                player_name=self.players[ev.player_id].name,
                minute=m.minute_label(ev.period, ev.clock_ms), x=ev.x, y=ev.y,
                outcome=ev.outcome,
                xg=rec.xg or 0.0, body_part=ev.body_part or "other",
                speed_kmh=ev.ball_speed_kmh or 0.0,
            ))  # fmt: skip
        return out

    def pass_network(self, team_id: str, window: Window = "match") -> PassNetwork:
        """Average positions of each player's completed passes and receptions, and the
        pass links between players with at least NETWORK_MIN_PASSES completions."""
        lo, hi, period = self._window_bounds(window)
        spots: dict[str, list[tuple[float, float]]] = {}
        made: dict[str, int] = {}
        links: dict[tuple[str, str], int] = {}
        for rec in self.records:
            ev = rec.ev
            if not (lo < rec.t <= hi and (period is None or ev.period == period)):
                continue
            if ev.type != "pass" or ev.team_id != team_id or ev.outcome != "complete":
                continue
            src, dst = ev.player_id, ev.recipient_id
            if src is None or dst is None or ev.end_x is None or ev.end_y is None:
                continue
            spots.setdefault(src, []).append((ev.x, ev.y))
            spots.setdefault(dst, []).append((ev.end_x, ev.end_y))
            made[src] = made.get(src, 0) + 1
            a, b = sorted((src, dst))
            links[(a, b)] = links.get((a, b), 0) + 1
        nodes = []
        for pid, pts in sorted(spots.items()):
            p = self.players[pid]
            nodes.append(NetworkNode(
                player_id=pid, short_name=p.short_name, shirt_number=p.shirt_number,
                x=round(sum(x for x, _ in pts) / len(pts), 1),
                y=round(sum(y for _, y in pts) / len(pts), 1),
                passes=made.get(pid, 0),
            ))  # fmt: skip
        edges = [
            NetworkEdge(source=a, target=b, count=n)
            for (a, b), n in sorted(links.items())
            if n >= NETWORK_MIN_PASSES
        ]
        return PassNetwork(team_id=team_id, nodes=nodes, edges=edges)

    def difficulty_histogram(self, team_id: str) -> DifficultyHistogram:
        completed, incomplete = [0] * 10, [0] * 10
        for rec in self.records:
            ev = rec.ev
            if ev.type != "pass" or ev.team_id != team_id or rec.difficulty is None:
                continue
            b = min(int(rec.difficulty // 10), 9)
            (completed if ev.outcome == "complete" else incomplete)[b] += 1
        return DifficultyHistogram(team_id=team_id, completed=completed, incomplete=incomplete)

    def analyst_report(self) -> AnalystReport:
        return AnalystReport(
            match_id=self.match_id,
            minute=self.minute(),
            shots=self.shot_map(),
            networks=[self.pass_network(t) for t in self.team_ids],
            histograms=[self.difficulty_histogram(t) for t in self.team_ids],
            momentum=list(self.momentum_points),
        )

    def minute(self) -> str:
        return m.minute_label(self.period, self.clock_ms)

    def _team_line(self, club: Club) -> TeamLine:
        return TeamLine(
            team_id=club.team_id,
            name=club.name,
            short_name=club.short_name,
            score=self.score[club.team_id],
            red_cards=self.acc.teams[club.team_id].reds,
            color=club.colors.primary,
        )

    def match_state(self) -> MatchState:
        return MatchState(
            match_id=self.match_id,
            status=self.status,
            scenario=self.info.scenario,
            period=self.period,
            clock_ms=self.clock_ms,
            clock_display=m.clock_display(self.period, self.clock_ms),
            minute=self.minute(),
            seq=self.seq,
            home=self._team_line(self.home),
            away=self._team_line(self.away),
            possession_team_id=self._poss_team,
            goals=list(self.goals),
            cards=list(self.cards),
            momentum=self.momentum_now(),
        )

    def snapshot(self) -> StatsSnapshot:
        """Match-level numbers for the live screen. Cheap: no replay."""
        lines = []
        for pid, team in self.player_team.items():
            if pid not in self.stints:
                continue
            pc = self.acc.players.get(pid, PlayerCounters())
            r = self.runners[pid]
            lines.append(PlayerLine(
                player_id=pid, team_id=team, on_pitch=self.on_pitch(pid), touches=pc.touches,
                passes=pc.passes, passes_completed=pc.completed, shots=pc.shots,
                goals=pc.goals, xg=round(pc.xg, 2), distance_km=round(r.distance_m / 1000, 2),
                top_speed_kmh=_r1(r.top), speed_kmh=round(r.speed, 1),
            ))  # fmt: skip
        return StatsSnapshot(
            match_id=self.match_id,
            seq=max(self.seq, 0),
            status=self.status,
            period=self.period,
            clock_ms=self.clock_ms,
            clock_display=m.clock_display(self.period, self.clock_ms),
            minute=self.minute(),
            teams=[self._team_stats(self.acc, t, "match") for t in self.team_ids],
            momentum=self.momentum_now(),
            players=lines,
        )


def _avg(total: float, n: int) -> float | None:
    return round(total / n, 1) if n else None


def _r1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)
