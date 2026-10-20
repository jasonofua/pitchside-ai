"""Stats service: keeps a StatsEngine per live match, fed from the bus.

Consumes `matches`, `accepted` (validated events) and `tracking`; publishes `triggers` and
throttled `stats` snapshots. The StatsRegistry is shared in-process with the Match Stats
MCP server, which is how agents read the numbers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable

from contracts import MatchEvent, MatchInfo, TrackingFrame, World
from runtime.bus import Bus, Message
from runtime.store import Store
from stats.engine import StatsEngine

log = logging.getLogger(__name__)

SNAPSHOT_MIN_INTERVAL_S = 0.5
URGENT = frozenset({"goal", "card", "shot", "kickoff", "period_end", "substitution"})


class StatsRegistry:
    """Live StatsEngines by match id. Rebuilds an engine from the event log on demand."""

    def __init__(self, world: World, store: Store) -> None:
        self.world = world
        self.store = store
        self._engines: dict[str, StatsEngine] = {}
        self._lock = asyncio.Lock()

    def get(self, match_id: str) -> StatsEngine | None:
        return self._engines.get(match_id)

    def create(self, info: MatchInfo) -> StatsEngine:
        engine = self._engines.get(info.match_id)
        if engine is None:
            engine = self._engines[info.match_id] = StatsEngine(self.world, info)
        else:
            engine.info = info
        return engine

    async def load(self, match_id: str) -> StatsEngine | None:
        """The engine for a match, replaying the stored event log if it is not in memory.

        A rebuilt engine has every event-derived number; tracking-derived ones (distance,
        speed) start from zero because frames are not persisted, and pass difficulty uses
        its events-only estimate.
        """
        engine = self._engines.get(match_id)
        if engine is not None:
            return engine
        async with self._lock:
            if match_id in self._engines:
                return self._engines[match_id]
            info = await self.store.get_match(match_id)
            if info is None:
                return None
            engine = self.create(info)
            for event in await self.store.events(match_id):
                engine.on_event(event)
            return engine

    def put(self, engine: StatsEngine) -> None:
        """Register an engine built elsewhere (evals replay matches up to a moment)."""
        self._engines[engine.match_id] = engine

    def match_ids(self) -> list[str]:
        return list(self._engines)

    def drop(self, match_id: str) -> None:
        self._engines.pop(match_id, None)


class StatsService:
    def __init__(
        self,
        registry: StatsRegistry,
        bus: Bus,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = registry
        self.bus = bus
        self._clock = clock
        self._last_snapshot: dict[str, float] = {}

    async def _engine(self, match_id: str) -> StatsEngine | None:
        engine = self.registry.get(match_id)
        if engine is None:
            engine = await self.registry.load(match_id)
        return engine

    async def on_match(self, info: MatchInfo) -> None:
        self.registry.create(info)

    async def on_event(self, event: MatchEvent) -> None:
        engine = await self._engine(event.match_id)
        if engine is None:
            log.warning("event for unknown match %s", event.match_id)
            return
        for trigger in engine.on_event(event):
            await self.bus.publish("triggers", event.match_id, trigger)
        now = self._clock()
        last = self._last_snapshot.get(event.match_id, float("-inf"))
        if event.type in URGENT or now - last >= SNAPSHOT_MIN_INTERVAL_S:
            self._last_snapshot[event.match_id] = now
            await self.bus.publish("stats", event.match_id, engine.snapshot())

    async def on_frame(self, frame: TrackingFrame) -> None:
        engine = self.registry.get(frame.match_id)
        if engine is None:
            return
        for trigger in engine.on_frame(frame):
            await self.bus.publish("triggers", frame.match_id, trigger)

    async def _consume_matches(self, messages: AsyncIterator[Message]) -> None:
        async for msg in messages:
            await self.on_match(MatchInfo.model_validate(msg.data))

    async def _consume_events(self, messages: AsyncIterator[Message]) -> None:
        async for msg in messages:
            try:
                await self.on_event(MatchEvent.model_validate(msg.data))
            except Exception:
                log.exception("stats failed on an event")

    async def _consume_tracking(self, messages: AsyncIterator[Message]) -> None:
        async for msg in messages:
            try:
                await self.on_frame(TrackingFrame.model_validate(msg.data))
            except Exception:
                log.exception("stats failed on a frame")

    async def run(self) -> None:
        # Subscribe before the first await so nothing published after start() is missed.
        matches = self.bus.subscribe("matches", "stats")
        events = self.bus.subscribe("accepted", "stats")
        frames = self.bus.subscribe("tracking", "stats")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._consume_matches(matches))
            tg.create_task(self._consume_events(events))
            tg.create_task(self._consume_tracking(frames))
