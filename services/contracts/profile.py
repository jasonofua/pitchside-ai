# Generated from schemas/profile.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Profile(BaseModel):
    """
    A viewer's personalization profile, set in the onboarding sheet, kept in the browser and sent with the WebSocket subscription. Cards are written per profile hash.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Literal["analyst", "casual", "player_cam", "kids"]
    """
    analyst: dense, tactical. casual: short, emotional, no jargon. player_cam: everything about one player. kids: simple and upbeat.
    """
    language: Literal["en", "pcm", "yo", "fr", "es"]
    """
    en = English, pcm = Nigerian Pidgin, yo = Yoruba, fr = French, es = Spanish.
    """
    favorite_club: Annotated[str | None, Field(pattern="^[A-Z]{3}$")] = None
    favorite_player: Annotated[str | None, Field(pattern="^[A-Z]{3}-[0-9]{2}$")] = None
    focus_metric: (
        Literal[
            "shot_speed", "top_speed", "distance", "possession", "xg", "pass_accuracy", "momentum"
        ]
        | None
    ) = None
    """
    The one stat shown in a persistent bug.
    """
