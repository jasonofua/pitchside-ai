"""Tactical Analyst (large model): why the moment matters, grounded in MCP stats.

Runs for moments of importance 0.5+ and for momentum swings of 30+ points. Without an
insight the moment still reaches the Narrator for goals and cards; template cards cover the
screen either way.
"""

from __future__ import annotations

from agent_framework import Executor, WorkflowContext, handler

from agents.resilience import AgentUnavailableError
from agents.run import Run
from contracts.agents import Insight, InsightDraft, Moment, Story

NAME = "tactical_analyst"
TASK = "Explain why this moment matters, using only numbers from the Match Stats tools."
MIN_IMPORTANCE = 0.5
MIN_SWING = 30.0


def wants_insight(moment: Moment, swing: float | None) -> bool:
    if moment.importance >= MIN_IMPORTANCE:
        return True
    return moment.kind == "momentum_swing" and swing is not None and abs(swing) >= MIN_SWING


class TacticalAnalyst(Executor):
    def __init__(self, run: Run) -> None:
        super().__init__(id=NAME)
        self.run = run

    @handler
    async def on_moment(self, moment: Moment, ctx: WorkflowContext[Story]) -> None:
        run = self.run
        step = run.step(NAME)
        insight: Insight | None = None
        if not wants_insight(moment, run.trigger.value):
            step.status, step.detail = "skipped", f"importance {moment.importance} below 0.5"
        else:
            payload = {"moment": moment.model_dump(mode="json", exclude_none=True)}
            try:
                with run.crew.tracer.span(step):
                    draft, record = await run.crew.run(
                        NAME, TASK, payload, InsightDraft, step, on_slow=run.template_cards
                    )
                run.recorded.extend(record.payloads())
                optional = {k: v for k, v in (("team_id", moment.team_id),
                                              ("player_id", moment.player_id)) if v}  # fmt: skip
                insight = Insight(
                    insight_id=f"i:{moment.moment_id}",
                    moment_id=moment.moment_id,
                    match_id=moment.match_id,
                    trace_id=moment.trace_id,
                    headline=draft.headline[:120] or moment.summary[:120],
                    why_it_matters=draft.why_it_matters[:500] or moment.summary,
                    stats_cited=draft.stats_cited[:8],
                    **optional,
                )
                step.detail = insight.headline
                await run.crew.store.put_doc(
                    "insight", moment.match_id, insight.insight_id, insight.model_dump(mode="json")
                )
            except AgentUnavailableError as exc:
                step.status, step.detail = "circuit_open", str(exc)
            except Exception as exc:
                step.status = "timeout" if isinstance(exc, TimeoutError) else "error"
                step.detail = f"{type(exc).__name__}: {exc}"[:500]
        await run.crew.tracer.emit(step)
        await ctx.send_message(Story(moment=moment, **({"insight": insight} if insight else {})))
