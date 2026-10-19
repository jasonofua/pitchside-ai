"""Azure Web PubSub delivery for Azure mode (managed identity, no keys).

Browsers get a client URL from /api/negotiate whose token joins them to three groups on
connect: the match (tracking, events, stats, status), their profile within the match
(overlay cards written for them) and, for Director panels, the admin group (agent trace).
The forwarder consumes the same bus topics as the local Hub and sends each message to the
right group.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from gateway.hub import Hub, envelope
from runtime.bus import Bus, Message, Topic
from runtime.config import Settings

log = logging.getLogger(__name__)

TRACKING_EVERY = 2  # forward every 2nd frame (2.5 Hz); the pitch interpolates between them

_client: Any = None


def _service(settings: Settings) -> Any:
    global _client
    if _client is None:
        from azure.identity.aio import DefaultAzureCredential
        from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient

        _client = WebPubSubServiceClient(
            hub=settings.webpubsub_hub,
            endpoint=settings.webpubsub_endpoint,
            credential=DefaultAzureCredential(),
        )
    return _client


def group_match(match_id: str) -> str:
    return f"m.{match_id}"


def group_profile(match_id: str, profile_hash: str) -> str:
    return f"m.{match_id}.p.{profile_hash}"


def group_admin(match_id: str) -> str:
    return f"m.{match_id}.admin"


async def client_url(settings: Settings, match_id: str, profile_hash: str, admin: bool) -> str:
    groups = [group_match(match_id), group_profile(match_id, profile_hash)]
    if admin:
        groups.append(group_admin(match_id))
    token = await _service(settings).get_client_access_token(groups=groups, minutes_to_expire=180)
    return str(token["url"])


class WebPubSubHub(Hub):
    """The Hub's cache and routing, delivered through Web PubSub groups."""

    def __init__(self, bus: Bus, settings: Settings) -> None:
        super().__init__(bus)
        self.settings = settings
        self._frames: dict[str, int] = {}

    async def _send(self, group: str, text: str) -> None:
        try:
            await _service(self.settings).send_to_group(
                group, text, content_type="application/json"
            )
        except Exception:
            log.exception("web pubsub send to %s failed", group)

    async def deliver(self, msg: Message) -> None:
        self.route(msg)  # keeps the cache that /api/matches/{id}/live serves
        kind = {
            "tracking": "tracking", "accepted": "event", "stats": "stats",
            "overlays": "overlay", "trace": "trace", "matches": "match",
        }.get(msg.topic)  # fmt: skip
        if kind is None:
            return
        if msg.topic == "tracking":
            n = self._frames.get(msg.key, 0) + 1
            self._frames[msg.key] = n
            if n % TRACKING_EVERY:
                return
        text = envelope(kind, msg.data)
        if msg.topic == "overlays":
            group = group_profile(msg.key, str(msg.data.get("audience_profile_hash", "")))
        elif msg.topic == "trace":
            group = group_admin(msg.key)
        else:
            group = group_match(msg.key)
        await self._send(group, text)

    async def _consume(self, topic: Topic, messages: AsyncIterator[Message]) -> None:
        async for msg in messages:
            await self.deliver(msg)
