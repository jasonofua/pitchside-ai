from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contracts import MatchEvent, MatchInfo, TrackingFrame, World
from sim.engine import MatchConfig, MatchEngine
from sim.tracking import TrackingGenerator
from sim.world import load_world
from stats import StatsEngine

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


@cache
def validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def as_json(model: MatchEvent | TrackingFrame) -> Any:
    return json.loads(model.model_dump_json(exclude_none=True))


@cache
def match_events(home: str = "LAG", away: str = "HCF", seed: int = 42) -> tuple[MatchEvent, ...]:
    engine = MatchEngine(load_world(), MatchConfig(home=home, away=away, seed=seed))
    return tuple(engine.events())


@cache
def match_with_tracking(seed: int = 42) -> tuple[MatchEvent | TrackingFrame, ...]:
    world = load_world()
    engine = MatchEngine(world, MatchConfig(home="LAG", away="HCF", seed=seed))
    tracker = TrackingGenerator(world, engine.match_id, "LAG", "HCF", seed)
    return tuple(tracker.stream(engine.events()))


def match_info(
    match_id: str, home: str, away: str, seed: int, scenario: str = "default"
) -> MatchInfo:
    return MatchInfo(
        match_id=match_id, home=home, away=away, scenario=scenario, seed=seed, speed=0,
        status="scheduled",
    )  # fmt: skip


@cache
def stats_with_tracking(seed: int = 42) -> tuple[StatsEngine, tuple[Any, ...]]:
    """A StatsEngine fed a full LAG v HCF match with tracking, and every trigger it raised."""
    items = match_with_tracking(seed)
    first = next(i for i in items if isinstance(i, MatchEvent))
    stats = StatsEngine(load_world(), match_info(first.match_id, "LAG", "HCF", seed))
    triggers: list[Any] = []
    for item in items:
        if isinstance(item, MatchEvent):
            triggers.extend(stats.on_event(item))
        else:
            triggers.extend(stats.on_frame(item))
    return stats, tuple(triggers)


@pytest.fixture(scope="session")
def world() -> World:
    return load_world()
