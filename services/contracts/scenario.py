# Generated from schemas/scenario.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type RangeItem = Annotated[int, Field(ge=0)]


class Modifiers(BaseModel):
    """
    Multipliers on the engine's team model; 1.0 is neutral. Unset fields keep their current value.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    attack: Annotated[float | None, Field(ge=0.1, le=5.0)] = None
    press: Annotated[float | None, Field(ge=0.1, le=5.0)] = None
    fatigue: Annotated[float | None, Field(ge=0.1, le=5.0)] = None
    composure: Annotated[float | None, Field(ge=0.1, le=5.0)] = None


class StoppageS(BaseModel):
    """
    Override the stoppage-time range per period, in seconds.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    p1: Annotated[list[RangeItem] | None, Field(max_length=2, min_length=2)] = None
    p2: Annotated[list[RangeItem] | None, Field(max_length=2, min_length=2)] = None


class Beat(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    at: Annotated[str, Field(pattern="^[0-9]{1,2}(\\+[0-9]{1,2})?$")]
    """
    Match minute the beat lands on: '71' means 71:00, '90+2' means 92:00 in second-half stoppage.
    """
    kind: Literal["goal", "red_card", "modifiers"]
    """
    goal: the team scores at (or just after) `at`. red_card: the team's next foul from `at` is a straight red. modifiers: from `at`, the team plays with these multipliers.
    """
    team: Literal["home", "away", "favourite", "underdog"]
    """
    A venue, or a story role resolved through `favourite`.
    """
    modifiers: Modifiers | None = None
    note: str | None = None


class Scenario(BaseModel):
    """
    A scenario script (services/sim/scenarios/*.yaml) that injects story beats at set minutes so a demo match has a narrative arc.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-z][a-z0-9_]*$")]
    description: Annotated[str, Field(min_length=1)]
    home: Annotated[str | None, Field(pattern="^[A-Z]{3}$")] = None
    """
    Default home club when the CLI does not pass --home.
    """
    away: Annotated[str | None, Field(pattern="^[A-Z]{3}$")] = None
    favourite: Literal["home", "away"] | None = None
    """
    Which side the story treats as the favourite; the other side is the underdog.
    """
    scoring: Literal["free", "scripted"]
    """
    free: shots score by the usual model. scripted: only goal beats score; every other shot that would have scored is saved.
    """
    stoppage_s: StoppageS | None = None
    """
    Override the stoppage-time range per period, in seconds.
    """
    beats: list[Beat]
