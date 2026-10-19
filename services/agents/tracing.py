"""Agent trace: one AgentTrace per workflow step, to the Director panel and App Insights.

Each step is published on the `trace` topic, stored for the Director panel's history,
and recorded as an OpenTelemetry span (exported to Application Insights in Azure mode).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace as otel

from contracts.agents import AgentTrace
from runtime.bus import Bus
from runtime.store import Store

log = logging.getLogger(__name__)
tracer = otel.get_tracer("pitchside.agents")


@dataclass
class Step:
    """A step being timed; fill in status/detail/tools before it closes."""

    agent: str
    model: str
    trace_id: str
    match_id: str
    moment_id: str | None = None
    profile_hash: str | None = None
    status: str = "ok"
    detail: str = ""
    tools: list[str] = field(default_factory=list)
    clock_ms: int = 0
    started: float = field(default_factory=time.monotonic)


class Tracer:
    def __init__(self, bus: Bus, store: Store | None = None) -> None:
        self.bus = bus
        self.store = store

    async def emit(self, step: Step) -> AgentTrace:
        latency = int((time.monotonic() - step.started) * 1000)
        fields: dict[str, Any] = {
            "trace_id": step.trace_id,
            "match_id": step.match_id,
            "agent": step.agent,
            "model": step.model,
            "status": step.status,
            "latency_ms": latency,
            "clock_ms": step.clock_ms,
            "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
        }
        if step.moment_id:
            fields["moment_id"] = step.moment_id
        if step.profile_hash:
            fields["profile_hash"] = step.profile_hash
        if step.detail:
            fields["detail"] = step.detail[:500]
        if step.tools:
            fields["tools"] = step.tools
        record = AgentTrace(**fields)
        await self.bus.publish("trace", step.match_id, record)
        if self.store is not None:
            doc_id = f"{step.trace_id}:{step.agent}:{step.profile_hash or '-'}:{latency}"
            await self.store.put_doc("trace", step.match_id, doc_id, record.model_dump(mode="json"))
        log.info(
            "%s %s %s %dms %s", step.agent, step.status, step.moment_id or "", latency, step.detail
        )
        return record

    @contextmanager
    def span(self, step: Step) -> Iterator[Any]:
        with tracer.start_as_current_span(f"agent.{step.agent}") as span:
            span.set_attribute("pitchside.match_id", step.match_id)
            span.set_attribute("pitchside.trace_id", step.trace_id)
            if step.moment_id:
                span.set_attribute("pitchside.moment_id", step.moment_id)
            span.set_attribute("gen_ai.request.model", step.model)
            yield span
            span.set_attribute("pitchside.status", step.status)
