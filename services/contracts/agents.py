# Generated from schemas/agents.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type Ulid = Annotated[str, Field(pattern="^[0-9A-HJKMNP-TV-Z]{26}$")]


class Moment(BaseModel):
    """
    Output of the Moment Detector.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    moment_id: Annotated[str, Field(min_length=1)]
    match_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    trigger_id: Annotated[str, Field(min_length=1)]
    kind: Literal[
        "goal",
        "big_chance",
        "card",
        "speed_burst",
        "hard_pass",
        "momentum_swing",
        "spell",
        "half_time",
        "full_time",
    ]
    period: Literal[1, 2]
    clock_ms: Annotated[int, Field(ge=0)]
    minute: str
    importance: Annotated[float, Field(ge=0.0, le=1.0)]
    team_id: str | None = None
    player_id: str | None = None
    summary: Annotated[str, Field(max_length=200)]
    """
    One factual line, no numbers beyond the trigger's own value.
    """
    evidence_event_ids: list[Ulid]


class StatCitation(BaseModel):
    """
    A number an agent used, with where it came from.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    label: Annotated[str, Field(min_length=1)]
    value: float | str
    unit: str | None = None
    source: str
    """
    MCP tool and field, e.g. 'get_team_stats.LAG.possession_pct'.
    """


class Insight(BaseModel):
    """
    Output of the Tactical Analyst.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    insight_id: Annotated[str, Field(min_length=1)]
    moment_id: Annotated[str, Field(min_length=1)]
    match_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    headline: Annotated[str, Field(max_length=120, min_length=1)]
    why_it_matters: Annotated[str, Field(max_length=500, min_length=1)]
    stats_cited: list[StatCitation]
    team_id: str | None = None
    player_id: str | None = None


class Commentary(BaseModel):
    """
    Output of the Narrator.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    commentary_id: Annotated[str, Field(min_length=1)]
    moment_id: Annotated[str, Field(min_length=1)]
    match_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    kind: Literal["line", "half_time_story", "full_time_recap"]
    text: Annotated[str, Field(max_length=900, min_length=1)]
    stats_cited: list[StatCitation]


class Mismatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    cited: str
    """
    The figure as written in the card.
    """
    expected: str | None = None
    """
    What match state says, if known.
    """
    reason: str


class FactCheck(BaseModel):
    """
    Output of the Fact Checker.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    draft_id: Annotated[str, Field(min_length=1)]
    verdict: Literal["pass", "reject"]
    numbers_checked: Annotated[int, Field(ge=0)]
    mismatches: list[Mismatch]


class StatItem(BaseModel):
    """
    Same shape as the overlay contract's StatItem.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    label: Annotated[str, Field(min_length=1)]
    value: float | str
    unit: str | None = None


class Story(BaseModel):
    """
    What flows from the Narrator to the Fan Lens: the moment, plus the insight and commentary when they exist.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    moment: Moment
    insight: Insight | None = None
    commentary: Commentary | None = None


class MomentDecision(BaseModel):
    """
    Structured output of the Moment Detector model.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    is_moment: bool
    kind: Literal[
        "goal",
        "big_chance",
        "card",
        "speed_burst",
        "hard_pass",
        "momentum_swing",
        "spell",
        "half_time",
        "full_time",
    ]
    importance: Annotated[float, Field(ge=0.0, le=1.0)]
    summary: Annotated[str, Field(max_length=200)]


class InsightDraft(BaseModel):
    """
    Structured output of the Tactical Analyst model.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    headline: Annotated[str, Field(max_length=120)]
    why_it_matters: Annotated[str, Field(max_length=500)]
    stats_cited: list[StatCitation]


class CommentaryDraft(BaseModel):
    """
    Structured output of the Narrator model.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    text: Annotated[str, Field(max_length=900)]
    stats_cited: list[StatCitation]


class CardText(BaseModel):
    """
    Structured output of the Fan Lens and Localizer models.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    title: Annotated[str, Field(max_length=120)]
    body: Annotated[str, Field(max_length=600)]
    stats: Annotated[list[StatItem], Field(max_length=4)]


class ClaimCheck(BaseModel):
    """
    Structured output of the Fact Checker model (qualitative claims; numbers are checked in code).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    verdict: Literal["pass", "reject"]
    reason: Annotated[str, Field(max_length=300)]


class ProducerPlan(BaseModel):
    """
    Structured output of the Producer model: where and how long a card shows.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    slot: Literal["lower_third", "corner_bug", "player_tag", "full_card", "ticker"]
    priority: Annotated[int, Field(ge=1, le=5)]
    ttl_s: Annotated[int, Field(ge=4, le=60)]


class AgentTrace(BaseModel):
    """
    One step of the agent workflow, as shown in the Director panel's live trace. The $defs are the typed messages agents hand to each other; every handoff carries trace_id and moment_id.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    trace_id: Annotated[str, Field(min_length=1)]
    match_id: Annotated[str, Field(min_length=1)]
    moment_id: str | None = None
    agent: Literal[
        "moment_detector",
        "tactical_analyst",
        "narrator",
        "fan_lens",
        "localizer",
        "fact_checker",
        "producer",
    ]
    model: str
    """
    Deployment used: the large or small model name, 'code' for deterministic steps, or 'mock' offline.
    """
    status: Literal[
        "ok",
        "skipped",
        "timeout",
        "error",
        "fallback",
        "rejected",
        "regenerated",
        "circuit_open",
        "dropped",
    ]
    latency_ms: Annotated[int, Field(ge=0)]
    clock_ms: Annotated[int, Field(ge=0)]
    """
    Match clock when the step finished.
    """
    at: str
    """
    Wall-clock ISO 8601 time the step finished.
    """
    detail: Annotated[str | None, Field(max_length=500)] = None
    tools: list[str] | None = None
    """
    MCP tools the agent called.
    """
    profile_hash: str | None = None


class CardDraft(BaseModel):
    """
    A profile-specific card from the Fan Lens, localised by the Localizer, checked by the Fact Checker.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    draft_id: Annotated[str, Field(min_length=1)]
    moment_id: Annotated[str, Field(min_length=1)]
    match_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    profile_hash: Annotated[str, Field(min_length=1)]
    mode: Literal["analyst", "casual", "player_cam", "kids"]
    lang: Literal["en", "pcm", "yo", "fr", "es"]
    kind: Literal[
        "goal",
        "big_chance",
        "card",
        "speed_burst",
        "hard_pass",
        "momentum_swing",
        "spell",
        "half_time",
        "full_time",
    ]
    title: Annotated[str, Field(max_length=120, min_length=1)]
    body: Annotated[str, Field(max_length=600)]
    stats: list[StatItem]
    evidence_event_ids: list[Ulid]
    importance: Annotated[float, Field(ge=0.0, le=1.0)]
    player_id: str | None = None
    team_id: str | None = None
    source: Literal["agent", "template"]
    """
    agent: written by models. template: the stats-only fallback.
    """
    replaces: str | None = None
    """
    draft_id of a template card this upgraded card replaces.
    """
