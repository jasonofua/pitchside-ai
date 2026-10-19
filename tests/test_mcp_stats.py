"""The Match Stats MCP server, called by a real MCP client over Streamable HTTP."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from agents.stats_client import StatsClient, StatsToolError
from contracts import MatchEvent, World
from mcp_stats import build_server, http_app
from runtime.store import SqliteStore
from stats.service import StatsRegistry

from .conftest import match_events, match_info

SPEC_TOOLS = {
    "get_match_state", "get_team_stats", "get_player_stats", "get_events", "get_momentum",
    "compare_periods",
}  # fmt: skip


def with_client(
    world: World,
    fn: Callable[[StatsClient, StatsRegistry], Awaitable[Any]],
    *,
    store_only: bool = False,
) -> Any:
    async def main() -> Any:
        store = SqliteStore()
        registry = StatsRegistry(world, store)
        events = match_events()
        info = match_info(events[0].match_id, "LAG", "HCF", 42)
        if store_only:  # not in memory: the server must rebuild it from the event log
            await store.put_match(info)
            for e in events:
                await store.append_event(e)
        else:
            engine = registry.create(info)
            for e in events:
                engine.on_event(e)
        mcp = build_server(registry)
        app = http_app(mcp)
        async with mcp.session_manager.run():
            transport = httpx.ASGITransport(app=app)
            async with (
                httpx.AsyncClient(transport=transport, base_url="http://mcp") as http,
                StatsClient("http://mcp/mcp", http_client=http) as client,
            ):
                return await fn(client, registry)

    return asyncio.run(main())


def test_exposes_exactly_the_six_spec_tools(world: World) -> None:
    async def fn(client: StatsClient, _: StatsRegistry) -> set[str]:
        assert client._session is not None
        listed = await client._session.list_tools()
        assert all(t.annotations and t.annotations.readOnlyHint for t in listed.tools)
        return {t.name for t in listed.tools}

    assert with_client(world, fn) == SPEC_TOOLS


def test_tool_results_match_the_stats_engine(world: World) -> None:
    async def fn(client: StatsClient, registry: StatsRegistry) -> None:
        mid = match_events()[0].match_id
        engine = registry.get(mid)
        assert engine is not None
        state = await client.call("get_match_state", match_id=mid)
        assert state == engine.match_state().model_dump(mode="json")
        report = await client.call("get_team_stats", match_id=mid, window="last_10")
        assert report == engine.team_stats("last_10").model_dump(mode="json")
        player = await client.call("get_player_stats", match_id=mid, player_id="LAG-09")
        assert player["goals"] == engine.player_stats("LAG-09").goals
        assert player["heatmap"] is None
        with_heat = await client.call(
            "get_player_stats", match_id=mid, player_id="LAG-09", include_heatmap=True
        )
        assert with_heat["heatmap"]["cols"] == 12
        momentum = await client.call("get_momentum", match_id=mid, window="last_5")
        assert momentum["now"] == engine.momentum_now().model_dump(mode="json")
        halves = await client.call("compare_periods", match_id=mid)
        assert len(halves["first_half"]) == len(halves["second_half"]) == 2

    with_client(world, fn)


def test_get_events_filters_and_limits(world: World) -> None:
    async def fn(client: StatsClient, _: StatsRegistry) -> list[MatchEvent]:
        mid = match_events()[0].match_id
        raw = await client.call("get_events", match_id=mid, since=100, types=["shot"], limit=5)
        return [MatchEvent.model_validate(e) for e in raw]

    shots = with_client(world, fn)
    assert 0 < len(shots) <= 5
    assert all(e.type == "shot" and e.seq > 100 for e in shots)


def test_errors_are_tool_errors(world: World) -> None:
    async def fn(client: StatsClient, _: StatsRegistry) -> None:
        with pytest.raises(StatsToolError, match="unknown match_id"):
            await client.call("get_match_state", match_id="nope")
        mid = match_events()[0].match_id
        with pytest.raises(StatsToolError, match="unknown player_id"):
            await client.call("get_player_stats", match_id=mid, player_id="XXX-01")

    with_client(world, fn)


def test_rebuilds_a_match_from_the_event_log(world: World) -> None:
    async def fn(client: StatsClient, _: StatsRegistry) -> dict[str, Any]:
        result: dict[str, Any] = await client.call(
            "get_match_state", match_id=match_events()[0].match_id
        )
        return result

    state = with_client(world, fn, store_only=True)
    goals = [e for e in match_events() if e.type == "goal"]
    assert len(state["goals"]) == len(goals)
    assert state["status"] == "full_time"
