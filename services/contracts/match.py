# Generated from schemas/match.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class MatchInfo(BaseModel):
    """
    Metadata for one simulated match, published before kickoff so downstream services know which team is home (tracking frames are in the home team's frame).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    match_id: Annotated[str, Field(min_length=1)]
    home: Annotated[str, Field(pattern="^[A-Z]{3}$")]
    away: Annotated[str, Field(pattern="^[A-Z]{3}$")]
    scenario: Annotated[str, Field(min_length=1)]
    seed: int
    speed: Annotated[float, Field(ge=0.0)]
    """
    Match-clock speed multiplier; 0 means unpaced.
    """
    status: Literal["scheduled", "live", "half_time", "full_time", "aborted"]
    created_at: str | None = None
    """
    ISO 8601 wall-clock time the match was started.
    """
