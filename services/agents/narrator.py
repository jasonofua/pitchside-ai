"""Narrator (large model): a commentary line for insights, goals and cards, the half-time
story and the full-time recap."""

from __future__ import annotations

from agent_framework import Executor, WorkflowContext, handler

from agents.resilience import AgentUnavailableError
from agents.run import Run
from contracts.agents import Commentary, CommentaryDraft, Story

NAME = "narrator"
TASK = "Write the commentary for this moment."
ALWAYS = frozenset({"goal", "card", "half_time", "full_time"})


def commentary_kind(moment_kind: str) -> str:
    return {"half_time": "half_time_story", "full_time": "full_time_recap"}.get(moment_kind, "line")


class Narrator(Executor):
    def __init__(self, run: Run) -> None:
        super().__init__(id=NAME)
        self.run = run

    @handler
    async def on_story(self, story: Story, ctx: WorkflowContext[Story]) -> None:
        run = self.run
        moment = story.moment
        step = run.step(NAME)
        commentary: Commentary | None = None
        if story.insight is None and moment.kind not in ALWAYS:
            step.status, step.detail = "skipped", "no insight to narrate"
        else:
            kind = commentary_kind(moment.kind)
            payload = {
                "moment": moment.model_dump(mode="json", exclude_none=True),
                "insight": story.insight.model_dump(mode="json") if story.insight else None,
                "commentary_kind": kind,
            }
            try:
                with run.crew.tracer.span(step):
                    draft, record = await run.crew.run(
                        NAME, TASK, payload, CommentaryDraft, step, on_slow=run.template_cards
                    )
                run.recorded.extend(record.payloads())
                commentary = Commentary(
                    commentary_id=f"c:{moment.moment_id}",
                    moment_id=moment.moment_id,
                    match_id=moment.match_id,
                    trace_id=moment.trace_id,
                    kind=kind,
                    text=draft.text[:900],
                    stats_cited=draft.stats_cited[:8],
                )
                step.detail = commentary.text[:200]
                await run.crew.store.put_doc(
                    "commentary", moment.match_id, commentary.commentary_id,
                    commentary.model_dump(mode="json"),
                )  # fmt: skip
            except AgentUnavailableError as exc:
                # The chaos switch lands here: viewers keep their stats-only cards.
                step.status, step.detail = "circuit_open", f"{exc}; stats-only cards stay up"
                await run.template_cards()
            except Exception as exc:
                step.status = "timeout" if isinstance(exc, TimeoutError) else "error"
                step.detail = f"{type(exc).__name__}: {exc}"[:500]
                await run.template_cards()
        await run.crew.tracer.emit(step)
        if story.insight is None and commentary is None:
            return  # nothing explained: the stats-only cards are the final word
        update = {"commentary": commentary} if commentary else {}
        await ctx.send_message(story.model_copy(update=update))
