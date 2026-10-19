"""Moment Detector (small model): is this trigger a moment worth explaining, and how big?

Goals and period ends are moments by rule, so the model is skipped for them. For everything
else the model reads match state through MCP and decides; if it is slow, failing or
switched off, the code baseline decides instead.
"""

from __future__ import annotations

from agent_framework import Executor, WorkflowContext, handler

from agents.resilience import AgentUnavailableError
from agents.run import BASELINE, Run
from contracts import Trigger
from contracts.agents import Moment, MomentDecision

NAME = "moment_detector"
RULE_KINDS = frozenset({"goal", "half_time", "full_time"})
SPELL_GAP_MS = 5 * 60_000  # at most one "spell" moment per 5 minutes of match time
SPELL_MIN_MINUTES = 5  # ticks are judged once a half has 5 minutes of play


def _minutes_into_half(trigger: Trigger) -> float:
    start = 0 if trigger.period == 1 else 45 * 60_000
    return (trigger.clock_ms - start) / 60_000


TASK = "Decide whether this trigger is a moment worth explaining."


class MomentDetector(Executor):
    def __init__(self, run: Run) -> None:
        super().__init__(id=NAME)
        self.run = run

    @handler
    async def on_trigger(self, trigger: Trigger, ctx: WorkflowContext[Moment]) -> None:
        run = self.run
        step = run.step(NAME)
        moment = run.moment
        if trigger.kind in RULE_KINDS:
            step.status, step.model = "skipped", "code"
            step.detail = f"{trigger.kind}: always a moment"
        elif trigger.kind == "tick" and _minutes_into_half(trigger) < SPELL_MIN_MINUTES:
            return  # the 5-minute window is not full yet: no spell to judge, no model call
        else:
            payload = {
                "trigger": trigger.model_dump(mode="json", exclude_none=True),
                "match_id": trigger.match_id,
            }
            try:
                with run.crew.tracer.span(step):
                    decision, record = await run.crew.run(
                        NAME, TASK, payload, MomentDecision, step, on_slow=run.template_cards
                    )
                run.recorded.extend(record.payloads())
                if decision.is_moment and decision.kind == "spell" and self._recent_spell():
                    note = "a spell was explained in the last 5 minutes"
                    decision = decision.model_copy(update={"is_moment": False, "summary": note})
                if not decision.is_moment:
                    step.detail = f"not a moment: {decision.summary}"[:500]
                    await run.crew.tracer.emit(step)
                    return
                moment = moment.model_copy(update={
                    "kind": decision.kind,
                    "importance": round(min(1.0, max(0.0, decision.importance)), 2),
                    "summary": decision.summary[:200] or moment.summary,
                })  # fmt: skip
                step.detail = f"{moment.kind} importance {moment.importance}: {moment.summary}"
            except AgentUnavailableError as exc:
                step.status, step.detail = "circuit_open", f"{exc}; baseline used"
                if trigger.kind == "tick":
                    await run.crew.tracer.emit(step)
                    return
            except Exception as exc:  # timeout, model or parse error
                step.status = "timeout" if isinstance(exc, TimeoutError) else "fallback"
                step.detail = f"{type(exc).__name__}; baseline {BASELINE[trigger.kind][0]}"
                if trigger.kind == "tick":
                    await run.crew.tracer.emit(step)
                    return
        if trigger.kind == "card":
            moment = await self._card_importance(moment)
        run.moment = moment
        if moment.kind == "spell":
            run.memory["spell"] = (moment.period, moment.clock_ms)
        await run.crew.store.put_doc(
            "moment", moment.match_id, moment.moment_id, moment.model_dump(mode="json")
        )
        await run.crew.tracer.emit(step)
        await ctx.send_message(moment)

    def _recent_spell(self) -> bool:
        last = self.run.memory.get("spell")
        trig = self.run.trigger
        return (
            last is not None and last[0] == trig.period and trig.clock_ms - last[1] < SPELL_GAP_MS
        )

    async def _card_importance(self, moment: Moment) -> Moment:
        """A red or second yellow outranks a booking; the colour is in match state."""
        state = (await self.run.context()).match_state
        for card in state.get("cards", []):
            if card["event_id"] in moment.evidence_event_ids and card["card_color"] != "yellow":
                return moment.model_copy(update={"importance": max(moment.importance, 0.9)})
        return moment
