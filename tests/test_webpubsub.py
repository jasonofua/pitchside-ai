"""Azure-mode delivery through Web PubSub, against a fake service client."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import pytest

from gateway import webpubsub
from runtime.bus import LocalBus, Message
from runtime.config import Settings


class FakeService:
    def __init__(self) -> None:
        self.sent: list[tuple[str, Any, str]] = []
        self.gate = asyncio.Event()
        self.gate.set()

    async def send_to_group(self, group: str, message: Any, *, content_type: str) -> None:
        await self.gate.wait()
        self.sent.append((group, message, content_type))


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> FakeService:
    fake = FakeService()
    monkeypatch.setattr(webpubsub, "_service", lambda settings: fake)
    return fake


def _hub() -> webpubsub.WebPubSubHub:
    settings = replace(Settings.from_env(), webpubsub_endpoint="https://wps.example")
    return webpubsub.WebPubSubHub(LocalBus(), settings)


def test_messages_are_sent_as_json_objects_to_the_right_group(service: FakeService) -> None:
    overlay = {"overlay_id": "o1", "audience_profile_hash": "abc", "title": "Goal"}

    async def scenario() -> None:
        hub = _hub()
        await hub.deliver(Message("overlays", "m1", overlay))
        await hub.deliver(Message("trace", "m1", {"agent": "narrator"}))
        await hub.deliver(Message("accepted", "m1", {"event_id": "e1"}))

    asyncio.run(scenario())
    # A dict, not a JSON string: the SDK serializes JSON bodies itself.
    assert service.sent == [
        ("m.m1.p.abc", {"type": "overlay", "data": overlay}, "application/json"),
        ("m.m1.admin", {"type": "trace", "data": {"agent": "narrator"}}, "application/json"),
        ("m.m1", {"type": "event", "data": {"event_id": "e1"}}, "application/json"),
    ]


def test_tracking_keeps_only_the_latest_frame_while_a_send_is_slow(service: FakeService) -> None:
    async def scenario() -> None:
        hub = _hub()
        service.gate.clear()  # the first send hangs
        for t in range(1, 21):  # every 2nd frame is forwarded (TRACKING_EVERY)
            await hub.deliver(Message("tracking", "m1", {"t_ms": t}))
            await asyncio.sleep(0)  # let the sender pick up the first forwarded frame
        service.gate.set()
        while hub._frame_senders:
            await asyncio.sleep(0.01)

    asyncio.run(scenario())
    frames = [msg["data"]["t_ms"] for _, msg, _ in service.sent]
    assert frames == [2, 20]  # the one in flight, then only the newest
