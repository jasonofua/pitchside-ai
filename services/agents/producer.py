"""Producer (large model for planning + code for timing): approved cards become timed
overlay cards on the bus.

The model plans slot, priority and time on screen for important agent cards (importance
0.8+); house rules plan the rest and clamp every plan. Code drops cards whose moment the
match clock has left behind, and gives each upgraded card its template's overlay id so it
replaces the template on screen.
"""

from __future__ import annotations

from typing import Never

from agent_framework import Executor, WorkflowContext, handler

from agents.producer_rules import clamp_plan, rule_plan
from agents.run import Run
from contracts import OverlayCard
from contracts.agents import CardDraft, ProducerPlan

NAME = "producer"
TASK = "Plan where and for how long this approved card appears."
PLAN_WITH_MODEL_FROM = 0.8


class Producer(Executor):
    def __init__(self, run: Run) -> None:
        super().__init__(id=NAME)
        self.run = run

    async def _plan(self, draft: CardDraft) -> tuple[ProducerPlan, str]:
        rules = rule_plan(draft)
        if draft.source != "agent" or draft.importance < PLAN_WITH_MODEL_FROM:
            return rules, "code"
        step = self.run.step(NAME, draft.profile_hash)
        payload = {
            "card": {"kind": draft.kind, "importance": draft.importance, "mode": draft.mode,
                     "title": draft.title, "body": draft.body},
            "suggested": rules.model_dump(),
        }  # fmt: skip
        try:
            with self.run.crew.tracer.span(step):
                plan, _ = await self.run.crew.run(NAME, TASK, payload, ProducerPlan, step)
            return clamp_plan(plan, draft), self.run.crew.model_name(NAME)
        except Exception:
            return rules, "code"

    @handler
    async def on_draft(self, draft: CardDraft, ctx: WorkflowContext[Never, OverlayCard]) -> None:
        run = self.run
        step = run.step(NAME, draft.profile_hash)
        plan, planner = await self._plan(draft)
        step.model = planner
        if await run.is_stale(plan.ttl_s):
            step.status = "dropped"
            step.detail = f"stale: the match clock passed {draft.kind} + {plan.ttl_s}s"
            await run.crew.tracer.emit(step)
            return
        overlay = await run.publish(draft, plan)
        step.detail = (
            f"{overlay.slot} p{overlay.priority} {plan.ttl_s}s {draft.source} {draft.lang}: "
            f"{overlay.title}"
        )[:500]
        await run.crew.tracer.emit(step)
        await ctx.yield_output(overlay)
