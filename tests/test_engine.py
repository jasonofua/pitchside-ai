from __future__ import annotations

from collections import Counter

import pytest

from contracts import World
from sim.engine import HALF_MS, MatchConfig, MatchEngine, expected_goal_probability

from .conftest import as_json, match_events, validator


def test_same_seed_same_match(world: World) -> None:
    def run() -> list[str]:
        engine = MatchEngine(world, MatchConfig(home="NBR", away="KVA", seed=7))
        return [e.model_dump_json() for e in engine.events()]

    assert run() == run()


def test_different_seed_different_match() -> None:
    a = [(e.type, e.clock_ms) for e in match_events(seed=1)]
    b = [(e.type, e.clock_ms) for e in match_events(seed=2)]
    assert a != b


def test_match_id_changes_ids_but_not_the_match(world: World) -> None:
    base = list(MatchEngine(world, MatchConfig(home="LAG", away="HCF", seed=5)).events())
    other = list(
        MatchEngine(world, MatchConfig(home="LAG", away="HCF", seed=5, match_id="live-1")).events()
    )
    assert {e.event_id for e in base}.isdisjoint(e.event_id for e in other)
    strip = {"event_id", "match_id"}
    assert [e.model_dump(exclude=strip) for e in base] == [
        e.model_dump(exclude=strip) for e in other
    ]


@pytest.mark.parametrize(("home", "away", "seed"), [("LAG", "HCF", 42), ("NBR", "KVA", 3)])
def test_every_event_validates_against_json_schema(home: str, away: str, seed: int) -> None:
    v = validator("event")
    for event in match_events(home, away, seed):
        errors = list(v.iter_errors(as_json(event)))
        assert not errors, (event, errors[0].message)


@pytest.mark.parametrize("seed", [42, 3])
def test_sequence_and_clock_ordering(seed: int) -> None:
    events = match_events(seed=seed)
    assert [e.seq for e in events] == list(range(len(events)))
    ids = [e.event_id for e in events]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    for period in (1, 2):
        clocks = [e.clock_ms for e in events if e.period == period]
        assert clocks == sorted(clocks)
    assert [e.period for e in events] == sorted(e.period for e in events)


def test_period_structure() -> None:
    events = match_events()
    kickoffs = [e for e in events if e.type == "kickoff"]
    ends = [e for e in events if e.type == "period_end"]
    assert events[0].type == "kickoff" and events[0].clock_ms == 0
    assert events[-1].type == "period_end" and events[-1].period == 2
    assert [e.period for e in ends] == [1, 2]
    assert HALF_MS <= ends[0].clock_ms <= HALF_MS + 4 * 60_000
    assert 2 * HALF_MS <= ends[1].clock_ms <= 2 * HALF_MS + 8 * 60_000
    second_half = next(e for e in kickoffs if e.period == 2)
    assert second_half.clock_ms == HALF_MS
    goals = sum(e.type == "goal" for e in events)
    assert len(kickoffs) == 2 + goals


@pytest.mark.parametrize("seed", range(6))
def test_goals_follow_scoring_shots(seed: int) -> None:
    events = match_events(seed=seed)
    for i, event in enumerate(events):
        if event.type == "goal":
            shot = events[i - 1]
            assert shot.type == "shot" and shot.outcome == "complete"
            assert shot.player_id == event.player_id
        if event.type == "shot" and event.outcome == "complete":
            assert events[i + 1].type == "goal"


@pytest.mark.parametrize("seed", range(6))
def test_roster_integrity(world: World, seed: int) -> None:
    """Players act only while on the pitch, for their own club; subs within the limit."""
    clubs = {c.team_id: c for c in world.clubs}
    on_pitch = {pid for team in ("LAG", "HCF") for pid in clubs[team].starting_xi}
    subs: Counter[str] = Counter()
    for event in match_events(seed=seed):
        if event.player_id is None:
            continue
        assert event.team_id is not None
        assert event.player_id.startswith(event.team_id + "-")
        assert event.player_id in on_pitch, event
        if event.type == "pass":
            assert event.recipient_id in on_pitch
            assert event.recipient_id.startswith(event.team_id + "-")
        if event.type == "substitution":
            assert event.recipient_id is not None and event.recipient_id not in on_pitch
            on_pitch.remove(event.player_id)
            on_pitch.add(event.recipient_id)
            subs[event.team_id] += 1
        if event.type == "card" and event.card_color in ("red", "second_yellow"):
            on_pitch.remove(event.player_id)
    assert all(n <= 5 for n in subs.values())


def test_second_yellow_only_after_a_yellow() -> None:
    for seed in range(20):
        booked: set[str] = set()
        for event in match_events(seed=seed):
            if event.type == "card" and event.player_id:
                if event.card_color == "second_yellow":
                    assert event.player_id in booked
                booked.add(event.player_id)


def test_expected_goal_probability_shape() -> None:
    penalty_spot = expected_goal_probability(94.0, 34.0)
    six_yards = expected_goal_probability(99.5, 34.0)
    long_range = expected_goal_probability(75.0, 34.0)
    tight_angle = expected_goal_probability(103.0, 60.0)
    assert six_yards > penalty_spot > long_range
    assert 0.1 < penalty_spot < 0.25
    assert long_range < 0.03
    assert tight_angle < penalty_spot
