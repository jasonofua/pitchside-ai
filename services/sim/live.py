"""Run a simulated match onto the message bus, paced by the match clock (asyncio)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from contracts import MatchEvent, MatchInfo, World
from runtime.bus import Bus
from sim.engine import MatchConfig
from sim.pacing import Pacer
from sim.runner import match_stream

log = logging.getLogger(__name__)

YIELD_EVERY = 50  # unpaced runs hand the event loop back this often


def new_match_info(config: MatchConfig, speed: float) -> MatchInfo:
    return MatchInfo(
        match_id=config.resolved_match_id(),
        home=config.home,
        away=config.away,
        scenario=config.scenario,
        seed=config.seed,
        speed=speed,
        status="scheduled",
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


async def run_live(
    world: World,
    config: MatchConfig,
    bus: Bus,
    *,
    speed: float,
    halftime_s: float = 10.0,
    info: MatchInfo | None = None,
) -> MatchInfo:
    """Publish MatchInfo, then every event and tracking frame of the match in clock order.

    Status changes (live, half_time, full_time) are republished on the `matches` topic.
    Cancelling the task marks the match aborted.
    """
    info = info or new_match_info(config, speed)
    match_id = info.match_id
    await bus.publish("matches", match_id, info.model_copy(update={"status": "live"}))
    pacer = Pacer(speed, halftime_s)
    n = 0
    status = "live"
    try:
        for topic, item in match_stream(world, config, ("events", "tracking")):
            delay = pacer.delay(item.period, item.clock_ms)
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                n += 1
                if n % YIELD_EVERY == 0:
                    await asyncio.sleep(0)
            await bus.publish(topic, match_id, item)
            if isinstance(item, MatchEvent) and item.type == "period_end":
                status = "half_time" if item.period == 1 else "full_time"
                await bus.publish("matches", match_id, info.model_copy(update={"status": status}))
    except asyncio.CancelledError:
        status = "aborted"
        await bus.publish("matches", match_id, info.model_copy(update={"status": status}))
        raise
    return info.model_copy(update={"status": status})
