"""A direct MCP client for the agents' code paths (template cards, fact-check facts).

Model-driven agents reach the same server through Agent Framework's MCPStreamableHTTPTool;
code that needs numbers without a model uses this client, so every number the agents
service handles comes through the Match Stats MCP server.
"""

from __future__ import annotations

import json
import logging
from contextlib import AsyncExitStack
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

log = logging.getLogger(__name__)


class StatsToolError(Exception):
    """The MCP tool reported an error (unknown match, unknown player, bad arguments)."""


class StatsClient:
    def __init__(self, url: str, http_client: httpx.AsyncClient | None = None) -> None:
        self.url = url
        self._http = http_client
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> StatsClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def connect(self) -> None:
        if self._session is not None:
            return
        stack = AsyncExitStack()
        http = self._http or httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0))
        if self._http is None:
            await stack.enter_async_context(http)
        read, write, _ = await stack.enter_async_context(
            streamable_http_client(self.url, http_client=http)
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._stack, self._session = stack, session

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack, self._session = None, None

    async def call(self, tool: str, **args: Any) -> Any:
        """Call a tool and return its structured result (unwrapping list results)."""
        if self._session is None:
            await self.connect()
        assert self._session is not None
        try:
            result = await self._session.call_tool(tool, {k: v for k, v in args.items()
                                                          if v is not None})  # fmt: skip
        except Exception:
            # A dropped connection: reconnect once and retry.
            await self.close()
            await self.connect()
            assert self._session is not None
            result = await self._session.call_tool(tool, args)
        if result.isError:
            text = " ".join(getattr(c, "text", "") for c in result.content)
            raise StatsToolError(f"{tool}: {text}")
        data = result.structuredContent
        if data is None:
            text = "".join(getattr(c, "text", "") for c in result.content)
            data = json.loads(text) if text else None
        if isinstance(data, dict) and set(data) == {"result"}:
            return data["result"]
        return data
