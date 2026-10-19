"""The seven-agent workflow end to end with the offline mock models and a real MCP server.

The match is fed to the Stats Engine up to the moment of each trigger, so the agents see
the match as it was then (and the Producer does not drop the cards as stale).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

import httpx

from agents import mock_llm
from agents.crew import Crew
from agents.workflow import AgentService
from contracts import MatchEvent, OverlayCard, Profile, Trigger, World
from contracts.agents import AgentTrace
from mcp_stats import build_server, http_app
from runtime.bus import LocalBus, Message
from runtime.config import Settings
from runtime.profiles import DEMO_PROFILES, profile_hash
from runtime.store import SqliteStore
from sim.engine import MatchConfig, MatchEngine
from stats.service import StatsRegistry

from .conftest import match_info

MATCH = "wf-comeback-42"


class Harness:
    def __init__(self, world: World) -> None:
        self.world = world
        self.bus = LocalBus(maxsize=100_000)
        self.store = SqliteStore()
        self.registry = StatsRegistry(world, self.store)
        self.events = list(
            MatchEngine(
                world,
                MatchConfig(home="LAG", away="HCF", seed=42, scenario="comeback", match_id=MATCH),
            ).events()
        )
        self.engine = self.registry.create(match_info(MATCH, "LAG", "HCF", 42, "comeback"))
        self.fed = 0
        self.traces = self.bus.subscribe("trace", "test")
        self.overlays = self.bus.subscribe("overlays", "test")

    def feed_until(self, kind: str, nth: int = 1) -> Trigger:
        """Feed events until the nth trigger of `kind` fires; return it."""
        seen = 0
        while self.fed < len(self.events):
            event: MatchEvent = self.events[self.fed]
            self.fed += 1
            for trig in self.engine.on_event(event):
                if trig.kind == kind:
                    seen += 1
                    if seen == nth:
                        return trig
        raise AssertionError(f"no {kind} trigger #{nth}")

    async def drain(self, sub: Any) -> list[dict[str, Any]]:
        out = []
        while True:
            try:
                msg: Message = await asyncio.wait_for(anext(sub), 0.05)
            except TimeoutError:
                return out
            out.append(msg.data)


def with_crew(
    world: World,
    profiles: list[Profile],
    fn: Callable[[Harness, AgentService], Awaitable[Any]],
) -> Any:
    async def main() -> Any:
        h = Harness(world)
        mcp = build_server(h.registry)
        app = http_app(mcp)
        settings = replace(
            Settings.from_env(), llm="mock", mcp_url="http://mcp.test/mcp", model_timeout_s=5.0
        )
        async with mcp.session_manager.run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as http:
                crew = Crew(settings, h.bus, h.store, http_client=http)
                await crew.start()
                service = AgentService(crew)
                service.on_control({
                    "type": "profiles", "match_id": MATCH,
                    "profiles": [{"hash": profile_hash(p),
                                  "profile": p.model_dump(exclude_none=True)} for p in profiles],
                })  # fmt: skip
                try:
                    return await fn(h, service)
                finally:
                    await crew.close()

    return asyncio.run(main())


def test_goal_flows_through_all_seven_agents(world: World) -> None:
    profiles = list(DEMO_PROFILES)

    async def fn(h: Harness, service: AgentService) -> tuple[list[OverlayCard], list[AgentTrace]]:
        trig = h.feed_until("goal")
        cards = await service.handle(trig)
        traces = [AgentTrace.model_validate(t) for t in await h.drain(h.traces)]
        published = [OverlayCard.model_validate(o) for o in await h.drain(h.overlays)]
        assert {c.overlay_id for c in cards} <= {p.overlay_id for p in published}
        return published, traces

    published, traces = with_crew(world, profiles, fn)
    agents = {t.agent for t in traces}
    assert agents == {"moment_detector", "tactical_analyst", "narrator", "fan_lens",
                      "localizer", "fact_checker", "producer"}  # fmt: skip
    hashes = {profile_hash(p): p for p in profiles}
    # Each viewer gets the instant stats-only card and then the agents' card, same overlay id.
    for h_, profile in hashes.items():
        mine = [c for c in published if c.audience_profile_hash == h_]
        sources = [c.source for c in mine]
        assert sources[0] == "template" and "agent" in sources
        assert len({c.overlay_id for c in mine}) == 1
        assert all(c.lang == profile.language for c in mine)
    assert all(t.trace_id == traces[0].trace_id for t in traces)
    assert not [t for t in traces if t.status in ("error", "rejected", "fallback")]
    analyst = next(t for t in traces if t.agent == "tactical_analyst")
    assert "get_team_stats" in (analyst.tools or [])


def test_chaos_switch_kills_the_narrator_but_cards_keep_coming(world: World) -> None:
    profile = DEMO_PROFILES[1]

    async def fn(h: Harness, service: AgentService) -> tuple[list[OverlayCard], list[AgentTrace]]:
        service.on_control({"type": "chaos", "agent": "narrator", "seconds": 60})
        trig = h.feed_until("goal")
        await service.handle(trig)
        traces = [AgentTrace.model_validate(t) for t in await h.drain(h.traces)]
        cards = [OverlayCard.model_validate(o) for o in await h.drain(h.overlays)]
        return cards, traces

    cards, traces = with_crew(world, [profile], fn)
    narrator = [t for t in traces if t.agent == "narrator"]
    assert narrator and narrator[0].status == "circuit_open"
    assert cards and cards[0].source == "template"  # the screen never goes blank
    assert any(c.source == "agent" for c in cards)  # the insight still reaches the viewer


def test_fact_checker_catches_an_injected_wrong_number(world: World) -> None:
    profile = DEMO_PROFILES[0]

    async def fn(h: Harness, service: AgentService) -> tuple[list[OverlayCard], list[AgentTrace]]:
        service.on_control({"type": "fault", "kind": "wrong_number", "count": 1})
        trig = h.feed_until("goal")
        await service.handle(trig)
        traces = [AgentTrace.model_validate(t) for t in await h.drain(h.traces)]
        cards = [OverlayCard.model_validate(o) for o in await h.drain(h.overlays)]
        return cards, traces

    cards, traces = with_crew(world, [profile], fn)
    checks = [t.status for t in traces if t.agent == "fact_checker"]
    assert "rejected" in checks and "regenerated" in checks
    final = [c for c in cards if c.source == "agent"]
    assert final  # the regenerated card made it


def test_a_failing_agent_falls_back_and_opens_its_breaker(world: World, monkeypatch: Any) -> None:
    def broken(req: dict[str, Any], res: Any) -> Any:
        raise RuntimeError("model unavailable")

    monkeypatch.setitem(mock_llm.BRAINS, "fan_lens", broken)
    profile = DEMO_PROFILES[1]

    async def fn(h: Harness, service: AgentService) -> list[AgentTrace]:
        for _ in range(4):  # the comeback has four goals
            await service.handle(h.feed_until("goal"))
        return [AgentTrace.model_validate(t) for t in await h.drain(h.traces)]

    traces = with_crew(world, [profile], fn)
    fan = [t.status for t in traces if t.agent == "fan_lens"]
    assert fan == ["error", "error", "error", "circuit_open"]


def test_nobody_watching_skips_low_value_triggers(world: World) -> None:
    async def fn(h: Harness, service: AgentService) -> tuple[int, int]:
        tick = h.feed_until("tick")
        await service.handle(tick)
        return service.runs, service.skipped

    runs, skipped = with_crew(world, [], fn)
    assert (runs, skipped) == (0, 1)
