"""The gateway in local mode: REST, match start, WebSocket fan-out and profile filtering."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from contracts import Profile
from runtime.config import Settings
from runtime.main import build
from runtime.profiles import profile_hash


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("PITCHSIDE_START_COOLDOWN_S", "0")
    monkeypatch.setenv("PITCHSIDE_WEB_DIR", str(tmp_path / "no-web"))
    settings = replace(
        Settings.from_env(), llm="mock", data_dir=tmp_path, mcp_url="http://127.0.0.1:9/mcp"
    )
    app = build("all", settings)
    with TestClient(app) as c:
        yield c


def test_static_endpoints(client: TestClient) -> None:
    assert client.get("/api/health").json()["mode"] == "local"
    world = client.get("/api/world").json()
    assert {c["team_id"] for c in world["clubs"]} == {"LAG", "HCF", "NBR", "KVA"}
    names = {s["name"] for s in client.get("/api/scenarios").json()}
    assert {"comeback", "late_winner", "red_card", "pressing_collapse", "default"} <= names
    crest = client.get("/api/crests/LAG.svg")
    assert crest.status_code == 200 and crest.text.startswith("<svg")
    assert client.get("/api/crests/..%2Fworld.svg").status_code == 404


def test_start_validation(client: TestClient) -> None:
    assert client.post("/api/matches", json={"scenario": "nope"}).status_code == 422
    assert client.post("/api/matches", json={"speed": 7}).status_code == 422
    bad = client.post("/api/matches", json={"scenario": "default", "home": "LAG", "away": "LAG"})
    assert bad.status_code == 422


def _receive(ws: Any, seconds: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        out.append(json.loads(ws.receive_text()))
        kinds = {m["type"] for m in out}
        if {"hello", "tracking", "event", "stats"} <= kinds and len(out) > 50:
            break
    return out


def test_live_match_over_websocket(client: TestClient) -> None:
    started = client.post("/api/matches", json={"scenario": "comeback", "speed": 20, "seed": 3})
    assert started.status_code == 202
    mid = started.json()["match_id"]
    assert mid.startswith("lag-hcf-comeback-s3-")
    profile = Profile(mode="casual", language="pcm", favorite_club="LAG")
    neg = client.get(
        "/api/negotiate",
        params={"match_id": mid, "profile": json.dumps(profile.model_dump(exclude_none=True))},
    ).json()
    assert neg["protocol"] == "plain" and neg["profile_hash"] == profile_hash(profile)
    path = neg["url"].split("://", 1)[1].split("/", 1)[1]
    with client.websocket_connect("/" + path) as ws:
        messages = _receive(ws, 30)
    kinds = [m["type"] for m in messages]
    assert kinds[0] == "hello"
    assert {"tracking", "event", "stats"} <= set(kinds)
    frame = next(m["data"] for m in messages if m["type"] == "tracking")
    assert frame["match_id"] == mid and len(frame["players"]) >= 18
    state = client.get(f"/api/matches/{mid}/state").json()
    assert state["match_id"] == mid and state["status"] == "live"
    assert client.get(f"/api/matches/{mid}/stats", params={"window": "last_5"}).status_code == 200
    assert client.get(f"/api/matches/{mid}").json()["scenario"] == "comeback"
    assert client.get("/api/matches/missing/state").status_code == 404
    client.post(f"/api/matches/{mid}/stop")


def _overlay(mid: str, h: str, title: str) -> dict[str, Any]:
    return {
        "overlay_id": f"m:x:{h}", "match_id": mid, "clock_ms": 60_000, "slot": "lower_third",
        "priority": 3, "ttl_ms": 10_000, "audience_profile_hash": h, "lang": "en",
        "title": title, "body": "", "stats": [], "evidence_event_ids": [], "trace_id": "t",
    }  # fmt: skip


def test_overlays_only_reach_their_profile(client: TestClient) -> None:
    bus = client.app.state.bus  # type: ignore[attr-defined]
    a = Profile(mode="analyst", language="en")
    b = Profile(mode="kids", language="fr")
    mid = "overlay-test"

    def url(p: Profile) -> str:
        return f"/ws/matches/{mid}?profile={json.dumps(p.model_dump(exclude_none=True))}"

    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        assert json.loads(wa.receive_text())["type"] == "hello"
        assert json.loads(wb.receive_text())["type"] == "hello"
        assert client.portal is not None
        client.portal.call(bus.publish, "overlays", mid, _overlay(mid, profile_hash(a), "for A"))
        client.portal.call(bus.publish, "overlays", mid, _overlay(mid, profile_hash(b), "for B"))
        got_a = json.loads(wa.receive_text())
        got_b = json.loads(wb.receive_text())
    assert (got_a["type"], got_a["data"]["title"]) == ("overlay", "for A")
    assert (got_b["type"], got_b["data"]["title"]) == ("overlay", "for B")
    live = client.get(f"/api/matches/{mid}/live", params={"profile_hash": profile_hash(a)})
    assert [o["title"] for o in live.json()["overlays"]] == ["for A"]


def test_tracking_is_thinned_for_fast_replays() -> None:
    from gateway.hub import tracking_stride

    assert tracking_stride(None) == 1
    assert tracking_stride({"speed": 5}) == 1
    assert tracking_stride({"speed": 20}) == 4
    assert tracking_stride({"speed": 0}) == 1


def test_web_pubsub_viewers_are_announced_until_their_heartbeat_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Viewers on Web PubSub never connect to the gateway: they register by heartbeat."""
    import asyncio

    from gateway import hub as hub_module
    from runtime.bus import LocalBus

    now = [1_000.0]
    monkeypatch.setattr(hub_module.time, "monotonic", lambda: now[0])
    viewer = Profile(mode="casual", language="pcm", favorite_club="LAG")

    async def scenario() -> list[list[str]]:
        bus = LocalBus()
        control = bus.subscribe("control", "agents")
        hub = hub_module.Hub(bus)
        assert await hub.touch("m1", viewer) == profile_hash(viewer)
        await hub.touch("m1", viewer)  # a heartbeat with nothing new announces nothing
        now[0] += hub_module.VIEWER_TTL_S - 1
        await hub.refresh()  # still alive: re-announced for a restarted agents service
        now[0] += 2
        await hub.refresh()  # heartbeat stopped: announced empty, then forgotten
        await hub.refresh()
        await bus.close()
        return [[p["hash"] for p in m.data["profiles"]] async for m in control]

    h = profile_hash(viewer)
    assert asyncio.run(scenario()) == [[h], [h], []]


def test_viewer_heartbeat_registers_the_profile(client: TestClient) -> None:
    viewer = Profile(mode="player_cam", language="yo", favorite_player="LAG-09")
    res = client.post("/api/matches/hb-test/viewers", json={"profile": viewer.model_dump()})
    assert res.status_code == 200
    assert res.json()["profile_hash"] == profile_hash(viewer)
    hub = client.app.state.hub  # type: ignore[attr-defined]
    assert set(hub.active_profiles("hb-test")) == {profile_hash(viewer)}
    bad = client.post("/api/matches/hb-test/viewers", json={"profile": {"mode": "nope"}})
    assert bad.status_code == 422
