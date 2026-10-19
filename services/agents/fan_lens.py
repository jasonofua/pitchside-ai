"""Fan Lens (small model): one card per active viewer profile, in English.

Fans out over the profiles watching the match (analyst, casual, Player Cam, kids; club and
player focus). A viewer whose card cannot be written gets the stats-only template in their
own language instead, which skips the Localizer.
"""

from __future__ import annotations

import asyncio

from agent_framework import Executor, WorkflowContext, handler

from agents.resilience import AgentUnavailableError
from agents.run import Run
from contracts import Profile
from contracts.agents import CardDraft, CardText, StatItem, Story

NAME = "fan_lens"
TASK = "Rewrite this explained moment as one overlay card for this viewer."


def to_draft(run: Run, story: Story, profile: Profile, h: str, text: CardText) -> CardDraft:
    moment = story.moment
    player = profile.favorite_player if profile.mode == "player_cam" else moment.player_id
    optional = {k: v for k, v in (("player_id", player), ("team_id", moment.team_id)) if v}
    return CardDraft(
        draft_id=f"{moment.moment_id}:{h}:a",
        moment_id=moment.moment_id,
        match_id=moment.match_id,
        trace_id=moment.trace_id,
        profile_hash=h,
        mode=profile.mode,
        lang="en",
        kind=moment.kind,
        title=text.title[:120] or moment.summary[:120],
        body=text.body[:600],
        stats=[StatItem(label=s.label, value=s.value, unit=s.unit) for s in text.stats[:4]],
        evidence_event_ids=list(moment.evidence_event_ids),
        importance=moment.importance,
        source="agent",
        **optional,
    )


async def write_card(
    run: Run, story: Story, profile: Profile, h: str, correction: str | None = None
) -> CardDraft:
    """The Fan Lens call for one viewer; raises on failure (callers fall back)."""
    step = run.step(NAME, h)
    payload = {
        "story": story.model_dump(mode="json", exclude_none=True),
        "profile": profile.model_dump(exclude_none=True),
        "match_id": story.moment.match_id,
        "trigger": run.trigger.model_dump(mode="json", exclude_none=True),
    }
    task = TASK
    if correction:
        payload["correction"] = correction
        task += " Your previous card failed fact-checking; fix exactly what the correction says."
        step.status = "regenerated"
    try:
        with run.crew.tracer.span(step):
            text, record = await run.crew.run(NAME, task, payload, CardText, step)
        run.recorded.extend(record.payloads())
        draft = to_draft(run, story, profile, h, text)
        step.detail = f"{profile.mode}: {draft.title}"[:500]
        return draft
    except AgentUnavailableError as exc:
        step.status, step.detail = "circuit_open", str(exc)
        raise
    except Exception as exc:
        step.status = "timeout" if isinstance(exc, TimeoutError) else "error"
        step.detail = f"{type(exc).__name__}: {exc}"[:500]
        raise
    finally:
        await run.crew.tracer.emit(step)


class FanLens(Executor):
    def __init__(self, run: Run) -> None:
        super().__init__(id=NAME)
        self.run = run

    @handler
    async def on_story(self, story: Story, ctx: WorkflowContext[CardDraft]) -> None:
        run = self.run
        run.story = story

        async def one(h: str, profile: Profile) -> CardDraft | None:
            try:
                return await write_card(run, story, profile, h)
            except Exception:
                ctx_data = await run.context(profile.favorite_player)
                if not ctx_data.match_state:
                    return None
                return run.template_for(h, ctx_data)

        drafts = await asyncio.gather(*(one(h, p) for h, p in run.profiles.items()))
        for draft in drafts:
            if draft is not None:
                await ctx.send_message(draft)
