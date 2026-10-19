"""Ball and player kinematics shared by the event engine and the tracking model."""

from __future__ import annotations

import math

# Average speed over a flight as a fraction of the initial ball speed.
PASS_DRAG = 0.78
SHOT_DRAG = 0.85


def flight_ms(distance_m: float, speed_kmh: float, drag: float) -> float:
    return 1000 * distance_m / (speed_kmh / 3.6 * drag)


def carry_speed_ms(pace: int) -> float:
    """Dribbling speed in m/s."""
    return 3.2 + 0.045 * pace


def top_speed_ms(pace: int) -> float:
    """Sprint speed in m/s: about 25 km/h at pace 50 and 35 km/h at pace 99."""
    return 6.9 + 2.8 * (pace - 50) / 49


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)
