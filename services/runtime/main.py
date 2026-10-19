"""Process entry point: `python -m runtime.main --role all` (local) or one role per
Container App in Azure (gateway, sim, ingestor, stats, agents).

Local mode (`--role all`, the default) runs every service in one process over the
in-process bus and SQLite, serves the Match Stats MCP server at /mcp and the web app at /,
and needs no Azure account and no model (the offline mock is used unless FOUNDRY_ENDPOINT
or OPENAI_COMPAT_BASE_URL is set).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from fastapi import FastAPI

from gateway.app import create_app
from gateway.hub import Hub
from gateway.readers import LocalStatsReader, RemoteStatsReader, StatsReader
from ingestor import Ingestor
from runtime.bus import Bus, LocalBus
from runtime.config import Settings
from runtime.store import SqliteStore, Store
from sim.service import SimService
from sim.world import load_world
from stats.service import StatsRegistry, StatsService

log = logging.getLogger("pitchside")

ROLES = ("all", "gateway", "sim", "ingestor", "stats", "agents")


def configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("PITCHSIDE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("httpx", "mcp", "mcp.server", "mcp.client", "agent_framework", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def make_bus(settings: Settings) -> Bus:
    if settings.mode == "azure":
        from runtime.eventhubs import EventHubsBus

        return EventHubsBus(settings.eventhubs_namespace)
    return LocalBus()


def make_store(settings: Settings) -> Store:
    if settings.mode == "azure":
        from runtime.cosmos import CosmosStore

        return CosmosStore(settings.cosmos_endpoint, settings.cosmos_database)
    return SqliteStore(settings.data_dir / "pitchside.sqlite")


def setup_telemetry(settings: Settings) -> None:
    if settings.appinsights_connection_string:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=settings.appinsights_connection_string,
            logger_name="pitchside",
        )
        from agent_framework.observability import enable_instrumentation

        enable_instrumentation()


def build(role: str, settings: Settings | None = None) -> FastAPI:
    """Assemble the services for one role into a FastAPI app whose lifespan runs them."""
    settings = settings or Settings.from_env()
    world = load_world()
    bus = make_bus(settings)
    store = make_store(settings)
    runs_stats = role in ("all", "stats")
    registry = StatsRegistry(world, store) if runs_stats else None
    reader: StatsReader
    if registry is not None:
        reader = LocalStatsReader(registry)
    else:
        reader = RemoteStatsReader(os.environ.get("PITCHSIDE_STATS_URL", "http://stats"))

    hub: Hub | None = None
    if role in ("all", "gateway"):
        if settings.webpubsub_endpoint:
            from gateway.webpubsub import WebPubSubHub

            hub = WebPubSubHub(bus, settings)
        else:
            hub = Hub(bus)

    mcp = None
    extra_routes: list[Any] = []
    if registry is not None:
        from mcp_stats import build_server, http_app

        mcp = build_server(registry)
        extra_routes = list(http_app(mcp).routes)

    agent_service: Any = None

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal agent_service
        setup_telemetry(settings)
        tasks: list[asyncio.Task[Any]] = []
        async with contextlib.AsyncExitStack() as stack:
            if mcp is not None:
                await stack.enter_async_context(mcp.session_manager.run())
            if hasattr(bus, "start"):
                await bus.start()
            if role in ("all", "ingestor"):
                tasks.append(asyncio.create_task(Ingestor(store, bus).run(), name="ingestor"))
            if registry is not None:
                tasks.append(asyncio.create_task(StatsService(registry, bus).run(), name="stats"))
            if role in ("all", "sim"):
                tasks.append(asyncio.create_task(SimService(world, bus, store).run(), name="sim"))
            if hub is not None:
                tasks.append(asyncio.create_task(hub.run(), name="hub"))
            if role in ("all", "agents"):
                from agents.crew import Crew
                from agents.workflow import AgentService

                crew = Crew(settings, bus, store)
                agent_service = AgentService(crew)
                tasks.append(asyncio.create_task(agent_service.run(), name="agents"))
                # The crew connects to the MCP server, which this same process may be serving:
                # connect once the server is accepting requests.
                tasks.append(asyncio.create_task(_start_crew(crew), name="crew"))
                stack.push_async_callback(crew.close)
            log.info("pitchside %s up (mode=%s, llm=%s)", role, settings.mode, settings.llm)
            try:
                yield
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await bus.close()
                await store.close()

    return create_app(
        settings=settings,
        world=world,
        bus=bus,
        store=store,
        reader=reader,
        hub=hub,
        extra_routes=extra_routes,
        lifespan=lifespan,
        agent_status=lambda: agent_service.status() if agent_service else {},
        start_cooldown_s=float(os.environ.get("PITCHSIDE_START_COOLDOWN_S", "20")),
    )


async def _start_crew(crew: Any) -> None:
    for attempt in range(60):
        try:
            await crew.start()
            log.info("agent crew ready (%d agents)", len(crew.agents))
            return
        except Exception as exc:
            log.warning("agent crew not ready yet (%s); retrying", type(exc).__name__)
            await crew.close()
            await asyncio.sleep(min(5.0, 0.5 * (attempt + 1)))
    log.error("agent crew could not start")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pitchside AI services.")
    parser.add_argument("--role", choices=ROLES, default=os.environ.get("PITCHSIDE_ROLE", "all"))
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    configure_logging()
    uvicorn.run(
        build(args.role), host=args.host, port=args.port, log_level="info", access_log=False
    )


if __name__ == "__main__":
    main()
