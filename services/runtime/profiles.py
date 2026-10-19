"""Personalization profiles: canonical hashing and the defaults the demo uses."""

from __future__ import annotations

import hashlib
import json

from contracts import Profile

# The Three Fans view: analyst in English, casual fan in Pidgin, Player Cam in Yoruba.
DEMO_PROFILES: tuple[Profile, ...] = (
    Profile(mode="analyst", language="en", focus_metric="xg"),
    Profile(mode="casual", language="pcm", favorite_club="LAG", focus_metric="possession"),
    Profile(
        mode="player_cam",
        language="yo",
        favorite_club="LAG",
        favorite_player="LAG-09",
        focus_metric="top_speed",
    ),
)


def profile_hash(profile: Profile) -> str:
    """Stable 12-hex-digit id for a profile: equal profiles share cards."""
    canonical = json.dumps(profile.model_dump(exclude_none=True), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]
