"""Acceptance check from docs/SPEC.md: realistic match totals over 50 seeded runs."""

from __future__ import annotations

import itertools
import statistics

import pytest

from contracts import World
from sim.engine import MatchConfig, MatchEngine

RUNS = 50


@pytest.mark.slow
def test_average_totals_over_50_seeded_runs(world: World) -> None:
    pairings = list(itertools.permutations([c.team_id for c in world.clubs], 2))
    passes, shots, goals, completion = [], [], [], []
    for seed in range(RUNS):
        home, away = pairings[seed % len(pairings)]
        events = list(MatchEngine(world, MatchConfig(home=home, away=away, seed=seed)).events())
        match_passes = [e for e in events if e.type == "pass"]
        passes.append(len(match_passes))
        shots.append(sum(e.type == "shot" for e in events))
        goals.append(sum(e.type == "goal" for e in events))
        completion.append(sum(e.outcome == "complete" for e in match_passes) / len(match_passes))

    summary = (
        f"passes={statistics.mean(passes):.0f} shots={statistics.mean(shots):.1f} "
        f"goals={statistics.mean(goals):.2f} completion={statistics.mean(completion):.1%}"
    )
    assert 800 <= statistics.mean(passes) <= 1100, summary
    assert 20 <= statistics.mean(shots) <= 30, summary
    assert 2 <= statistics.mean(goals) <= 4, summary
    assert 0.70 <= statistics.mean(completion) <= 0.90, summary
