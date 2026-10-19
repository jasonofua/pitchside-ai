"""Release stream items in step with the match clock."""

from __future__ import annotations

import time
from collections.abc import Callable


class Pacer:
    """Sleeps so that wall time tracks match time divided by `speed`.

    speed=0 disables pacing. Each period is anchored separately, with a short
    half-time pause in between, because the period 2 clock restarts at 45:00.
    If the consumer falls behind, items are released immediately until it catches up.
    """

    def __init__(
        self,
        speed: float,
        halftime_s: float = 10.0,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if speed < 0:
            raise ValueError("speed must be >= 0")
        self.speed = speed
        self.halftime_s = halftime_s
        self._now = now
        self._sleep = sleep
        self._period: int | None = None
        self._anchor_clock = 0
        self._anchor_wall = 0.0

    def delay(self, period: int, clock_ms: int) -> float:
        """Seconds to wait before releasing an item at (period, clock_ms); never negative."""
        if self.speed == 0:
            return 0.0
        if period != self._period:
            pause = self.halftime_s if self._period is not None else 0.0
            self._period = period
            self._anchor_clock = clock_ms
            self._anchor_wall = self._now() + max(pause, 0.0)
        due = self._anchor_wall + (clock_ms - self._anchor_clock) / 1000 / self.speed
        return max(0.0, due - self._now())

    def wait(self, period: int, clock_ms: int) -> None:
        seconds = self.delay(period, clock_ms)
        if seconds > 0:
            self._sleep(seconds)
