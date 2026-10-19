from __future__ import annotations

import pytest

from sim.pacing import Pacer


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


def test_speed_scales_wall_time() -> None:
    clock = FakeClock()
    pacer = Pacer(5, halftime_s=0, now=clock.now, sleep=clock.sleep)
    for ms in range(0, 60_001, 200):
        pacer.wait(1, ms)
    assert clock.t - 100.0 == pytest.approx(60 / 5)


def test_half_time_pause_and_second_half_anchor() -> None:
    clock = FakeClock()
    pacer = Pacer(20, halftime_s=3, now=clock.now, sleep=clock.sleep)
    pacer.wait(1, 0)
    pacer.wait(1, 2_820_000)  # 47:00, end of first-half stoppage
    pacer.wait(2, 2_700_000)  # second half restarts the clock at 45:00
    pacer.wait(2, 2_760_000)
    assert clock.t - 100.0 == pytest.approx(2_820 / 20 + 3 + 60 / 20)


def test_speed_zero_never_sleeps() -> None:
    clock = FakeClock()
    pacer = Pacer(0, now=clock.now, sleep=clock.sleep)
    pacer.wait(1, 0)
    pacer.wait(2, 5_000_000)
    assert clock.slept == []


def test_slow_consumer_catches_up_without_sleeping() -> None:
    clock = FakeClock()
    pacer = Pacer(1, now=clock.now, sleep=clock.sleep)
    pacer.wait(1, 0)
    clock.t += 10  # consumer stalled for 10 s
    pacer.wait(1, 5_000)
    assert clock.slept == []


def test_negative_speed_rejected() -> None:
    with pytest.raises(ValueError):
        Pacer(-1)
