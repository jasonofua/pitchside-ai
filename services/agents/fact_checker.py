"""Fact Checker (small model + code): no card reaches a viewer with a number match state
does not back.

Code checks every figure (percentages, speeds, distances, xG, minutes, scorelines, counts)
against MCP results; the model checks the words around them. A rejected card gets one
regeneration with the correction in context; if that fails too, the viewer gets the
stats-only template card.
"""

from __future__ import annotations

from agent_framework import Executor, WorkflowContext, handler

from agents.fan_lens import write_card
from agents.localizer import localize
from agents.numbers import check_text, corrupt_first_figure
from agents.resilience import AgentUnavailableError
from agents.run import Run
from contracts.agents import CardDraft, ClaimCheck, FactCheck

NAME = "fact_checker"
TASK = "Check this card's claims against match state."


async def numbers_check(run: Run, draft: CardDraft) -> FactCheck:
    facts = await run.facts()
    checked, mismatches = 0, []
    for text in (draft.title, draft.body, *(f"{s.value}{s.unit}" for s in draft.stats)):
        n, bad = check_text(text, facts)
        checked += n
        mismatches.extend(bad)
    return FactCheck(
        draft_id=draft.draft_id,
        verdict="reject" if mismatches else "pass",
        numbers_checked=checked,
        mismatches=mismatches,
    )


async def claims_check(run: Run, draft: CardDraft, step_detail: list[str]) -> ClaimCheck:
    """The model's half; a model failure passes the card (numbers are already verified)."""
    ctx = await run.context()
    payload = {
        "card": {"title": draft.title, "body": draft.body, "lang": draft.lang,
                 "stats": [s.model_dump() for s in draft.stats]},
        "match_state": ctx.match_state,
        "team_stats": ctx.team_stats,
    }  # fmt: skip
    step = run.step(NAME, draft.profile_hash)
    try:
        with run.crew.tracer.span(step):
            verdict, _ = await run.crew.run(NAME, TASK, payload, ClaimCheck, step)
        return verdict
    except Exception as exc:
        step_detail.append(f"claim check skipped ({type(exc).__name__})")
        return ClaimCheck(verdict="pass", reason="claim check unavailable")


def correction_note(check: FactCheck, claim: ClaimCheck | None) -> str:
    parts = [
        f"'{m.cited}' is wrong"
        + (f" (match state: {m.expected})" if m.expected else "")
        + f": {m.reason}"
        for m in check.mismatches
    ]
    if claim is not None and claim.verdict == "reject":
        parts.append(claim.reason)
    return "; ".join(parts) or "Use only figures from the tools."


class FactChecker(Executor):
    def __init__(self, run: Run) -> None:
        super().__init__(id=NAME)
        self.run = run

    async def _check(self, draft: CardDraft) -> tuple[FactCheck, ClaimCheck | None, list[str]]:
        notes: list[str] = []
        check = await numbers_check(self.run, draft)
        claim = None
        if check.verdict == "pass" and draft.source == "agent":
            claim = await claims_check(self.run, draft, notes)
        return check, claim, notes

    @handler
    async def on_draft(self, draft: CardDraft, ctx: WorkflowContext[CardDraft]) -> None:
        run = self.run
        if draft.source == "agent" and run.crew.chaos.take_wrong_number():
            # The Director panel's fault injection: pretend a writer got a number wrong.
            wrong = corrupt_first_figure(draft.body, await run.facts())
            draft = draft.model_copy(update={"body": wrong})
        step = run.step(NAME, draft.profile_hash)
        step.model = f"code+{run.crew.model_name(NAME)}"
        check, claim, notes = await self._check(draft)
        rejected = check.verdict == "reject" or (claim is not None and claim.verdict == "reject")
        if not rejected:
            step.detail = f"pass: {check.numbers_checked} figures checked" + (
                f"; {'; '.join(notes)}" if notes else ""
            )
            await run.crew.tracer.emit(step)
            await ctx.send_message(draft)
            return

        step.status = "rejected"
        note = correction_note(check, claim)
        step.detail = f"reject: {note}"[:500]
        await run.crew.tracer.emit(step)
        if draft.source == "template":  # cannot happen with honest templates; drop it
            return
        fixed = await self._regenerate(draft, note)
        if fixed is not None:
            await ctx.send_message(fixed)
            return
        profile = run.profiles[draft.profile_hash]
        template = run.template_for(draft.profile_hash, await run.context(profile.favorite_player))
        fallback = run.step(NAME, draft.profile_hash)
        fallback.status, fallback.model = "fallback", "code"
        fallback.detail = "second check failed: stats-only card instead"
        await run.crew.tracer.emit(fallback)
        await ctx.send_message(template)

    async def _regenerate(self, draft: CardDraft, note: str) -> CardDraft | None:
        run = self.run
        story = run.story
        if story is None:
            return None
        profile = run.profiles[draft.profile_hash]
        try:
            again = await write_card(run, story, profile, draft.profile_hash, correction=note)
            again = await localize(run, again)
        except (AgentUnavailableError, Exception):
            return None
        check, claim, _ = await self._check(again)
        step = run.step(NAME, draft.profile_hash)
        step.model = f"code+{run.crew.model_name(NAME)}"
        ok = check.verdict == "pass" and (claim is None or claim.verdict == "pass")
        step.status = "regenerated" if ok else "rejected"
        step.detail = (
            f"pass after regeneration: {check.numbers_checked} figures checked"
            if ok
            else f"still wrong: {correction_note(check, claim)}"
        )[:500]
        await run.crew.tracer.emit(step)
        return again if ok else None
