"""Simulator service: starts matches on request and streams them onto the bus.

The gateway publishes {"type": "start_match", ...} or {"type": "stop_match", ...} on the
`control` topic; this service runs each match with sim.live.run_live. In local mode it
runs in the gateway process; in Azure it is its own Container App.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

from contracts import MatchInfo, World
from runtime.bus import Bus
from runtime.store import Store
from sim.engine import MatchConfig
from sim.live import new_match_info, run_live

log = logging.getLogger(__name__)

MAX_LIVE_MATCHES = 3
SPEEDS = (1.0, 5.0, 20.0)


def fresh_match_id(home: str, away: str, scenario: str, seed: int) -> str:
    """Live runs get a unique id so their event ids never collide with earlier runs."""
    token = secrets.token_hex(3)
    return f"{home}-{away}-{scenario}-s{seed}-{token}".lower()


class SimService:
    def __init__(self, world: World, bus: Bus, store: Store, halftime_s: float = 10.0) -> None:
        self.world = world
        self.bus = bus
        self.store = store
        self.halftime_s = halftime_s
        self.tasks: dict[str, asyncio.Task[MatchInfo]] = {}

    def live(self) -> list[str]:
        return [m for m, t in self.tasks.items() if not t.done()]

    async def start(self, cmd: dict[str, Any]) -> MatchInfo | None:
        if len(self.live()) >= MAX_LIVE_MATCHES:
            log.warning("refusing match start: %d already live", len(self.live()))
            return None
        config = MatchConfig(
            home=cmd["home"], away=cmd["away"], seed=int(cmd["seed"]),
            scenario=cmd.get("scenario", "default"), match_id=cmd["match_id"],
        )  # fmt: skip
        info = new_match_info(config, float(cmd.get("speed", 5.0)))
        await self.store.put_match(info)
        task = asyncio.create_task(
            run_live(
                self.world,
                config,
                self.bus,
                speed=info.speed,
                halftime_s=self.halftime_s,
                info=info,
            )
        )
        self.tasks[info.match_id] = task
        task.add_done_callback(lambda _t: log.info("match %s finished", info.match_id))
        return info

    async def stop(self, match_id: str) -> bool:
        task = self.tasks.get(match_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def run(self) -> None:
        async for msg in self.bus.subscribe("control", "sim"):
            kind = msg.data.get("type")
            try:
                if kind == "start_match":
                    await self.start(msg.data)
                elif kind == "stop_match":
                    await self.stop(msg.data["match_id"])
            except Exception:
                log.exception("sim failed on a control message")
