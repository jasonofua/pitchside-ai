"""Message bus between services.

Local mode uses LocalBus, an in-process fan-out queue. Azure mode uses Event Hubs
(runtime.eventhubs), one hub per topic, partitioned by match_id so each match stays in
order. Both carry JSON-able dicts, so services behave the same in either mode.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel

log = logging.getLogger(__name__)

Topic = Literal[
    "matches",  # MatchInfo: a match was created or changed status
    "events",  # MatchEvent from the simulator (raw)
    "tracking",  # TrackingFrame from the simulator
    "accepted",  # MatchEvent after Ingestor validation and de-duplication
    "stats",  # StatsSnapshot from the Stats Engine
    "triggers",  # Trigger from the Stats Engine
    "overlays",  # OverlayCard from the Producer
    "trace",  # AgentTrace from the agent workflow
    "control",  # admin commands, e.g. the chaos switch
]
TOPICS: tuple[Topic, ...] = (
    "matches", "events", "tracking", "accepted", "stats", "triggers", "overlays", "trace",
    "control",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Message:
    topic: Topic
    key: str  # partition key: the match_id
    data: dict[str, Any]


def to_data(payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """JSON-able dict of a model. Unset optional fields are left out (the JSON Schemas
    forbid null for them) while fields set to None, such as a TeamStats ppda with no
    defensive actions yet, are kept as null."""
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json", exclude_unset=True)
    return payload


class Bus(Protocol):
    async def publish(self, topic: Topic, key: str, payload: BaseModel | dict[str, Any]) -> None:
        """Send one message. Messages with the same key keep their order."""

    def subscribe(self, topic: Topic, group: str) -> AsyncIterator[Message]:
        """Messages published to `topic` from now on. Each group gets its own copy."""

    async def close(self) -> None: ...


class LocalBus:
    """In-process fan-out. Each (topic, group) subscription gets its own bounded queue.

    A slow subscriber cannot stall publishers: when its queue is full the oldest message
    is dropped and counted (tracking frames are the only realistic case).
    """

    def __init__(self, maxsize: int = 20_000) -> None:
        self.maxsize = maxsize
        self._subs: dict[Topic, dict[str, list[asyncio.Queue[Message | None]]]] = {}
        self.dropped = 0
        self.published = 0

    async def publish(self, topic: Topic, key: str, payload: BaseModel | dict[str, Any]) -> None:
        msg = Message(topic, key, to_data(payload))
        self.published += 1
        for queues in self._subs.get(topic, {}).values():
            for q in queues:
                if q.full():
                    q.get_nowait()
                    self.dropped += 1
                q.put_nowait(msg)

    def queue(self, topic: Topic, group: str) -> asyncio.Queue[Message | None]:
        """Register a subscription now (so nothing published afterwards is missed)."""
        q: asyncio.Queue[Message | None] = asyncio.Queue(self.maxsize)
        self._subs.setdefault(topic, {}).setdefault(group, []).append(q)
        return q

    async def _drain(
        self, topic: Topic, group: str, q: asyncio.Queue[Message | None]
    ) -> AsyncIterator[Message]:
        try:
            while True:
                msg = await q.get()
                if msg is None:
                    return
                yield msg
        finally:
            queues = self._subs.get(topic, {}).get(group, [])
            if q in queues:
                queues.remove(q)

    def subscribe(self, topic: Topic, group: str) -> AsyncIterator[Message]:
        return self._drain(topic, group, self.queue(topic, group))

    async def close(self) -> None:
        for groups in self._subs.values():
            for queues in groups.values():
                for q in queues:
                    if q.full():
                        q.get_nowait()
                    q.put_nowait(None)
