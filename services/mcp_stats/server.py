"""Match Stats MCP server: the one source of truth agents read numbers from.

Six read-only tools over the Stats Engine (spec: get_match_state, get_team_stats,
get_player_stats, get_events, get_momentum, compare_periods). Each takes the match_id
first because one server serves every live match. Served over Streamable HTTP at /mcp,
stateless, so any replica can answer.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from starlette.applications import Starlette

from contracts import (
    MatchEvent,
    MatchState,
    Momentum,
    PeriodComparison,
    PlayerStats,
    TeamStatsReport,
)
from stats.engine import StatsEngine, Window
from stats.service import StatsRegistry

EventType = Literal[
    "pass", "carry", "shot", "tackle", "interception", "pressure", "foul", "card",
    "substitution", "goal", "possession_change", "out_of_play", "kickoff", "period_end",
]  # fmt: skip

INSTRUCTIONS = """\
Live statistics for Pitchside AI's synthetic football matches. Every number an agent
writes must come from one of these tools. Windows: match, first_half, second_half,
last_5, last_10, last_15 (minutes of playing time). Coordinates are metres on a 105 x 68
pitch, in the acting team's frame (attacking towards x=105). Percentages are 0-100,
speeds km/h, distances km (players) or m (passes), xG 0-1, pass difficulty 0-100,
Control vs Chaos index -100 (chaos) to +100 (control)."""

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
SERVER_NAME = "pitchside-match-stats"


def build_server(registry: StatsRegistry, path: str = "/mcp") -> FastMCP:
    """The server, configured for stateless Streamable HTTP with JSON responses (no session
    affinity needed, so any replica can answer). host 0.0.0.0 leaves Host-header checks to
    the platform's ingress rather than assuming localhost."""
    mcp = FastMCP(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
        host="0.0.0.0",
        streamable_http_path=path,
        stateless_http=True,
        json_response=True,
    )

    async def engine(match_id: str) -> StatsEngine:
        found = await registry.load(match_id)
        if found is None:
            raise ToolError(f"unknown match_id {match_id!r}")
        return found

    @mcp.tool(annotations=READ_ONLY)
    async def get_match_state(match_id: str) -> MatchState:
        """Score, clock, status, possession, goals (with xG and shot speed), cards and the
        current Control vs Chaos index for a match."""
        return (await engine(match_id)).match_state()

    @mcp.tool(annotations=READ_ONLY)
    async def get_team_stats(match_id: str, window: Window = "match") -> TeamStatsReport:
        """Both teams' stats over a window (home first): goals, shots, xG, passes, pass
        accuracy and difficulty, possession, pressures, tackles, PPDA, turnovers,
        distance covered, sprints and top speed."""
        return (await engine(match_id)).team_stats(window)

    @mcp.tool(annotations=READ_ONLY)
    async def get_player_stats(
        match_id: str, player_id: str, window: Window = "match", include_heatmap: bool = False
    ) -> PlayerStats:
        """One player's stats over a window: touches, passes, key passes, pass difficulty,
        shots, goals, xG, shot speed, defensive actions, cards, distance, sprints, top
        speed. player_id looks like 'LAG-09'. The optional heatmap covers the whole match."""
        found = await engine(match_id)
        try:
            stats = found.player_stats(player_id, window)
        except KeyError as exc:
            raise ToolError(f"unknown player_id {player_id!r} in this match") from exc
        return stats if include_heatmap else stats.model_copy(update={"heatmap": None})

    @mcp.tool(annotations=READ_ONLY, structured_output=True)
    async def get_events(
        match_id: str, since: int = -1, types: list[EventType] | None = None, limit: int = 30
    ) -> list[MatchEvent]:
        """Raw match events with seq greater than `since`, optionally only these types,
        newest last; at most `limit` (the most recent ones)."""
        return (await engine(match_id)).events(since, types, max(1, min(limit, 200)))

    @mcp.tool(annotations=READ_ONLY)
    async def get_momentum(match_id: str, window: Window = "last_15") -> Momentum:
        """The Control vs Chaos index (5-minute rolling window, every 30 s of match time)
        inside a window, plus the current value, its 5-minute swing and the dominant team.
        Components: possession stability, turnovers, pressure and tempo, each -1..1."""
        return (await engine(match_id)).momentum(window)

    @mcp.tool(annotations=READ_ONLY)
    async def compare_periods(match_id: str) -> PeriodComparison:
        """First-half and second-half team stats side by side."""
        return (await engine(match_id)).compare_periods()

    return mcp


def http_app(mcp: FastMCP) -> Starlette:
    """The Streamable HTTP app. A host app that mounts its routes must run
    `mcp.session_manager.run()` in its own lifespan (a mounted app's lifespan does not run)."""
    return mcp.streamable_http_app()
