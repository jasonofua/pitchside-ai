"""Day 3 milestone: one simulated match, explained end to end, in a terminal.

Runs the simulator, Ingestor, Stats Engine, Match Stats MCP server and the seven-agent
workflow in one process (in-process bus, SQLite in memory, MCP over an in-process HTTP
transport) and prints each explained moment as the agents produce it. Uses the offline mock
models unless FOUNDRY_ENDPOINT or OPENAI_COMPAT_BASE_URL is set.

    uv run python scripts/explain_match.py --scenario comeback --seed 42 --speed 0
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import replace

import httpx

from agents.crew import Crew
from agents.workflow import AgentService
from contracts import OverlayCard
from contracts.agents import AgentTrace
from ingestor import Ingestor
from mcp_stats import build_server, http_app
from runtime.bus import LocalBus
from runtime.config import Settings
from runtime.profiles import DEMO_PROFILES, profile_hash
from runtime.store import SqliteStore
from sim.engine import MatchConfig
from sim.live import run_live
from sim.scenario import load_scenario
from sim.world import load_world
from stats.service import StatsRegistry, StatsService

COLOURS = {"ok": "\033[32m", "regenerated": "\033[32m", "rejected": "\033[31m",
           "fallback": "\033[33m", "timeout": "\033[33m", "circuit_open": "\033[31m",
           "error": "\033[31m", "skipped": "\033[2m", "dropped": "\033[2m"}  # fmt: skip
RESET = "\033[0m"


async def main(args: argparse.Namespace) -> None:
    world = load_world()
    settings = replace(Settings.from_env(), mcp_url="http://mcp.local/mcp", model_timeout_s=8.0)
    bus, store = LocalBus(maxsize=500_000), SqliteStore()
    registry = StatsRegistry(world, store)
    mcp = build_server(registry)
    app = http_app(mcp)
    home, away = args.home, args.away
    if args.scenario != "default":
        sc = load_scenario(args.scenario)
        home, away = home or sc.home, away or sc.away
    config = MatchConfig(home=home or "LAG", away=away or "HCF", seed=args.seed,
                         scenario=args.scenario, match_id=f"explain-{args.seed}")  # fmt: skip
    profiles = list(DEMO_PROFILES[: args.viewers])

    async with mcp.session_manager.run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://mcp.local") as http:
            crew = Crew(settings, bus, store, http_client=http)
            await crew.start()
            service = AgentService(crew)
            service.on_control({
                "type": "profiles", "match_id": config.match_id,
                "profiles": [{"hash": profile_hash(p), "profile": p.model_dump(exclude_none=True)}
                             for p in profiles],
            })  # fmt: skip
            labels = {profile_hash(p): f"{p.mode}/{p.language}" for p in profiles}
            overlays = bus.subscribe("overlays", "terminal")
            traces = bus.subscribe("trace", "terminal")
            tasks = [
                asyncio.create_task(Ingestor(store, bus).run()),
                asyncio.create_task(StatsService(registry, bus).run()),
                asyncio.create_task(service.run()),
                asyncio.create_task(print_overlays(overlays, labels)),
            ]
            tasks.append(asyncio.create_task(print_traces(traces, everything=args.trace)))
            await asyncio.sleep(0)
            print(f"== {config.home} v {config.away} · {args.scenario} · seed {args.seed} · "
                  f"models: {settings.llm} · viewers: {', '.join(labels.values())}")  # fmt: skip
            await run_live(world, config, bus, speed=args.speed, halftime_s=0)
            await asyncio.sleep(0.5)
            await service.drain()
            await asyncio.sleep(0.2)
            for t in tasks:
                t.cancel()
            await crew.close()
    recap = await store.docs("recap", config.match_id)
    if recap:
        r = recap[-1]
        print(f"\n== RECAP: {r['headline']['en']}\n{r['story']['en']}")
        potm = r.get("player_of_the_match")
        if potm:
            print(f"Player of the match: {potm['name']}")
    print(f"\nworkflow runs: {service.runs}, triggers skipped: {service.skipped}")


async def print_overlays(messages: object, labels: dict[str, str]) -> None:
    async for msg in messages:  # type: ignore[attr-defined]
        card = OverlayCard.model_validate(msg.data)
        who = labels.get(card.audience_profile_hash, "?")
        tag = "AI" if card.source == "agent" else "stats"
        print(f"[{card.clock_ms // 60000:>3}'] {who:<14} {card.slot:<11} {tag:<5} "
              f"{card.title}" + (f" — {card.body}" if card.body else ""))  # fmt: skip


async def print_traces(messages: object, everything: bool) -> None:
    """Every agent step with --trace; otherwise just the explanations as they land."""
    async for msg in messages:  # type: ignore[attr-defined]
        tr = AgentTrace.model_validate(msg.data)
        if everything:
            colour = COLOURS.get(tr.status, "")
            tools = f" [{', '.join(tr.tools)}]" if tr.tools else ""
            print(f"      {colour}{tr.agent:<16} {tr.status:<12}{RESET} {tr.latency_ms:>5}ms"
                  f"{tools} {tr.detail or ''}"[:220])  # fmt: skip
        elif tr.status == "ok" and tr.agent in ("tactical_analyst", "narrator"):
            label = "INSIGHT " if tr.agent == "tactical_analyst" else "NARRATOR"
            print(f"  >> {label} {tr.detail}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="comeback")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--speed",
        type=float,
        default=20.0,
        help="match-clock multiplier; 0 = as fast as possible (most agent cards then go stale)",
    )
    parser.add_argument("--home")
    parser.add_argument("--away")
    parser.add_argument("--viewers", type=int, default=3, choices=[0, 1, 2, 3])
    parser.add_argument("--trace", action="store_true", help="print every agent step")
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main(parser.parse_args()))
