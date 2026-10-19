"""Run one simulated match: engine -> (tracking) -> pacing -> sink."""

from __future__ import annotations

from collections.abc import Collection, Iterator

from contracts import MatchEvent, TrackingFrame, World
from sim.engine import MatchConfig, MatchEngine
from sim.pacing import Pacer
from sim.sinks import Sink, Topic
from sim.tracking import TrackingGenerator


def match_stream(
    world: World, config: MatchConfig, topics: Collection[Topic]
) -> Iterator[tuple[Topic, MatchEvent | TrackingFrame]]:
    """Yield (topic, item) pairs in match-clock order for the requested topics."""
    engine = MatchEngine(world, config)
    items: Iterator[MatchEvent | TrackingFrame]
    if "tracking" in topics:
        tracker = TrackingGenerator(world, engine.match_id, config.home, config.away, config.seed)
        items = tracker.stream(engine.events())
    else:
        items = engine.events()
    for item in items:
        if isinstance(item, MatchEvent):
            if "events" in topics:
                yield "events", item
        else:
            yield "tracking", item


def run_match(
    world: World,
    config: MatchConfig,
    sink: Sink,
    *,
    speed: float,
    topics: Collection[Topic],
    halftime_s: float = 10.0,
) -> None:
    pacer = Pacer(speed, halftime_s)
    try:
        for topic, item in match_stream(world, config, topics):
            pacer.wait(item.period, item.clock_ms)
            sink.emit(topic, item)
    finally:
        sink.close()
