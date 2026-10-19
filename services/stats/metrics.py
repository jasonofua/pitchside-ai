"""Pure metric functions. Every function here has a unit test in tests/test_metrics.py.

Coordinates follow the event convention: metres on a 105 x 68 pitch in the acting team's
frame, attacking towards x=105.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
GOAL_CENTRE = (PITCH_LENGTH, PITCH_WIDTH / 2)
GOAL_HALF_WIDTH = 3.66
BOX_X = 88.5
BOX_Y = (13.84, 54.16)
PENALTY_SPOT = (94.0, 34.0)

# xG: logistic over distance (m) and the angle the goal mouth subtends (rad).
XG_INTERCEPT = -0.6
XG_DISTANCE = -0.16
XG_ANGLE = 1.0
XG_PENALTY = 0.76
XG_HEADER_FACTOR = 0.5
XG_PRESSURE_FACTOR = 0.75
XG_FREE_KICK_FACTOR = 0.6

SPRINT_KMH = 25.2  # 7 m/s
SPRINT_MIN_MS = 1000

# PPDA zone: the opponent's first 60% of the pitch, i.e. x >= 42 in the pressing team's frame.
PPDA_ZONE_X = 0.4 * PITCH_LENGTH


def clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def flip(x: float, y: float) -> tuple[float, float]:
    """Convert a point between the two teams' frames (a 180 degree rotation)."""
    return PITCH_LENGTH - x, PITCH_WIDTH - y


def in_box(x: float, y: float) -> bool:
    return x >= BOX_X and BOX_Y[0] <= y <= BOX_Y[1]


def goal_angle(x: float, y: float) -> float:
    """Angle in radians that the goal mouth subtends from (x, y)."""
    dx, dy = PITCH_LENGTH - x, abs(y - GOAL_CENTRE[1])
    angle = math.atan2(2 * GOAL_HALF_WIDTH * dx, dx * dx + dy * dy - GOAL_HALF_WIDTH**2)
    return angle + math.pi if angle < 0 else angle


def shot_distance(x: float, y: float) -> float:
    return math.hypot(PITCH_LENGTH - x, GOAL_CENTRE[1] - y)


def xg(
    x: float,
    y: float,
    *,
    header: bool = False,
    under_pressure: bool = False,
    free_kick: bool = False,
    penalty: bool = False,
) -> float:
    """Expected goals for a shot from (x, y): distance + angle logistic model.

    Coefficients match the synthetic world's average finisher, so a season of xG tracks a
    season of goals. Headers, shots under pressure and direct free kicks are discounted.
    """
    if penalty:
        return XG_PENALTY
    z = XG_INTERCEPT + XG_DISTANCE * shot_distance(x, y) + XG_ANGLE * goal_angle(x, y)
    p = 1 / (1 + math.exp(-z))
    if header:
        p *= XG_HEADER_FACTOR
    if under_pressure:
        p *= XG_PRESSURE_FACTOR
    if free_kick:
        p *= XG_FREE_KICK_FACTOR
    return clamp(p, 0.0, 0.99)


def opponents_bypassed(
    start_x: float, end_x: float, opponents_x: Iterable[float], margin: float = 2.0
) -> int:
    """Opponents (x in the passer's frame) strictly between the start and end of a pass."""
    if end_x - start_x <= 2 * margin:
        return 0
    return sum(1 for ox in opponents_x if start_x + margin < ox < end_x - margin)


def is_line_breaking(forward_m: float, bypassed: int | None) -> bool:
    """A pass breaks a line if it goes 10 m+ forward past 3+ opponents.

    Without tracking (bypassed is None) a 20 m+ forward pass counts.
    """
    if bypassed is None:
        return forward_m >= 20
    return forward_m >= 10 and bypassed >= 3


def pass_difficulty(
    distance_m: float,
    under_pressure: bool,
    bypassed: int | None,
    forward_m: float,
    receiver_space_m: float | None,
) -> float:
    """Pass difficulty on a 0-100 scale, 1 dp.

    - distance: up to 30 points, linear to 40 m
    - pressure on the passer: 20 points
    - line-breaking: up to 25 points, from opponents bypassed (5+ = full marks)
    - receiver tightness: up to 25 points, from the space around the target
      (1.5 m or less = full marks, 9 m or more = none)

    Without tracking, bypassed and receiver_space_m are None: line-breaking falls back to
    forward distance and tightness scores a neutral half.
    """
    score = 30 * clamp(distance_m / 40, 0.0, 1.0)
    if under_pressure:
        score += 20
    if bypassed is None:
        score += 15 if is_line_breaking(forward_m, None) else 0
    elif forward_m > 0:
        score += 25 * clamp(bypassed / 5, 0.0, 1.0)
    if receiver_space_m is None:
        score += 12.5
    else:
        score += 25 * clamp((9 - receiver_space_m) / 7.5, 0.0, 1.0)
    return round(clamp(score, 0.0, 100.0), 1)


def pass_accuracy_pct(completed: int, attempted: int) -> float | None:
    if attempted == 0:
        return None
    return round(100 * completed / attempted, 1)


def possession_pct(own_ms: float, other_ms: float) -> float:
    """Share of ball-in-play time. An even split before any play."""
    total = own_ms + other_ms
    if total <= 0:
        return 50.0
    return round(100 * own_ms / total, 1)


def ppda(opponent_passes: int, defensive_actions: int) -> float | None:
    """Passes allowed per defensive action; None when there were no defensive actions."""
    if defensive_actions == 0:
        return None
    return round(opponent_passes / defensive_actions, 1)


def in_ppda_zone(x_pressing_frame: float) -> bool:
    return x_pressing_frame >= PPDA_ZONE_X


def speed_kmh(dx: float, dy: float, dt_ms: float) -> float:
    if dt_ms <= 0:
        return 0.0
    return math.hypot(dx, dy) / (dt_ms / 1000) * 3.6


def smoothed(values: Sequence[float]) -> float:
    """Mean of the values (used over the last three 5 Hz speed samples)."""
    return sum(values) / len(values) if values else 0.0


def count_sprints(speeds_kmh: Iterable[float], dt_ms: float = 200) -> int:
    """Runs of SPRINT_KMH or faster lasting at least SPRINT_MIN_MS."""
    sprints, run_ms, counted = 0, 0.0, False
    for v in speeds_kmh:
        if v >= SPRINT_KMH:
            run_ms += dt_ms
            if run_ms >= SPRINT_MIN_MS and not counted:
                sprints += 1
                counted = True
        else:
            run_ms, counted = 0.0, False
    return sprints


# ---------------------------------------------------------------- Control vs Chaos

# Baselines and scales are calibrated on 5-minute windows of default-scenario matches
# (scripts/calibrate_momentum.py): baseline is the median, scale about five standard
# deviations, so a typical window scores near 0 and only sustained shifts reach +/-50.
STABILITY_BASELINE = 3.3  # completed passes per possession
STABILITY_SCALE = 6.5
TURNOVER_BASELINE = 3.1  # turnovers per minute of ball-in-play time
TURNOVER_SCALE = 4.4
PRESSURE_BASELINE = 5.4  # pressure events per minute of ball-in-play time
PRESSURE_SCALE = 5.6
TEMPO_BASELINE = 123.0  # metres of forward progress per minute of ball-in-play time
TEMPO_SCALE = 90.0

MOMENTUM_WEIGHTS = {"stability": 0.35, "turnovers": 0.30, "pressure": 0.20, "tempo": 0.15}


def momentum_components(
    passes_per_possession: float,
    turnovers_per_min: float,
    pressures_per_min: float,
    progress_m_per_min: float,
) -> dict[str, float]:
    """Normalise the four Control vs Chaos inputs to [-1, 1] (positive = control)."""
    return {
        "stability": round(
            clamp((passes_per_possession - STABILITY_BASELINE) / STABILITY_SCALE, -1, 1), 3
        ),
        "turnovers": round(
            clamp((TURNOVER_BASELINE - turnovers_per_min) / TURNOVER_SCALE, -1, 1), 3
        ),
        "pressure": round(
            clamp((PRESSURE_BASELINE - pressures_per_min) / PRESSURE_SCALE, -1, 1), 3
        ),
        "tempo": round(clamp((TEMPO_BASELINE - progress_m_per_min) / TEMPO_SCALE, -1, 1), 3),
    }


def control_chaos_index(components: dict[str, float]) -> float:
    """Weighted blend of the components, scaled to -100 (chaos) .. +100 (control), 1 dp."""
    total = sum(MOMENTUM_WEIGHTS[k] * components[k] for k in MOMENTUM_WEIGHTS)
    return round(clamp(100 * total, -100.0, 100.0), 1)


# ---------------------------------------------------------------- clock


def elapsed_ms(period: int, clock_ms: int, first_half_end_ms: int) -> int:
    """Playing time since kickoff, so windows can span half-time."""
    if period == 1:
        return clock_ms
    return first_half_end_ms + (clock_ms - 45 * 60_000)


def clock_display(period: int, clock_ms: int) -> str:
    """'67:12', or '45+02:18' / '90+03:05' in stoppage time."""
    base = 45 * 60_000 * period
    if clock_ms >= base:
        extra = clock_ms - base
        return f"{45 * period}+{extra // 60_000:02d}:{extra // 1000 % 60:02d}"
    return f"{clock_ms // 60_000:02d}:{clock_ms // 1000 % 60:02d}"


def minute_label(period: int, clock_ms: int) -> str:
    """Football minute: 0:00-0:59 is the 1st minute; stoppage is "45+N'" / "90+N'"."""
    base = 45 * 60_000 * period
    if clock_ms >= base:
        return f"{45 * period}+{(clock_ms - base) // 60_000 + 1}'"
    return f"{clock_ms // 60_000 + 1}'"


# ---------------------------------------------------------------- recap


def player_of_the_match_score(
    goals: int,
    xg: float,
    key_passes: int,
    shots_on_target: int,
    tackles_won: int,
    interceptions: int,
    distance_km: float,
) -> float:
    """Ranking score for the full-time player of the match (not shown to viewers).

    Goals dominate, then chance creation and quality, then defensive work and running.
    """
    score = (
        3.0 * goals
        + 2.0 * xg
        + 1.0 * key_passes
        + 0.5 * shots_on_target
        + 0.4 * (tackles_won + interceptions)
        + 0.1 * distance_km
    )
    return round(score, 3)
