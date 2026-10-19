# Generated from schemas/overlay.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type EvidenceEventId = Annotated[str, Field(pattern="^[0-9A-HJKMNP-TV-Z]{26}$")]


class StatItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: Annotated[str, Field(min_length=1)]
    value: float | str
    unit: str | None = None


class OverlayCard(BaseModel):
    """
    A timed, renderer-agnostic overlay card emitted by the Producer agent. Any broadcast renderer can consume it.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    overlay_id: Annotated[str, Field(min_length=1)]
    match_id: Annotated[str, Field(min_length=1)]
    clock_ms: Annotated[int, Field(ge=0, le=7200000)]
    """
    Match clock at which the card should appear.
    """
    slot: Literal["lower_third", "corner_bug", "player_tag", "full_card", "ticker"]
    priority: Annotated[int, Field(ge=1, le=5)]
    """
    1 = lowest, 5 = must show now.
    """
    ttl_ms: Annotated[int, Field(ge=0)]
    """
    How long the card stays valid after clock_ms.
    """
    audience_profile_hash: Annotated[str, Field(min_length=1)]
    """
    Hash of the personalization profile this card was written for.
    """
    lang: Literal["en", "pcm", "yo", "fr", "es"]
    """
    en = English, pcm = Nigerian Pidgin, yo = Yoruba, fr = French, es = Spanish.
    """
    title: Annotated[str, Field(max_length=120, min_length=1)]
    body: Annotated[str, Field(max_length=600)]
    stats: list[StatItem]
    evidence_event_ids: list[EvidenceEventId]
    trace_id: Annotated[str, Field(min_length=1)]
    kind: Annotated[str | None, Field(min_length=1)] = None
    """
    What kind of moment the card is about (goal, big_chance, speed_burst, ...), for renderers that style by kind.
    """
    player_id: Annotated[str | None, Field(pattern="^[A-Z]{3}-[0-9]{2}$")] = None
    """
    The player a player_tag (or Player Cam card) is attached to.
    """
    team_id: Annotated[str | None, Field(pattern="^[A-Z]{3}$")] = None
    """
    The club the card is about, for club colours.
    """
    source: Literal["agent", "template"] | None = None
    """
    agent: written by the agent crew. template: the stats-only fallback.
    """
