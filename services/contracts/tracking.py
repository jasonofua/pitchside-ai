# Generated from schemas/tracking.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class PlayerPosition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    player_id: Annotated[str, Field(min_length=1)]
    x: Annotated[float, Field(ge=0.0, le=105.0)]
    y: Annotated[float, Field(ge=0.0, le=68.0)]


class BallPosition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    x: Annotated[float, Field(ge=0.0, le=105.0)]
    y: Annotated[float, Field(ge=0.0, le=68.0)]


class TrackingFrame(BaseModel):
    """
    Positions of every on-pitch player and the ball, sampled at 5 Hz. Unlike events, coordinates are absolute: the home team attacks left to right (towards x=105) for the whole match.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    match_id: Annotated[str, Field(min_length=1)]
    clock_ms: Annotated[int, Field(ge=0, le=7200000)]
    """
    Displayed match clock in ms, on a 200 ms grid.
    """
    period: Literal[1, 2]
    """
    Needed because stoppage time in period 1 overlaps the period 2 clock.
    """
    players: Annotated[list[PlayerPosition], Field(max_length=22)]
    ball: BallPosition
