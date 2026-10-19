"""Formation templates and role-based target positions.

All coordinates here are team-relative: the team attacks towards x=105, and y=0 is
the touchline on its left. The same target function drives where the event engine
places passes and where tracking steers players, so the two stay consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
CENTRE = (PITCH_LENGTH / 2, PITCH_WIDTH / 2)

FormationName = Literal["4-3-3", "4-4-2", "4-2-3-1", "3-5-2"]


@dataclass(frozen=True, slots=True)
class Slot:
    name: str
    role: str  # one of the world Position values
    x: float  # in-possession base position with the ball on the centre spot
    y: float


FORMATIONS: dict[str, tuple[Slot, ...]] = {
    "4-3-3": (
        Slot("GK", "GK", 6, 34),
        Slot("RB", "RB", 40, 58),
        Slot("RCB", "CB", 27, 44),
        Slot("LCB", "CB", 27, 24),
        Slot("LB", "LB", 40, 10),
        Slot("DM", "DM", 42, 34),
        Slot("RCM", "CM", 55, 45),
        Slot("LCM", "CM", 55, 23),
        Slot("RW", "RW", 74, 60),
        Slot("ST", "ST", 80, 34),
        Slot("LW", "LW", 74, 8),
    ),
    "4-4-2": (
        Slot("GK", "GK", 6, 34),
        Slot("RB", "RB", 38, 58),
        Slot("RCB", "CB", 26, 44),
        Slot("LCB", "CB", 26, 24),
        Slot("LB", "LB", 38, 10),
        Slot("RM", "RM", 62, 58),
        Slot("RCM", "CM", 48, 42),
        Slot("LCM", "CM", 48, 26),
        Slot("LM", "LM", 62, 10),
        Slot("RST", "ST", 78, 40),
        Slot("LST", "ST", 78, 28),
    ),
    "4-2-3-1": (
        Slot("GK", "GK", 6, 34),
        Slot("RB", "RB", 40, 58),
        Slot("RCB", "CB", 27, 44),
        Slot("LCB", "CB", 27, 24),
        Slot("LB", "LB", 40, 10),
        Slot("RDM", "DM", 42, 42),
        Slot("LDM", "DM", 42, 26),
        Slot("RW", "RW", 70, 58),
        Slot("AM", "AM", 64, 34),
        Slot("LW", "LW", 70, 10),
        Slot("ST", "ST", 80, 34),
    ),
    "3-5-2": (
        Slot("GK", "GK", 6, 34),
        Slot("RCB", "CB", 28, 50),
        Slot("CB", "CB", 25, 34),
        Slot("LCB", "CB", 28, 18),
        Slot("RWB", "RWB", 56, 62),
        Slot("RCM", "CM", 52, 44),
        Slot("DM", "DM", 42, 34),
        Slot("LCM", "CM", 52, 24),
        Slot("LWB", "LWB", 56, 6),
        Slot("RST", "ST", 77, 40),
        Slot("LST", "ST", 77, 28),
    ),
}

# Out of possession the block drops this far and narrows by this factor.
DEFENSIVE_DROP_M = 12.0
DEFENSIVE_WIDTH = 0.72


# Attackers stop short of the six-yard box in open play: defenders hold that space.
MAX_ATTACKING_X = 95.0


def clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def target_position(
    slot: Slot, ball_x: float, ball_y: float, in_possession: bool
) -> tuple[float, float]:
    """Where a player in `slot` wants to stand, given the ball in the team's frame."""
    if slot.role == "GK":
        x = clamp(3.0 + 0.1 * ball_x, 2.0, 16.0 if in_possession else 12.0)
        y = CENTRE[1] + 0.12 * (ball_y - CENTRE[1])
        return x, y
    shift = 0.55 * (ball_x - CENTRE[0])
    if in_possession:
        x = min(max(slot.x + shift, 3.0), MAX_ATTACKING_X)
        width = 1.0
    else:
        x = min(max(slot.x - DEFENSIVE_DROP_M + shift, 3.0), 101.0)
        width = DEFENSIVE_WIDTH
    y = CENTRE[1] + (slot.y - CENTRE[1]) * width + 0.28 * (ball_y - CENTRE[1])
    return x, min(max(y, 1.0), PITCH_WIDTH - 1.0)


def kickoff_position(slot: Slot) -> tuple[float, float]:
    """Position at a kickoff: everyone in their own half."""
    if slot.role == "GK":
        return 4.0, CENTRE[1]
    return min(slot.x * 0.62, 49.0), slot.y


def flip(x: float, y: float) -> tuple[float, float]:
    """Convert between the two teams' frames (a 180 degree rotation of the pitch)."""
    return PITCH_LENGTH - x, PITCH_WIDTH - y
