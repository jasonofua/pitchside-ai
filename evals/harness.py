"""Replays eval moments through the real agent crew and Match Stats MCP server.

Each sample's match is played into a Stats Engine up to its trigger; the crew (with the
configured models: offline mock unless FOUNDRY_ENDPOINT or OPENAI_COMPAT_BASE_URL is set)
then runs the whole workflow for that trigger for five viewer profiles covering every mode
and language. Everything the crew publishes is captured for scoring.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, replace
from typing import Any

import httpx

from agents.crew import Crew
from agents.numbers import Facts
from agents.stats_client import StatsClient
from agents.workflow import AgentService
from contracts import OverlayCard, Profile, Trigger
from contracts.agents import AgentTrace
from evals.dataset import Sample, play
from mcp_stats import build_server, http_app
from runtime.bus import LocalBus, Message
from runtime.config import Settings
from runtime.profiles import profile_hash
from runtime.store import SqliteStore
from sim.world import load_world
from stats.service import StatsRegistry


def profiles_for(sample: Sample) -> tuple[Profile, ...]:
    """Five viewers covering every mode and language: home fans, an away fan, neutrals."""
    home, away = sample.home, sample.away
    return (
        Profile(mode="analyst", language="en", focus_metric="xg"),
        Profile(mode="casual", language="pcm", favorite_club=home, focus_metric="possession"),
        Profile(
            mode="player_cam",
            language="yo",
            favorite_club=home,
            favorite_player=f"{home}-09",
            focus_metric="top_speed",
        ),
        Profile(mode="kids", language="fr", focus_metric="shot_speed"),
        Profile(mode="casual", language="es", favorite_club=away, focus_metric="xg"),
    )


@dataclass
class Outcome:
    sample: Sample
    trigger: Trigger
    traces: list[AgentTrace]
    overlays: list[OverlayCard]
    moments: list[dict[str, Any]]
    insights: list[dict[str, Any]]
    commentary: list[dict[str, Any]]
    facts: Facts
    names: dict[str, str]  # player id -> short name, for Player Cam checks
    seconds: float
    first_overlay_s: float | None
    profiles: dict[str, Profile] = field(default_factory=dict)

    def traces_for(self, agent: str) -> list[AgentTrace]:
        return [t for t in self.traces if t.agent == agent]


async def _drain(sub: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while True:
        try:
            msg: Message = await asyncio.wait_for(anext(sub), 0.05)
        except TimeoutError:
            return out
        out.append(msg.data)


class EvalHarness:
    def __init__(self, settings: Settings | None = None) -> None:
        base = settings or Settings.from_env()
        self.settings = replace(base, mcp_url="http://mcp.eval/mcp")
        self.world = load_world()
        self.bus = LocalBus(maxsize=200_000)
        self.store = SqliteStore()
        self.registry = StatsRegistry(self.world, self.store)
        self.mcp = build_server(self.registry)
        self.app = http_app(self.mcp)
        self.names = {p.player_id: p.short_name for c in self.world.clubs for p in c.players}

    async def __aenter__(self) -> EvalHarness:
        self._session = self.mcp.session_manager.run()
        await self._session.__aenter__()
        transport = httpx.ASGITransport(app=self.app)
        self.http = httpx.AsyncClient(transport=transport, base_url="http://mcp.eval")
        self.crew = Crew(self.settings, self.bus, self.store, http_client=self.http)
        await self.crew.start()
        self.service = AgentService(self.crew)
        self.stats = StatsClient(self.settings.mcp_url, http_client=self.http)
        await self.stats.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stats.close()
        await self.crew.close()
        await self.http.aclose()
        await self._session.__aexit__(None, None, None)

    async def run(self, sample: Sample) -> Outcome:
        engine, trigger = await asyncio.to_thread(play, sample)
        if not isinstance(trigger, Trigger):
            raise ValueError(f"{sample.sample_id}: trigger not found")
        self.registry.put(engine)
        profiles = {profile_hash(p): p for p in profiles_for(sample)}
        self.service.on_control({
            "type": "profiles", "match_id": sample.match_id,
            "profiles": [{"hash": h, "profile": p.model_dump(exclude_none=True)}
                         for h, p in profiles.items()],
        })  # fmt: skip
        traces_sub = self.bus.subscribe("trace", f"eval-{sample.sample_id}")
        overlays_sub = self.bus.subscribe("overlays", f"eval-{sample.sample_id}")
        first: list[float] = []
        started = time.monotonic()

        async def watch_first() -> None:
            q = self.bus.queue("overlays", f"first-{sample.sample_id}")
            await q.get()
            first.append(time.monotonic() - started)

        watcher = asyncio.create_task(watch_first())
        await self.service.handle(trigger)
        seconds = time.monotonic() - started
        watcher.cancel()
        traces = [AgentTrace.model_validate(t) for t in await _drain(traces_sub)]
        overlays = [OverlayCard.model_validate(o) for o in await _drain(overlays_sub)]
        payloads = [
            await self.stats.call(tool, match_id=sample.match_id, **args)
            for tool, args in (
                ("get_match_state", {}),
                ("get_team_stats", {"window": "match"}),
                ("get_team_stats", {"window": "last_5"}),
                ("get_team_stats", {"window": "last_10"}),
                ("get_team_stats", {"window": "last_15"}),
                ("compare_periods", {}),
                ("get_momentum", {"window": "last_15"}),
                ("get_player_stats", {"player_id": f"{sample.home}-09"}),
                ("get_events", {"since": max(trigger.seq - 4, -1), "limit": 6}),
            )
        ]
        if trigger.player_id:
            payloads.append(await self.stats.call("get_player_stats", match_id=sample.match_id,
                                                  player_id=trigger.player_id))  # fmt: skip
        payloads.append(trigger.model_dump(mode="json", exclude_none=True))
        return Outcome(
            sample=sample,
            trigger=trigger,
            traces=traces,
            overlays=overlays,
            moments=await self.store.docs("moment", sample.match_id),
            insights=await self.store.docs("insight", sample.match_id),
            commentary=await self.store.docs("commentary", sample.match_id),
            facts=Facts.from_payloads(payloads),
            names=self.names,
            seconds=seconds,
            first_overlay_s=first[0] if first else None,
            profiles=profiles,
        )
