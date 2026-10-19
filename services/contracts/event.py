# Generated from schemas/event.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class MatchEvent(BaseModel):
    """
    One on-ball or match-control event from the synthetic match engine. Coordinates are in metres on a 105 x 68 pitch, relative to the acting team (team_id) attacking left to right: x=0 is their own goal line, x=105 the opponent's, y=0 is the touchline on their left. See docs/DECISIONS.md.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    event_id: Annotated[str, Field(pattern="^[0-9A-HJKMNP-TV-Z]{26}$")]
    """
    ULID, unique and lexicographically sortable in emission order.
    """
    match_id: Annotated[str, Field(min_length=1)]
    seq: Annotated[int, Field(ge=0)]
    """
    Strictly increasing per match, starting at 0.
    """
    clock_ms: Annotated[int, Field(ge=0, le=7200000)]
    """
    Displayed match clock in ms. Period 2 starts at 2700000 (45:00); stoppage time runs past 45:00 / 90:00.
    """
    period: Literal[1, 2]
    type: Literal[
        "pass",
        "carry",
        "shot",
        "tackle",
        "interception",
        "pressure",
        "foul",
        "card",
        "substitution",
        "goal",
        "possession_change",
        "out_of_play",
        "kickoff",
        "period_end",
    ]
    team_id: Annotated[str | None, Field(min_length=1)] = None
    """
    Acting team. Absent only for period_end.
    """
    player_id: Annotated[str | None, Field(min_length=1)] = None
    """
    Acting player. For substitution, the player leaving the pitch. Absent only for period_end.
    """
    x: Annotated[float, Field(ge=0.0, le=105.0)]
    y: Annotated[float, Field(ge=0.0, le=68.0)]
    end_x: Annotated[float | None, Field(ge=0.0, le=105.0)] = None
    end_y: Annotated[float | None, Field(ge=0.0, le=68.0)] = None
    outcome: (
        Literal["complete", "incomplete", "saved", "blocked", "off_target", "won", "lost"] | None
    ) = None
    """
    For shots, 'complete' means the shot was scored (a goal event follows).
    """
    under_pressure: bool
    """
    True when an opponent applied pressure on the actor immediately before this event.
    """
    ball_speed_kmh: Annotated[float | None, Field(ge=0.0, le=200.0)] = None
    """
    Initial ball speed for passes and shots.
    """
    recipient_id: Annotated[str | None, Field(min_length=1)] = None
    """
    Intended receiver of a pass, or the player coming on for a substitution.
    """
    body_part: Literal["right_foot", "left_foot", "head", "other"] | None = None
    card_color: Literal["yellow", "second_yellow", "red"] | None = None
