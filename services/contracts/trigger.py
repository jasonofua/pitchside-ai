# Generated from schemas/trigger.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type EventId = Annotated[str, Field(pattern="^[0-9A-HJKMNP-TV-Z]{26}$")]


class Trigger(BaseModel):
    """
    Raised by the Stats Engine when a threshold is crossed, a key event happens, or 30 s of match time pass. The Moment Detector runs on every trigger.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    trigger_id: Annotated[str, Field(min_length=1)]
    """
    Deterministic: '<match_id>:<kind>:<seq or frame clock>'.
    """
    match_id: Annotated[str, Field(min_length=1)]
    kind: Literal[
        "speed",
        "pass_difficulty",
        "xg",
        "goal",
        "card",
        "half_time",
        "full_time",
        "momentum_swing",
        "tick",
    ]
    """
    speed: a player above 32 km/h. pass_difficulty: a completed pass above 80. xg: a shot above 0.3 xG. momentum_swing: the Control vs Chaos index moved 30+ points in 5 minutes. tick: 30 s of match time passed.
    """
    seq: Annotated[int, Field(ge=0)]
    """
    seq of the last event the Stats Engine had processed when the trigger fired.
    """
    clock_ms: Annotated[int, Field(ge=0, le=7200000)]
    period: Literal[1, 2]
    team_id: Annotated[str | None, Field(min_length=1)] = None
    player_id: Annotated[str | None, Field(min_length=1)] = None
    value: float | None = None
    """
    The measured value, e.g. 33.4 for a 33.4 km/h sprint.
    """
    threshold: float | None = None
    unit: str | None = None
    event_ids: list[EventId]
    """
    Evidence: the events behind the trigger (most recent last).
    """
