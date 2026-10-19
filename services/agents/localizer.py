"""Localizer (small model): the Fan Lens card in the viewer's language (en, pcm, yo, fr,
es). Numbers, names and units must come through unchanged; the Fact Checker checks."""

from __future__ import annotations

from agent_framework import Executor, WorkflowContext, handler

from agents.resilience import AgentUnavailableError
from agents.run import Run
from contracts.agents import CardDraft, CardText, StatItem

NAME = "localizer"
TASK = "Translate this overlay card into the target language."
LANG_NAMES = {
    "en": "English", "pcm": "Nigerian Pidgin", "yo": "Yoruba", "fr": "French", "es": "Spanish",
}  # fmt: skip


async def localize(run: Run, draft: CardDraft) -> CardDraft:
    """Translate an agent card into its viewer's language; raises on failure."""
    profile = run.profiles[draft.profile_hash]
    target = profile.language
    if target == draft.lang:
        return draft
    step = run.step(NAME, draft.profile_hash)
    payload = {
        "card": {"title": draft.title, "body": draft.body,
                 "stats": [s.model_dump() for s in draft.stats]},
        "language": target,
        "language_name": LANG_NAMES[target],
    }  # fmt: skip
    try:
        with run.crew.tracer.span(step):
            text, _ = await run.crew.run(NAME, TASK, payload, CardText, step)
        step.detail = f"{LANG_NAMES[target]}: {text.title}"[:500]
        return draft.model_copy(update={
            "lang": target,
            "title": text.title[:120] or draft.title,
            "body": text.body[:600],
            "stats": [StatItem(label=s.label, value=s.value, unit=s.unit) for s in text.stats[:4]]
            or draft.stats,
        })  # fmt: skip
    except AgentUnavailableError as exc:
        step.status, step.detail = "circuit_open", str(exc)
        raise
    except Exception as exc:
        step.status = "timeout" if isinstance(exc, TimeoutError) else "error"
        step.detail = f"{type(exc).__name__}: {exc}"[:500]
        raise
    finally:
        await run.crew.tracer.emit(step)


class Localizer(Executor):
    def __init__(self, run: Run) -> None:
        super().__init__(id=NAME)
        self.run = run

    @handler
    async def on_draft(self, draft: CardDraft, ctx: WorkflowContext[CardDraft]) -> None:
        if draft.source == "template":
            await ctx.send_message(draft)  # already in the viewer's language
            return
        try:
            out = await localize(self.run, draft)
        except Exception:
            profile = self.run.profiles[draft.profile_hash]
            ctx_data = await self.run.context(profile.favorite_player)
            out = self.run.template_for(draft.profile_hash, ctx_data)
        await ctx.send_message(out)
