# Generated from schemas/world.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Crest(BaseModel):
    """
    Parameters for the generated SVG crest in data/crests/.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    shape: Literal["shield", "circle", "hexagon", "diamond"]
    motif: Literal["stripe", "chevron", "star", "wave", "ring"]


class Colors(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    primary: Annotated[str, Field(pattern="^#[0-9A-F]{6}$")]
    secondary: Annotated[str, Field(pattern="^#[0-9A-F]{6}$")]


class Attributes(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    pace: Annotated[int, Field(ge=1, le=99)]
    passing: Annotated[int, Field(ge=1, le=99)]
    finishing: Annotated[int, Field(ge=1, le=99)]
    pressing: Annotated[int, Field(ge=1, le=99)]
    stamina: Annotated[int, Field(ge=1, le=99)]


class Player(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    player_id: Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{2}$")]
    name: Annotated[str, Field(min_length=1)]
    short_name: Annotated[str, Field(min_length=1)]
    shirt_number: Annotated[int, Field(ge=1, le=99)]
    position: Literal[
        "GK", "RB", "CB", "LB", "RWB", "LWB", "DM", "CM", "AM", "RM", "LM", "RW", "LW", "ST"
    ]
    attributes: Attributes


class Club(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    team_id: Annotated[str, Field(pattern="^[A-Z]{3}$")]
    name: Annotated[str, Field(min_length=1)]
    short_name: Annotated[str, Field(min_length=1)]
    city: Annotated[str, Field(min_length=1)]
    colors: Colors
    crest: Crest
    formation: Literal["4-3-3", "4-4-2", "4-2-3-1", "3-5-2"]
    starting_xi: Annotated[list[str], Field(max_length=11, min_length=11)]
    """
    Player ids in formation slot order (see services/sim/formation.py).
    """
    players: Annotated[list[Player], Field(max_length=18, min_length=18)]


class World(BaseModel):
    """
    The fictional football world: invented clubs, squads and crests. Nothing here may reference a real club, league, player or broadcaster.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Annotated[int, Field(ge=1)]
    clubs: Annotated[list[Club], Field(max_length=4, min_length=2)]
