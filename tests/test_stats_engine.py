"""Stats Engine invariants over a full simulated match (with tracking)."""

from __future__ import annotations

import json
import re
from collections import Counter

import pytest

from contracts import MatchEvent, Trigger, World
from sim.engine import MatchConfig, MatchEngine
from stats import WINDOWS, StatsEngine
from stats.engine import PASS_DIFFICULTY_TRIGGER, SPEED_TRIGGER_KMH, TICK_MS, XG_TRIGGER

from .conftest import match_info, stats_with_tracking, validator

ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _stats() -> StatsEngine:
    return stats_with_tracking()[0]


def _triggers() -> tuple[Trigger, ...]:
    return stats_with_tracking()[1]


def _events() -> list[MatchEvent]:
    return [r.ev for r in _stats().records]


def test_team_totals_match_raw_event_counts() -> None:
    stats, events = _stats(), _events()
    for team in stats.team_stats("match").teams:
        own = [e for e in events if e.team_id == team.team_id]
        passes = [e for e in own if e.type == "pass"]
        shots = [e for e in own if e.type == "shot"]
        assert team.passes == len(passes)
        assert team.passes_completed == sum(e.outcome == "complete" for e in passes)
        assert team.shots == len(shots)
        assert team.shots_on_target == sum(e.outcome in ("complete", "saved") for e in shots)
        assert team.goals == sum(e.type == "goal" for e in own)
        assert team.fouls == sum(e.type == "foul" for e in own)
        assert team.pressures == sum(e.type == "pressure" for e in own)
        assert team.interceptions == sum(e.type == "interception" for e in own)
        assert team.yellow_cards == sum(
            e.type == "card" and e.card_color in ("yellow", "second_yellow") for e in own
        )


def test_possession_splits_to_100_and_is_balanced() -> None:
    a, b = _stats().team_stats("match").teams
    assert a.possession_pct + b.possession_pct == pytest.approx(100, abs=0.11)
    assert 30 < a.possession_pct < 70


def test_plausible_match_level_numbers() -> None:
    for team in _stats().team_stats("match").teams:
        assert team.pass_accuracy_pct is not None and 65 < team.pass_accuracy_pct < 92
        assert team.avg_pass_distance_m is not None and 12 < team.avg_pass_distance_m < 30
        assert team.ppda is not None and 3 < team.ppda < 25
        assert 0.2 < team.xg < 5
        assert 90 < team.distance_km < 145  # 11 players, incl. substitutes
        assert team.top_speed_kmh is not None and 28 < team.top_speed_kmh < 37
        assert team.sprints > 20


def test_score_and_goal_list_follow_goal_events() -> None:
    stats = _stats()
    state = stats.match_state()
    goals = [e for e in _events() if e.type == "goal"]
    assert [g.event_id for g in state.goals] == [e.event_id for e in goals]
    assert state.home.score == sum(e.team_id == state.home.team_id for e in goals)
    assert state.away.score == sum(e.team_id == state.away.team_id for e in goals)
    assert state.goals[-1].score_after == f"{state.home.score}-{state.away.score}"
    assert state.status == "full_time"
    assert all(g.xg is not None and 0 < g.xg < 1 for g in state.goals)


@pytest.mark.parametrize("field", ["passes", "shots", "goals", "fouls", "tackles", "turnovers"])
def test_halves_add_up_to_the_match(field: str) -> None:
    stats = _stats()
    match = {t.team_id: getattr(t, field) for t in stats.team_stats("match").teams}
    halves = stats.compare_periods()
    for first, second in zip(halves.first_half, halves.second_half, strict=True):
        assert getattr(first, field) + getattr(second, field) == match[first.team_id]


def test_distance_by_half_adds_up() -> None:
    stats = _stats()
    match = {t.team_id: t.distance_km for t in stats.team_stats("match").teams}
    halves = stats.compare_periods()
    for first, second in zip(halves.first_half, halves.second_half, strict=True):
        assert first.distance_km + second.distance_km == pytest.approx(
            match[first.team_id], abs=0.05
        )


def test_last_n_windows_are_nested() -> None:
    stats = _stats()
    passes = {
        w: sum(t.passes for t in stats.team_stats(w).teams)
        for w in ("last_5", "last_10", "last_15", "match")
    }
    assert 0 < passes["last_5"] <= passes["last_10"] <= passes["last_15"] < passes["match"]


def test_every_window_and_snapshot_validates() -> None:
    stats = _stats()
    for window in WINDOWS:
        stats.team_stats(window)
        stats.momentum(window)
    v = validator("stats")
    v.validate(json.loads(stats.snapshot().model_dump_json()))


def test_player_stats_add_up_to_team_stats() -> None:
    stats = _stats()
    team_passes = {t.team_id: t.passes for t in stats.team_stats().teams}
    by_team: Counter[str] = Counter()
    for pid in stats.players:
        p = stats.player_stats(pid)
        by_team[p.team_id] += p.passes
        assert p.heatmap is not None
        if p.minutes_played:
            assert sum(p.heatmap.cells) == pytest.approx(1.0, abs=0.01)
    assert dict(by_team) == team_passes


def test_minutes_played() -> None:
    stats = _stats()
    keeper = stats.player_stats("LAG-01")
    assert keeper.minutes_played >= 90 and not keeper.on_pitch  # full time
    subs = [e for e in _events() if e.type == "substitution"]
    assert subs
    on = stats.player_stats(subs[0].recipient_id or "")
    off = stats.player_stats(subs[0].player_id or "")
    assert 0 < on.minutes_played < 45 < off.minutes_played


def test_key_passes_never_exceed_shots() -> None:
    stats = _stats()
    keys = sum(stats.player_stats(pid).key_passes for pid in stats.players)
    shots = sum(t.shots for t in stats.team_stats().teams)
    assert 0 < keys <= shots


def test_unknown_player_raises() -> None:
    with pytest.raises(KeyError):
        _stats().player_stats("XXX-99")


def test_events_query_filters() -> None:
    stats = _stats()
    shots = stats.events(types=["shot"], limit=0)
    assert shots and all(e.type == "shot" for e in shots)
    recent = stats.events(since_seq=100, limit=5)
    assert len(recent) == 5 and all(e.seq > 100 for e in recent)
    assert recent[-1].seq == stats.seq


def test_duplicate_events_are_ignored(world: World) -> None:
    engine = MatchEngine(world, MatchConfig(home="NBR", away="KVA", seed=9))
    stats = StatsEngine(world, match_info(engine.match_id, "NBR", "KVA", 9))
    events = list(engine.events())
    for e in events:
        stats.on_event(e)
    before = stats.snapshot().model_dump()
    for e in events[:200]:
        assert stats.on_event(e) == []
    assert stats.snapshot().model_dump() == before


def test_events_for_another_match_are_ignored(world: World) -> None:
    engine = MatchEngine(world, MatchConfig(home="NBR", away="KVA", seed=9))
    stats = StatsEngine(world, match_info("some-other-match", "NBR", "KVA", 9))
    for e in list(engine.events())[:50]:
        stats.on_event(e)
    assert stats.records == []


class TestTriggers:
    def test_ids_are_unique_and_evidence_is_real(self) -> None:
        triggers = _triggers()
        assert len({t.trigger_id for t in triggers}) == len(triggers)
        ids = {e.event_id for e in _events()}
        for t in triggers:
            assert all(ULID.match(i) and i in ids for i in t.event_ids)
            assert t.event_ids or t.kind == "speed"

    def test_thresholds(self) -> None:
        by_id = {r.ev.event_id: r for r in _stats().records}
        for t in _triggers():
            if t.kind == "xg":
                rec = by_id[t.event_ids[0]]
                assert rec.ev.type == "shot" and rec.xg is not None and rec.xg > XG_TRIGGER
            elif t.kind == "pass_difficulty":
                rec = by_id[t.event_ids[0]]
                assert rec.ev.type == "pass" and rec.ev.outcome == "complete"
                assert t.value is not None and t.value > PASS_DIFFICULTY_TRIGGER
            elif t.kind == "speed":
                assert t.value is not None and t.value > SPEED_TRIGGER_KMH
                assert t.player_id is not None

    def test_key_events_raise_triggers(self) -> None:
        kinds = Counter(t.kind for t in _triggers())
        events = Counter(e.type for e in _events())
        assert kinds["goal"] == events["goal"]
        assert kinds["card"] == events["card"]
        assert kinds["half_time"] == kinds["full_time"] == 1
        assert kinds["speed"] >= 1

    def test_tick_every_30_seconds_of_play(self) -> None:
        stats = _stats()
        ticks = [t for t in _triggers() if t.kind == "tick"]
        assert len(ticks) == stats.t // TICK_MS
        assert len(stats.momentum_points) == len(ticks)

    def test_momentum_index_bounded_and_moving(self) -> None:
        index = [p.index for p in _stats().momentum_points]
        assert all(-100 <= i <= 100 for i in index)
        assert max(index) - min(index) > 20

    def test_momentum_swing_triggers_meet_the_threshold(self) -> None:
        for t in _triggers():
            if t.kind == "momentum_swing":
                assert t.value is not None and abs(t.value) >= 30


class TestAnalystReport:
    def test_shot_map_matches_shots(self) -> None:
        stats = _stats()
        shots = stats.shot_map()
        assert len(shots) == sum(t.shots for t in stats.team_stats().teams)
        assert all(0 < s.xg < 1 for s in shots)
        goals = [s for s in shots if s.outcome == "complete"]
        assert len(goals) == len(stats.goals)

    def test_pass_network(self) -> None:
        stats = _stats()
        home = stats.home.team_id
        net = stats.pass_network(home)
        completed = next(t for t in stats.team_stats().teams if t.team_id == home)
        assert sum(n.passes for n in net.nodes) == completed.passes_completed
        ids = {n.player_id for n in net.nodes}
        assert all(e.source in ids and e.target in ids and e.count >= 3 for e in net.edges)
        assert all(stats.player_team[pid] == home for pid in ids)
        keeper = next(n for n in net.nodes if n.player_id == "LAG-01")
        striker = next(n for n in net.nodes if n.player_id == "LAG-09")
        assert keeper.x < 25 < 50 < striker.x  # keeper deep, striker high, own frame

    def test_difficulty_histogram_counts_every_pass(self) -> None:
        stats = _stats()
        for team in stats.team_stats().teams:
            h = stats.difficulty_histogram(team.team_id)
            assert sum(h.completed) == team.passes_completed
            assert sum(h.completed) + sum(h.incomplete) == team.passes
            assert sum(h.completed[8:]) >= team.difficult_passes_completed  # bins 80-100

    def test_report_validates(self) -> None:
        report = _stats().analyst_report()
        assert len(report.networks) == len(report.histograms) == 2
        assert report.momentum
