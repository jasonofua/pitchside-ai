"""Ingestor: validate raw simulator events, de-duplicate by event_id, append to the event
log, and republish accepted events for the Stats Engine."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from contracts import MatchEvent, MatchInfo
from runtime.bus import Bus, Message
from runtime.config import REPO_ROOT
from runtime.store import Store

log = logging.getLogger(__name__)


@cache
def event_validator() -> Draft202012Validator:
    schema = json.loads((REPO_ROOT / "schemas" / "event.schema.json").read_text())
    return Draft202012Validator(schema)


@dataclass
class IngestStats:
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    last_errors: list[str] = field(default_factory=list)


class Ingestor:
    def __init__(self, store: Store, bus: Bus) -> None:
        self.store = store
        self.bus = bus
        self.stats = IngestStats()

    def _reject(self, reason: str) -> None:
        self.stats.rejected += 1
        self.stats.last_errors = [*self.stats.last_errors[-9:], reason]
        log.warning("rejected event: %s", reason)

    async def handle(self, data: dict[str, Any]) -> MatchEvent | None:
        """Process one raw event. Returns the event if it was new and valid."""
        errors = sorted(event_validator().iter_errors(data), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            where = "/".join(str(p) for p in first.path) or "(root)"
            self._reject(f"{data.get('event_id', '?')}: {where}: {first.message}")
            return None
        try:
            event = MatchEvent.model_validate(data)
        except ValidationError as exc:
            self._reject(f"{data.get('event_id', '?')}: {exc.errors()[0]['msg']}")
            return None
        if not await self.store.append_event(event):
            self.stats.duplicates += 1
            return None
        self.stats.accepted += 1
        await self.bus.publish("accepted", event.match_id, event)
        return event

    async def _events(self, messages: AsyncIterator[Message]) -> None:
        async for msg in messages:
            try:
                await self.handle(msg.data)
            except Exception:  # keep consuming; one bad message must not stop ingestion
                log.exception("ingestor failed on a message")

    async def _matches(self, messages: AsyncIterator[Message]) -> None:
        """Keep the match records (status, speed, scenario) in the store."""
        async for msg in messages:
            try:
                await self.store.put_match(MatchInfo.model_validate(msg.data))
            except Exception:
                log.exception("ingestor failed on a match record")

    async def run(self) -> None:
        events = self.bus.subscribe("events", "ingestor")
        matches = self.bus.subscribe("matches", "ingestor")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._events(events))
            tg.create_task(self._matches(matches))
