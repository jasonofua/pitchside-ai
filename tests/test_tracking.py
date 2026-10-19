from __future__ import annotations

import itertools
import math
import statistics
from collections import defaultdict

from contracts import MatchEvent, TrackingFrame, World
from sim.engine import MatchConfig, MatchEngine
from sim.tracking import FRAME_MS, TrackingGenerator

from .conftest import as_json, match_with_tracking, validator


def _frames() -> list[TrackingFrame]:
    return [i for i in match_with_tracking() if isinstance(i, TrackingFrame)]


def _events() -> list[MatchEvent]:
    return [i for i in match_with_tracking() if isinstance(i, MatchEvent)]


def test_every_frame_is_valid() -> None:
    v = validator("tracking")
    for n, frame in enumerate(_frames()):
        data = as_json(frame)
        TrackingFrame.model_validate(data)  # bounds, required fields, no extras
        if n % 25 == 0:
            v.validate(data)
        assert 18 <= len(frame.players) <= 22


def test_frames_on_a_5hz_grid_only_while_the_ball_is_live() -> None:
    frames, events = _frames(), _events()
    ends = {e.period: e.clock_ms for e in events if e.type == "period_end"}
    for period in (1, 2):
        clocks = [f.clock_ms for f in frames if f.period == period]
        start = 0 if period == 1 else 45 * 60_000
        assert clocks[0] == start
        assert all(b - a == FRAME_MS for a, b in itertools.pairwise(clocks))
        assert clocks[-1] < ends[period] <= clocks[-1] + FRAME_MS


def test_stream_is_in_clock_order() -> None:
    keys = [(i.period, i.clock_ms) for i in match_with_tracking()]
    assert keys == sorted(keys)


def test_player_speeds_are_human() -> None:
    last: dict[str, tuple[int, float, float]] = {}
    top: dict[str, float] = defaultdict(float)
    distance: dict[str, float] = defaultdict(float)
    for frame in _frames():
        for p in frame.players:
            if p.player_id in last and frame.clock_ms - last[p.player_id][0] == FRAME_MS:
                _, x, y = last[p.player_id]
                step = math.hypot(p.x - x, p.y - y)
                distance[p.player_id] += step
                top[p.player_id] = max(top[p.player_id], step / (FRAME_MS / 1000) * 3.6)
            last[p.player_id] = (frame.clock_ms, p.x, p.y)
    assert max(top.values()) <= 36.5  # km/h, elite sprint ceiling
    assert max(top.values()) >= 30.0
    starters_km = [distance[pid] / 1000 for pid in ("LAG-08", "LAG-06", "HCF-06", "HCF-10")]
    assert all(8.0 <= km <= 14.0 for km in starters_km), starters_km


def test_ball_is_at_the_actor_for_on_ball_events() -> None:
    frames = {(f.period, f.clock_ms): f for f in _frames()}
    gaps = []
    for e in _events():
        if e.type not in ("pass", "carry", "shot") or e.player_id is None:
            continue
        frame = frames.get((e.period, e.clock_ms - e.clock_ms % FRAME_MS))
        if frame is None:
            continue
        pos = {p.player_id: (p.x, p.y) for p in frame.players}
        if e.player_id in pos:
            gaps.append(
                math.hypot(pos[e.player_id][0] - frame.ball.x, pos[e.player_id][1] - frame.ball.y)
            )
    assert statistics.median(gaps) < 2.0
    assert sorted(gaps)[int(len(gaps) * 0.9)] < 6.0


def test_substitutes_appear_and_leave() -> None:
    subs = [e for e in _events() if e.type == "substitution"]
    assert subs
    frames = _frames()
    for sub in subs:
        after = next(f for f in frames if (f.period, f.clock_ms) > (sub.period, sub.clock_ms))
        ids = {p.player_id for p in after.players}
        assert sub.recipient_id in ids and sub.player_id not in ids


def test_tracking_is_deterministic(world: World) -> None:
    def first_frames() -> list[str]:
        engine = MatchEngine(world, MatchConfig(home="KVA", away="NBR", seed=9))
        stream = TrackingGenerator(world, engine.match_id, "KVA", "NBR", 9).stream(engine.events())
        return [i.model_dump_json() for i in itertools.islice(stream, 1500)]

    assert first_frames() == first_frames()
