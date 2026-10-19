"""Scenario scripts land their story beats on time, every seed."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest
import yaml

from contracts import MatchEvent, World
from sim.engine import MatchConfig, MatchEngine
from sim.scenario import SCENARIO_DIR, beat_time, load_scenario, scenario_names
from sim.world import load_world

from .conftest import validator

SEEDS = range(1, 11)


@cache
def _run(name: str, seed: int) -> tuple[MatchEvent, ...]:
    scenario = load_scenario(name)
    assert scenario.home and scenario.away
    config = MatchConfig(home=scenario.home, away=scenario.away, seed=seed, scenario=name)
    return tuple(MatchEngine(load_world(), config).events())


def _goals(events: tuple[MatchEvent, ...]) -> list[tuple[str | None, float]]:
    return [(e.team_id, e.clock_ms / 60_000) for e in events if e.type == "goal"]


@pytest.mark.parametrize("path", sorted(SCENARIO_DIR.glob("*.yaml")), ids=lambda p: p.stem)
def test_scenario_files_validate(path: Path) -> None:
    validator("scenario").validate(yaml.safe_load(path.read_text()))
    assert load_scenario(path.stem).name == path.stem


def test_all_four_spec_scenarios_exist() -> None:
    assert set(scenario_names()) >= {
        "default", "comeback", "red_card", "pressing_collapse", "late_winner"
    }  # fmt: skip


def test_unknown_scenario() -> None:
    with pytest.raises(KeyError):
        load_scenario("nope")


@pytest.mark.parametrize(
    ("at", "expected"),
    [("34", (1, 34 * 60_000)), ("71", (2, 71 * 60_000)), ("45+1", (1, 46 * 60_000)),
     ("90+2", (2, 92 * 60_000)), ("45", (2, 45 * 60_000))],
)  # fmt: skip
def test_beat_time(at: str, expected: tuple[int, int]) -> None:
    assert beat_time(at) == expected


def test_stoppage_beat_must_follow_a_half() -> None:
    with pytest.raises(ValueError):
        beat_time("60+1")


@pytest.mark.parametrize("seed", SEEDS)
def test_comeback(seed: int) -> None:
    goals = _goals(_run("comeback", seed))
    assert [team for team, _ in goals] == ["HCF", "HCF", "LAG", "LAG"]
    for (_, minute), target in zip(goals, (17, 52, 71, 88), strict=True):
        assert target - 0.5 <= minute <= target + 7
    at_hour = [team for team, minute in goals if minute < 60]
    assert at_hour == ["HCF", "HCF"]  # trailing 0-2 at 60'


@pytest.mark.parametrize("seed", SEEDS)
def test_late_winner(seed: int) -> None:
    events = _run("late_winner", seed)
    goals = _goals(events)
    assert [team for team, _ in goals] == ["NBR", "KVA", "KVA"]
    winner = next(e for e in reversed(events) if e.type == "goal")
    assert winner.period == 2 and 91.5 <= winner.clock_ms / 60_000 <= 97
    end = events[-1]
    assert end.type == "period_end" and end.clock_ms > winner.clock_ms


@pytest.mark.parametrize("seed", SEEDS)
def test_red_card_lands_at_34(seed: int) -> None:
    reds = [
        e for e in _run("red_card", seed)
        if e.type == "card" and e.card_color == "red" and e.team_id == "NBR"
    ]  # fmt: skip
    assert reds and 34 <= reds[0].clock_ms / 60_000 < 37 and reds[0].period == 1


def test_pressing_collapse_turnovers_spike() -> None:
    """After 65' Northbank give the ball away more often per minute than before it."""
    before = after = 0
    for seed in SEEDS:
        for e in _run("pressing_collapse", seed):
            lost = e.type == "pass" and e.team_id == "NBR" and e.outcome == "incomplete"
            if lost and e.period == 2:
                if e.clock_ms < 65 * 60_000:
                    before += 1
                else:
                    after += 1
    assert after / 25 > 1.15 * before / 20  # per minute: 65-90' vs 45-65'


def test_scenarios_are_deterministic(world: World) -> None:
    def run() -> list[str]:
        config = MatchConfig(home="LAG", away="HCF", seed=3, scenario="comeback")
        return [e.model_dump_json() for e in MatchEngine(world, config).events()]

    assert run() == run()


def test_default_scenario_is_unchanged() -> None:
    """Regression guard for the published dataset (data/matches/lag-hcf-default-s42)."""
    config = MatchConfig(home="LAG", away="HCF", seed=42)
    events = list(MatchEngine(load_world(), config).events())
    assert len(events) == 1905
    assert [g[0] for g in _goals(tuple(events))].count("HCF") == 5
