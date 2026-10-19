"""Loading the fictional world (clubs, squads) from data/world.json."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

from contracts import Club, Player, World

REPO_ROOT = Path(__file__).resolve().parents[2]


def default_world_path() -> Path:
    return Path(os.environ.get("PITCHSIDE_WORLD", REPO_ROOT / "data" / "world.json"))


@cache
def load_world(path: Path | None = None) -> World:
    return World.model_validate_json((path or default_world_path()).read_text())


def club(world: World, team_id: str) -> Club:
    for candidate in world.clubs:
        if candidate.team_id == team_id:
            return candidate
    known = ", ".join(c.team_id for c in world.clubs)
    raise KeyError(f"unknown team {team_id!r}; known teams: {known}")


def players_by_id(world: World) -> dict[str, Player]:
    return {p.player_id: p for c in world.clubs for p in c.players}
