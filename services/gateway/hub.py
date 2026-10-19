"""WebSocket fan-out: bus topics to browsers, per match and per personalization profile.

Each browser subscribes to one match with one profile. Tracking frames, events, stats
snapshots and match status go to everyone watching the match; overlay cards only to the
viewers whose profile they were written for; agent traces only to Director panels.
Active profiles are announced on the `control` topic so the agents know whom to write for.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from contracts import Profile
from runtime.bus import Bus, Message, Topic
from runtime.profiles import profile_hash

log = logging.getLogger(__name__)

# Bus topic -> message type sent to browsers.
FORWARD: dict[Topic, str] = {
    "tracking": "tracking",
    "accepted": "event",
    "stats": "stats",
    "overlays": "overlay",
    "trace": "trace",
    "matches": "match",
}
CLIENT_QUEUE = 2_000
RECENT_OVERLAYS = 30
RECENT_EVENTS = 40
RECENT_TRACES = 60

Send = Callable[[str], Awaitable[None]]


@dataclass(eq=False)
class Client:
    match_id: str
    profile: Profile
    profile_hash: str
    send: Send
    admin: bool = False
    queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(CLIENT_QUEUE))
    dropped: int = 0

    def offer(self, text: str) -> None:
        if self.queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            self.dropped += 1
        self.queue.put_nowait(text)


@dataclass
class MatchCache:
    """What a late joiner needs to paint the screen at once."""

    match: dict[str, Any] | None = None
    stats: dict[str, Any] | None = None
    frame: dict[str, Any] | None = None
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=RECENT_EVENTS))
    overlays: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=RECENT_OVERLAYS * 4)
    )
    traces: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=RECENT_TRACES))


def envelope(kind: str, data: Any) -> str:
    return json.dumps({"type": kind, "data": data}, separators=(",", ":"))


class Hub:
    def __init__(self, bus: Bus) -> None:
        self.bus = bus
        self.clients: dict[str, set[Client]] = defaultdict(set)
        self.cache: dict[str, MatchCache] = defaultdict(MatchCache)
        self._announced: dict[str, tuple[str, ...]] = {}

    # --------------------------------------------------------------- clients

    def active_profiles(self, match_id: str) -> dict[str, Profile]:
        return {c.profile_hash: c.profile for c in self.clients.get(match_id, ())}

    async def _announce(self, match_id: str) -> None:
        profiles = self.active_profiles(match_id)
        key = tuple(sorted(profiles))
        if self._announced.get(match_id) == key:
            return
        self._announced[match_id] = key
        await self.bus.publish("control", match_id, {
            "type": "profiles",
            "match_id": match_id,
            "profiles": [
                {"hash": h, "profile": p.model_dump(exclude_none=True)} for h, p in profiles.items()
            ],
        })  # fmt: skip

    def hello(self, client: Client) -> str:
        return envelope("hello", self.snapshot(client.match_id, client.profile_hash, client.admin))

    async def serve(self, client: Client, receive: Callable[[], Awaitable[Any]]) -> None:
        """Run one browser connection until it closes."""
        self.clients[client.match_id].add(client)
        client.offer(self.hello(client))
        await self._announce(client.match_id)

        async def pump() -> None:
            while True:
                await client.send(await client.queue.get())

        sender = asyncio.create_task(pump())
        try:
            while True:  # browsers send nothing we need; this just detects the close
                await receive()
        except Exception:
            pass
        finally:
            sender.cancel()
            self.clients[client.match_id].discard(client)
            if not self.clients[client.match_id]:
                self.clients.pop(client.match_id, None)
            await self._announce(client.match_id)

    # ----------------------------------------------------------------- bus side

    def route(self, msg: Message) -> None:
        kind = FORWARD.get(msg.topic)
        if kind is None:
            return
        cache = self.cache[msg.key]
        data = msg.data
        if msg.topic == "tracking":
            cache.frame = data
        elif msg.topic == "stats":
            cache.stats = data
        elif msg.topic == "matches":
            cache.match = data
        elif msg.topic == "accepted":
            cache.events.append(data)
        elif msg.topic == "overlays":
            cache.overlays.append(data)
        elif msg.topic == "trace":
            cache.traces.append(data)
        clients = self.clients.get(msg.key)
        if not clients:
            return
        text = envelope(kind, data)
        for client in clients:
            if msg.topic == "overlays" and data.get("audience_profile_hash") != client.profile_hash:
                continue
            if msg.topic == "trace" and not client.admin:
                continue
            client.offer(text)

    async def _consume(self, topic: Topic, messages: AsyncIterator[Message]) -> None:
        async for msg in messages:
            try:
                self.route(msg)
            except Exception:
                log.exception("hub failed to route a %s message", topic)

    async def run(self) -> None:
        # Subscribe before the first await so nothing published after start is missed.
        subs = {topic: self.bus.subscribe(topic, "gateway") for topic in FORWARD}
        async with asyncio.TaskGroup() as tg:
            for topic, messages in subs.items():
                tg.create_task(self._consume(topic, messages))

    def snapshot(self, match_id: str, profile_hash: str, admin: bool = False) -> dict[str, Any]:
        """The same data as the WebSocket hello, for clients that connect elsewhere."""
        cache = self.cache.get(match_id, MatchCache())
        overlays = [o for o in cache.overlays if o.get("audience_profile_hash") == profile_hash]
        return {
            "match_id": match_id,
            "profile_hash": profile_hash,
            "match": cache.match,
            "stats": cache.stats,
            "frame": cache.frame,
            "events": list(cache.events),
            "overlays": overlays[-RECENT_OVERLAYS:],
            "traces": list(cache.traces) if admin else [],
        }


def make_client(match_id: str, profile: Profile, send: Send, admin: bool = False) -> Client:
    return Client(match_id, profile, profile_hash(profile), send, admin)
