"""How the gateway reads stats: in-process (local mode, and the stats app itself) or over
HTTP from the stats app (Azure mode, where the gateway is a separate Container App)."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from stats.engine import StatsEngine, Window
from stats.service import StatsRegistry


class StatsUnavailableError(Exception):
    """The match is unknown to the stats service."""


class StatsReader(Protocol):
    async def state(self, match_id: str) -> dict[str, Any]: ...
    async def team_stats(self, match_id: str, window: Window) -> dict[str, Any]: ...
    async def player(self, match_id: str, player_id: str, window: Window) -> dict[str, Any]: ...
    async def momentum(self, match_id: str, window: Window) -> dict[str, Any]: ...
    async def events(
        self, match_id: str, since: int, types: list[str] | None, limit: int
    ) -> list[dict[str, Any]]: ...
    async def compare(self, match_id: str) -> dict[str, Any]: ...
    async def analyst(self, match_id: str) -> dict[str, Any]: ...


class LocalStatsReader:
    def __init__(self, registry: StatsRegistry) -> None:
        self.registry = registry

    async def _engine(self, match_id: str) -> StatsEngine:
        engine = await self.registry.load(match_id)
        if engine is None:
            raise StatsUnavailableError(match_id)
        return engine

    async def state(self, match_id: str) -> dict[str, Any]:
        return (await self._engine(match_id)).match_state().model_dump(mode="json")

    async def team_stats(self, match_id: str, window: Window) -> dict[str, Any]:
        return (await self._engine(match_id)).team_stats(window).model_dump(mode="json")

    async def player(self, match_id: str, player_id: str, window: Window) -> dict[str, Any]:
        engine = await self._engine(match_id)
        try:
            return engine.player_stats(player_id, window).model_dump(mode="json")
        except KeyError as exc:
            raise StatsUnavailableError(player_id) from exc

    async def momentum(self, match_id: str, window: Window) -> dict[str, Any]:
        return (await self._engine(match_id)).momentum(window).model_dump(mode="json")

    async def events(
        self, match_id: str, since: int, types: list[str] | None, limit: int
    ) -> list[dict[str, Any]]:
        engine = await self._engine(match_id)
        return [
            e.model_dump(mode="json", exclude_none=True) for e in engine.events(since, types, limit)
        ]

    async def compare(self, match_id: str) -> dict[str, Any]:
        return (await self._engine(match_id)).compare_periods().model_dump(mode="json")

    async def analyst(self, match_id: str) -> dict[str, Any]:
        return (await self._engine(match_id)).analyst_report().model_dump(mode="json")


class RemoteStatsReader:
    """Calls the stats app's own REST routes (the same router, served in-process there)."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.base = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=5.0)

    async def _get(self, path: str, **params: Any) -> Any:
        r = await self.client.get(f"{self.base}{path}", params={k: v for k, v in params.items()
                                                                  if v is not None})  # fmt: skip
        if r.status_code == 404:
            raise StatsUnavailableError(path)
        r.raise_for_status()
        return r.json()

    async def state(self, match_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self._get(f"/api/matches/{match_id}/state")
        return result

    async def team_stats(self, match_id: str, window: Window) -> dict[str, Any]:
        result: dict[str, Any] = await self._get(f"/api/matches/{match_id}/stats", window=window)
        return result

    async def player(self, match_id: str, player_id: str, window: Window) -> dict[str, Any]:
        result: dict[str, Any] = await self._get(
            f"/api/matches/{match_id}/players/{player_id}", window=window
        )
        return result

    async def momentum(self, match_id: str, window: Window) -> dict[str, Any]:
        result: dict[str, Any] = await self._get(f"/api/matches/{match_id}/momentum", window=window)
        return result

    async def events(
        self, match_id: str, since: int, types: list[str] | None, limit: int
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await self._get(
            f"/api/matches/{match_id}/events", since=since,
            types=",".join(types) if types else None, limit=limit,
        )  # fmt: skip
        return result

    async def compare(self, match_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self._get(f"/api/matches/{match_id}/compare")
        return result

    async def analyst(self, match_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self._get(f"/api/matches/{match_id}/analyst")
        return result
