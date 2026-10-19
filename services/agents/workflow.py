"""The agent workflow and the service that runs it for every trigger.

Moment Detector → Tactical Analyst → Narrator → Fan Lens (fan-out per profile) → Localizer
→ Fact Checker → Producer, built with Agent Framework's WorkflowBuilder. Messages between
executors are the typed contracts (Trigger, Moment, Story, CardDraft); every one carries
trace_id and moment_id. A workflow instance cannot run twice at once, so each trigger gets
its own (executors are cheap; the agents they call are shared).
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections import defaultdict
from typing import Any

from agent_framework import Workflow, WorkflowBuilder

from agents.crew import Crew
from agents.fact_checker import FactChecker
from agents.fan_lens import FanLens
from agents.localizer import Localizer
from agents.moment_detector import MomentDetector
from agents.narrator import Narrator
from agents.producer import Producer
from agents.recap import build_recap
from agents.run import Run, provisional_moment
from agents.tactical_analyst import TacticalAnalyst
from contracts import OverlayCard, Profile, Trigger
from runtime.bus import Bus, Message

log = logging.getLogger(__name__)

# Triggers worth the models' time even when nobody is watching (they feed the dashboard and
# the recap); ticks and sprints are skipped then.
WITHOUT_VIEWERS = frozenset({"goal", "card", "half_time", "full_time", "xg", "momentum_swing"})
MAX_RUNS_PER_MATCH = 4
TICK_BUSY_LIMIT = 2  # skip a tick if this many runs are already in flight


def build_workflow(run: Run) -> Workflow:
    detector = MomentDetector(run)
    chain = [
        detector,
        TacticalAnalyst(run),
        Narrator(run),
        FanLens(run),
        Localizer(run),
        FactChecker(run),
        Producer(run),
    ]
    return (
        WorkflowBuilder(
            name="pitchside-moment",
            description="Trigger to explained, personalised, fact-checked overlay cards",
            start_executor=detector,
        )
        .add_chain(chain)
        .build()
    )


class AgentService:
    """Consumes triggers and control messages; runs one workflow per trigger."""

    def __init__(self, crew: Crew) -> None:
        self.crew = crew
        self.profiles: dict[str, dict[str, Profile]] = defaultdict(dict)
        self._inflight: dict[str, int] = defaultdict(int)
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self.memory: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
        self.runs = 0
        self.skipped = 0

    @property
    def bus(self) -> Bus:
        return self.crew.bus

    def status(self) -> dict[str, Any]:
        return {
            "chaos": self.crew.chaos.status(),
            "breakers": {
                name: {"open": b.is_open, "recent_failures": len(b.failures)}
                for name, b in self.crew.guard.breakers.items()
            },
            "runs": self.runs,
            "skipped": self.skipped,
            "inflight": dict(self._inflight),
            "viewers": {m: len(p) for m, p in self.profiles.items()},
            "llm": self.crew.settings.llm,
        }

    # ------------------------------------------------------------------ control

    def on_control(self, data: dict[str, Any]) -> None:
        kind = data.get("type")
        if kind == "profiles":
            profiles = {
                item["hash"]: Profile.model_validate(item["profile"])
                for item in data.get("profiles", [])
            }
            self.profiles[data["match_id"]] = profiles
        elif kind == "chaos":
            self.crew.chaos.kill(str(data.get("agent", "narrator")), float(data.get("seconds", 20)))
        elif kind == "fault" and data.get("kind") == "wrong_number":
            self.crew.chaos.wrong_numbers += int(data.get("count", 1))

    # ----------------------------------------------------------------- triggers

    async def handle(self, trigger: Trigger) -> list[OverlayCard]:
        """Run the whole crew for one trigger; returns the overlay cards it published."""
        match_id = trigger.match_id
        profiles = dict(self.profiles.get(match_id, {}))
        if not profiles and trigger.kind not in WITHOUT_VIEWERS:
            self.skipped += 1
            return []
        if trigger.kind == "tick" and self._inflight[match_id] >= TICK_BUSY_LIMIT:
            self.skipped += 1
            return []
        trace_id = f"t-{secrets.token_hex(6)}"
        run = Run(self.crew, trigger, trace_id, provisional_moment(trigger, trace_id), profiles,
                  memory=self.memory[match_id])  # fmt: skip
        sem = self._sems.setdefault(match_id, asyncio.Semaphore(MAX_RUNS_PER_MATCH))
        self._inflight[match_id] += 1
        try:
            await run.template_cards()  # the < 1 s stats-only overlay
            async with sem:
                self.runs += 1
                result = await build_workflow(run).run(trigger)
            cards = [o for o in result.get_outputs() if isinstance(o, OverlayCard)]
            if trigger.kind == "full_time":
                await build_recap(run)
            return cards
        finally:
            self._inflight[match_id] -= 1

    def _spawn(self, trigger: Trigger) -> None:
        async def guarded() -> None:
            try:
                await self.handle(trigger)
            except Exception:
                log.exception("workflow failed for %s", trigger.trigger_id)

        task = asyncio.create_task(guarded())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _consume_triggers(self, messages: Any) -> None:
        async for msg in messages:
            try:
                self._spawn(Trigger.model_validate(msg.data))
            except Exception:
                log.exception("bad trigger")

    async def _consume_control(self, messages: Any) -> None:
        msg: Message
        async for msg in messages:
            try:
                self.on_control(msg.data)
            except Exception:
                log.exception("bad control message")

    async def run(self) -> None:
        triggers = self.bus.subscribe("triggers", "agents")
        control = self.bus.subscribe("control", "agents")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._consume_triggers(triggers))
            tg.create_task(self._consume_control(control))

    async def drain(self) -> None:
        """Wait for in-flight workflows (tests and shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
