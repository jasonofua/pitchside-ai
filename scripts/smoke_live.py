"""End-to-end check of a running Pitchside AI: local mode, the container, or the Azure demo.

Starts a match (or joins one), connects the three demo viewers the way the browser does
(negotiate, then the gateway's WebSocket locally or Azure Web PubSub with a heartbeat in
Azure mode), follows the match to full time and reports what each viewer received, how
each agent fared and whether the recap was written. Exits non-zero if a viewer got no
cards, no card was written by the agents, or there is no recap.

    uv run python scripts/smoke_live.py http://localhost:8000 --speed 20
    uv run python scripts/smoke_live.py https://<gateway-url> --speed 5
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import httpx
from websockets.asyncio.client import connect
from websockets.typing import Subprotocol

from contracts import Profile
from runtime.profiles import DEMO_PROFILES

HEARTBEAT_S = 30
FINAL_GRACE_S = 45  # full-time cards and the recap arrive after the final whistle


@dataclass
class Viewer:
    profile: Profile
    protocol: str = ""
    messages: Counter[str] = field(default_factory=Counter)
    cards: dict[str, dict[str, Any]] = field(default_factory=dict)
    first_card_s: float | None = None

    @property
    def label(self) -> str:
        p = self.profile
        return f"{p.mode}/{p.language}" + (f"/{p.favorite_player}" if p.favorite_player else "")


async def watch(http: httpx.AsyncClient, match_id: str, viewer: Viewer, t0: float,
                stop: asyncio.Event) -> None:  # fmt: skip
    profile = json.dumps(viewer.profile.model_dump(exclude_none=True))
    neg = await http.get("/api/negotiate", params={"match_id": match_id, "profile": profile})
    neg.raise_for_status()
    info = neg.json()
    viewer.protocol = info["protocol"]
    subprotocols = [] if info["protocol"] == "plain" else [Subprotocol(info["protocol"])]

    async def heartbeat() -> None:
        body = {"profile": viewer.profile.model_dump(exclude_none=True)}
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            with contextlib.suppress(httpx.HTTPError):
                await http.post(f"/api/matches/{match_id}/viewers", json=body)

    async with connect(info["url"], subprotocols=subprotocols, max_size=2**22) as ws:
        beat = asyncio.create_task(heartbeat()) if subprotocols else None
        try:
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except TimeoutError:
                    continue
                msg = json.loads(raw)
                if msg.get("type") == "message":  # Web PubSub wraps our envelope
                    msg = msg.get("data") or {}
                kind = msg.get("type", "?")
                viewer.messages[kind] += 1
                if kind == "overlay":
                    card = msg["data"]
                    viewer.cards[card["overlay_id"]] = card  # an agent card replaces its template
                    if viewer.first_card_s is None:
                        viewer.first_card_s = time.monotonic() - t0
        finally:
            if beat:
                beat.cancel()


async def start_or_join(http: httpx.AsyncClient, args: argparse.Namespace) -> str:
    if args.match_id:
        return str(args.match_id)
    res = await http.post("/api/matches", json={"scenario": args.scenario, "speed": args.speed})
    if res.status_code == 429:  # someone just started one: join the newest live match
        live = [m for m in (await http.get("/api/matches")).json() if m.get("status") == "live"]
        if not live:
            sys.exit("a match was just started but none is live yet; retry in 20 s")
        return str(sorted(live, key=lambda m: m.get("created_at", ""))[-1]["match_id"])
    res.raise_for_status()
    return str(res.json()["match_id"])


async def main(args: argparse.Namespace) -> int:
    async with httpx.AsyncClient(base_url=args.url.rstrip("/"), timeout=30) as http:
        health = (await http.get("/api/health")).json()
        print(f"health: {health}")
        match_id = await start_or_join(http, args)
        print(f"match:  {match_id}")
        t0 = time.monotonic()
        stop = asyncio.Event()
        viewers = [Viewer(p) for p in DEMO_PROFILES]
        tasks = [asyncio.create_task(watch(http, match_id, v, t0, stop)) for v in viewers]

        status, last = "", ""
        while time.monotonic() - t0 < args.timeout:
            with contextlib.suppress(httpx.HTTPError):
                status = (await http.get(f"/api/matches/{match_id}")).json().get("status", "")
            cards = sum(len(v.cards) for v in viewers)
            line = f"{time.monotonic() - t0:5.0f}s  {status:<10} cards={cards}"
            if line.split()[1:] != last.split()[1:]:
                print(line, flush=True)
                last = line
            if status in ("full_time", "aborted") or any(t.done() for t in tasks):
                break
            await asyncio.sleep(5)

        recap: dict[str, Any] | None = None
        deadline = time.monotonic() + FINAL_GRACE_S
        while time.monotonic() < deadline and status == "full_time":
            res = await http.get(f"/api/matches/{match_id}/recap")
            if res.status_code == 200:
                recap = res.json()
                break
            await asyncio.sleep(3)
        await asyncio.sleep(5)  # let the last cards land
        stop.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)

        trace = (await http.get(f"/api/matches/{match_id}/trace", params={"limit": 1000})).json()

    failures: list[str] = []
    print(f"\nfinished as {status!r} after {time.monotonic() - t0:.0f}s")
    for viewer, result in zip(viewers, results, strict=True):
        sources = Counter(c.get("source", "agent") for c in viewer.cards.values())
        first = f"{viewer.first_card_s:.0f}s" if viewer.first_card_s is not None else "-"
        print(
            f"  {viewer.label:<26} via {viewer.protocol:<24} cards={len(viewer.cards):<4} "
            f"agent={sources['agent']:<4} template={sources['template']:<4} first={first}"
        )
        if isinstance(result, BaseException):
            failures.append(f"{viewer.label}: connection failed: {result!r}")
        elif not viewer.cards:
            failures.append(f"{viewer.label}: no cards")
        agent_cards = [c for c in viewer.cards.values() if c.get("source", "agent") == "agent"]
        if agent_cards:
            print(f"      latest agent card: {agent_cards[-1]['title']!r}")

    per_agent: dict[str, Counter[str]] = defaultdict(Counter)
    for step in trace:
        per_agent[step["agent"]][step["status"]] += 1
    print("\nagent steps (status counts):")
    for agent, counts in sorted(per_agent.items()):
        print(f"  {agent:<17} " + ", ".join(f"{k}={n}" for k, n in counts.most_common()))

    if not any(c.get("source", "agent") == "agent" for v in viewers for c in v.cards.values()):
        failures.append("no card was written by the agents (only stats-only templates)")
    if recap is None:
        failures.append("no recap" if status == "full_time" else f"match ended as {status!r}")
    else:
        print(f"\nrecap: {json.dumps(recap)[:300]}")
    for f in failures:
        print(f"FAIL: {f}")
    print("OK" if not failures else f"{len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--scenario", default="comeback")
    parser.add_argument("--speed", type=float, default=20.0, choices=[1.0, 5.0, 20.0])
    parser.add_argument("--match-id", help="join this match instead of starting one")
    parser.add_argument("--timeout", type=float, default=1800, help="seconds to wait for full time")
    sys.exit(asyncio.run(main(parser.parse_args())))
