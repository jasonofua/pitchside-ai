"""Gateway: REST API, WebSocket fan-out and the admin (Director) API.

`create_app(runtime)` builds the FastAPI app around whichever components the process runs
(see runtime.main). In local mode one process runs everything, so the stats routes read
the in-process registry and /mcp serves the Match Stats MCP server; in Azure mode the
gateway reads stats from the stats app and browsers connect through Web PubSub.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
import urllib.parse
from collections import deque
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.websockets import WebSocketDisconnect

from contracts import Profile, World
from gateway.hub import Hub, make_client
from gateway.readers import StatsReader, StatsUnavailableError
from runtime.bus import Bus
from runtime.config import REPO_ROOT, Settings
from runtime.profiles import profile_hash
from runtime.store import Store
from sim.scenario import load_scenario, scenario_names
from sim.service import SPEEDS, fresh_match_id
from stats.engine import Window

log = logging.getLogger(__name__)

START_COOLDOWN_S = 20.0


class StartMatch(BaseModel):
    scenario: str = "comeback"
    seed: int | None = Field(default=None, ge=0, le=1_000_000)
    speed: float = 5.0
    home: str | None = None
    away: str | None = None


class ChaosRequest(BaseModel):
    agent: Literal[
        "moment_detector", "tactical_analyst", "narrator", "fan_lens", "localizer",
        "fact_checker", "producer",
    ] = "narrator"  # fmt: skip
    seconds: float = Field(default=20.0, gt=0, le=300)


class FaultRequest(BaseModel):
    kind: Literal["wrong_number"] = "wrong_number"
    count: int = Field(default=1, ge=1, le=5)


def parse_profile(raw: str | None) -> Profile:
    if not raw:
        return Profile(mode="casual", language="en")
    try:
        return Profile.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, f"bad profile: {exc}") from exc


def stats_router(reader: StatsReader) -> APIRouter:
    """Read-only stats routes, served by the stats app and (locally) the gateway."""
    r = APIRouter(prefix="/api/matches/{match_id}", tags=["stats"])

    async def guard(coro: Any) -> Any:
        try:
            return await coro
        except StatsUnavailableError as exc:
            raise HTTPException(404, f"unknown: {exc}") from exc

    @r.get("/state")
    async def state(match_id: str) -> Any:
        return await guard(reader.state(match_id))

    @r.get("/stats")
    async def team_stats(match_id: str, window: Window = "match") -> Any:
        return await guard(reader.team_stats(match_id, window))

    @r.get("/players/{player_id}")
    async def player(match_id: str, player_id: str, window: Window = "match") -> Any:
        return await guard(reader.player(match_id, player_id, window))

    @r.get("/momentum")
    async def momentum(match_id: str, window: Window = "match") -> Any:
        return await guard(reader.momentum(match_id, window))

    @r.get("/events")
    async def events(
        match_id: str, since: int = -1, types: str | None = None, limit: int = Query(50, le=500)
    ) -> Any:
        wanted = [t for t in types.split(",") if t] if types else None
        return await guard(reader.events(match_id, since, wanted, limit))

    @r.get("/compare")
    async def compare(match_id: str) -> Any:
        return await guard(reader.compare(match_id))

    @r.get("/analyst")
    async def analyst(match_id: str) -> Any:
        return await guard(reader.analyst(match_id))

    return r


def create_app(
    *,
    settings: Settings,
    world: World,
    bus: Bus,
    store: Store,
    reader: StatsReader,
    hub: Hub | None,
    extra_routes: list[Any] | None = None,
    lifespan: Any = None,
    agent_status: Any = None,
    start_cooldown_s: float = START_COOLDOWN_S,
) -> FastAPI:
    app = FastAPI(
        title="Pitchside AI",
        version="0.1.0",
        description="Live, explained, personalized match intelligence for fictional football.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins) or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.bus = bus
    app.state.hub = hub
    last_start: deque[float] = deque(maxlen=1)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "mode": settings.mode, "llm": settings.llm}

    @app.get("/api/world")
    async def get_world() -> Any:
        return world.model_dump(mode="json")

    @app.get("/api/crests/{team_id}.svg")
    async def crest(team_id: str) -> FileResponse:
        path = REPO_ROOT / "data" / "crests" / f"{team_id.upper()}.svg"
        if not path.is_file() or not team_id.isalpha():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/svg+xml")

    @app.get("/api/scenarios")
    async def scenarios() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name in scenario_names():
            if name == "default":
                out.append({"name": name, "description": "No script: let the match play out.",
                            "home": "LAG", "away": "HCF"})  # fmt: skip
                continue
            sc = load_scenario(name)
            out.append({"name": name, "description": sc.description, "home": sc.home,
                        "away": sc.away})  # fmt: skip
        return out

    @app.get("/api/matches")
    async def list_matches() -> Any:
        return [m.model_dump(mode="json", exclude_none=True) for m in await store.list_matches()]

    @app.post("/api/matches", status_code=202)
    async def start_match(req: StartMatch) -> dict[str, Any]:
        now = time.monotonic()
        if last_start and now - last_start[0] < start_cooldown_s:
            raise HTTPException(429, "a match was just started; join it from the list")
        if req.scenario not in scenario_names():
            raise HTTPException(422, f"unknown scenario {req.scenario!r}")
        if req.speed not in SPEEDS:
            raise HTTPException(422, f"speed must be one of {SPEEDS}")
        want_home, want_away = req.home, req.away
        if req.scenario != "default":
            sc = load_scenario(req.scenario)
            want_home, want_away = want_home or sc.home, want_away or sc.away
        home: str = want_home or "LAG"
        away: str = want_away or "HCF"
        known = {c.team_id for c in world.clubs}
        if home not in known or away not in known or home == away:
            raise HTTPException(422, "home and away must be two different known clubs")
        seed = req.seed if req.seed is not None else 42
        match_id = fresh_match_id(home, away, req.scenario, seed)
        cmd = {"type": "start_match", "match_id": match_id, "home": home, "away": away,
               "seed": seed, "scenario": req.scenario, "speed": req.speed}  # fmt: skip
        await bus.publish("control", match_id, cmd)
        last_start.append(now)
        return {"match_id": match_id, **cmd}

    @app.post("/api/matches/{match_id}/stop", status_code=202)
    async def stop_match(match_id: str) -> dict[str, str]:
        await bus.publish("control", match_id, {"type": "stop_match", "match_id": match_id})
        return {"match_id": match_id, "status": "stopping"}

    @app.get("/api/matches/{match_id}")
    async def get_match(match_id: str) -> Any:
        info = await store.get_match(match_id)
        if info is None:
            raise HTTPException(404, "unknown match")
        return info.model_dump(mode="json", exclude_none=True)

    @app.get("/api/matches/{match_id}/overlays")
    async def overlays(match_id: str, profile_hash: str | None = None) -> Any:
        docs = await store.docs("overlay", match_id, limit=500)
        if profile_hash:
            docs = [d for d in docs if d.get("audience_profile_hash") == profile_hash]
        return docs

    @app.get("/api/matches/{match_id}/moments")
    async def moments(match_id: str) -> Any:
        return {
            "moments": await store.docs("moment", match_id),
            "insights": await store.docs("insight", match_id),
            "commentary": await store.docs("commentary", match_id),
        }

    @app.get("/api/matches/{match_id}/recap")
    async def recap(match_id: str) -> Any:
        docs = await store.docs("recap", match_id)
        if not docs:
            raise HTTPException(404, "no recap yet: it is written at full time")
        return docs[-1]

    @app.get("/api/matches/{match_id}/trace")
    async def trace(match_id: str, limit: int = Query(200, le=1000)) -> Any:
        return await store.docs("trace", match_id, limit=limit)

    @app.get("/api/matches/{match_id}/live")
    async def live(match_id: str, profile_hash: str, admin: bool = False) -> Any:
        """Snapshot for late joiners connecting through Web PubSub (the local WebSocket sends
        the same thing as its first message)."""
        if hub is None:
            raise HTTPException(404, "no live hub in this process")
        return hub.snapshot(match_id, profile_hash, admin)

    @app.get("/api/profiles/hash")
    async def hash_profile(profile: str) -> dict[str, str]:
        return {"profile_hash": profile_hash(parse_profile(profile))}

    @app.get("/api/negotiate")
    async def negotiate(request: Request, match_id: str, profile: str | None = None,
                        admin: bool = False) -> dict[str, Any]:  # fmt: skip
        """Where the browser connects for live data: this gateway's WebSocket locally,
        Azure Web PubSub in Azure mode."""
        prof = parse_profile(profile)
        if settings.webpubsub_endpoint:
            from gateway.webpubsub import client_url

            url = await client_url(settings, match_id, profile_hash(prof), admin)
            return {"url": url, "protocol": "json.webpubsub.azure.v1",
                    "profile_hash": profile_hash(prof)}  # fmt: skip
        scheme = "wss" if request.url.scheme == "https" else "ws"
        host = request.headers.get("host", "localhost:8000")
        params = {"profile": json.dumps(prof.model_dump(exclude_none=True))}
        if admin:
            params["admin"] = "1"
        query = urllib.parse.urlencode(params)
        return {"url": f"{scheme}://{host}/ws/matches/{match_id}?{query}", "protocol": "plain",
                "profile_hash": profile_hash(prof)}  # fmt: skip

    # ---------------------------------------------------------------- admin

    @app.post("/api/admin/chaos")
    async def chaos(req: ChaosRequest) -> dict[str, Any]:
        await bus.publish("control", "admin", {"type": "chaos", "agent": req.agent,
                                               "seconds": req.seconds})  # fmt: skip
        return {"killed": req.agent, "seconds": req.seconds}

    @app.post("/api/admin/fault")
    async def fault(req: FaultRequest) -> dict[str, Any]:
        await bus.publish("control", "admin", {"type": "fault", "kind": req.kind,
                                               "count": req.count})  # fmt: skip
        return {"fault": req.kind, "count": req.count}

    @app.get("/api/admin/status")
    async def admin_status() -> Any:
        return agent_status() if agent_status else {}

    # ------------------------------------------------------------- websocket

    if hub is not None:

        @app.websocket("/ws/matches/{match_id}")
        async def ws(websocket: WebSocket, match_id: str) -> None:
            try:
                prof = parse_profile(websocket.query_params.get("profile"))
            except HTTPException:
                await websocket.close(code=1008)
                return
            await websocket.accept()
            client = make_client(
                match_id, prof, websocket.send_text, websocket.query_params.get("admin") == "1"
            )
            with contextlib.suppress(WebSocketDisconnect):
                await hub.serve(client, websocket.receive_text)

    ingest_token = os.environ.get("PITCHSIDE_INGEST_TOKEN", "")

    @app.websocket("/ws/ingest")
    async def ingest(websocket: WebSocket) -> None:
        """The simulator CLI's `--sink ws`: envelopes in, bus messages out. Open in local
        mode; in Azure mode only with PITCHSIDE_INGEST_TOKEN (the public demo uses the sim
        service instead)."""
        allowed = settings.mode == "local" and not ingest_token
        if ingest_token and websocket.query_params.get("token") == ingest_token:
            allowed = True
        if not allowed:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        topics = {"match": "matches", "events": "events", "tracking": "tracking"}
        key = "unknown"
        with contextlib.suppress(WebSocketDisconnect):
            while True:
                envelope = json.loads(await websocket.receive_text())
                topic = topics.get(envelope.get("topic", ""))
                data = envelope.get("data")
                if topic is None or not isinstance(data, dict):
                    continue
                key = str(data.get("match_id", key))
                if topic == "matches":
                    data = {**data, "status": "live"}
                await bus.publish(topic, key, data)  # type: ignore[arg-type]

    app.include_router(stats_router(reader))
    for route in extra_routes or []:
        app.router.routes.append(route)

    web_out = Path(os.environ.get("PITCHSIDE_WEB_DIR", REPO_ROOT / "web" / "out"))
    if web_out.is_dir():
        app.mount("/", StaticFiles(directory=web_out, html=True), name="web")
    else:

        @app.get("/")
        async def root() -> JSONResponse:
            return JSONResponse({"name": "Pitchside AI gateway", "docs": "/docs",
                                 "web": "run `pnpm dev` in web/ or build web/out"})  # fmt: skip

    return app
