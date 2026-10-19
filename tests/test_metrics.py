"""One or more unit tests per metric in stats.metrics."""

from __future__ import annotations

import math

import pytest

from stats import metrics as m


class TestXg:
    def test_close_central_shot_beats_a_long_one(self) -> None:
        assert m.xg(99, 34) > m.xg(88, 34) > m.xg(75, 34)

    def test_central_beats_wide_at_the_same_distance(self) -> None:
        d = 14.0
        wide = (m.PITCH_LENGTH - d * math.cos(1.0), 34 + d * math.sin(1.0))
        assert m.xg(m.PITCH_LENGTH - d, 34) > m.xg(*wide)

    def test_values_are_sane_probabilities(self) -> None:
        assert 0.5 < m.xg(103, 34) < 0.99  # a tap-in
        assert 0.15 < m.xg(94, 34) < 0.45  # penalty-spot range open play
        assert m.xg(75, 34) < 0.05  # 30 m

    def test_penalty_is_fixed(self) -> None:
        assert m.xg(*m.PENALTY_SPOT, penalty=True) == m.XG_PENALTY

    def test_discounts(self) -> None:
        base = m.xg(95, 30)
        assert m.xg(95, 30, header=True) == pytest.approx(base * m.XG_HEADER_FACTOR)
        assert m.xg(95, 30, under_pressure=True) == pytest.approx(base * m.XG_PRESSURE_FACTOR)
        assert m.xg(95, 30, free_kick=True) == pytest.approx(base * m.XG_FREE_KICK_FACTOR)

    def test_symmetric_about_the_centre_line(self) -> None:
        assert m.xg(92, 20) == pytest.approx(m.xg(92, 48))


def test_goal_angle_is_widest_in_front_of_goal() -> None:
    assert m.goal_angle(100, 34) > m.goal_angle(100, 20) > 0
    assert m.goal_angle(104.9, 34) == pytest.approx(math.pi, abs=0.1)


class TestPassDifficulty:
    def test_short_easy_pass_is_low(self) -> None:
        assert m.pass_difficulty(8, False, 0, 2, 12) < 10

    def test_monotonic_in_each_input(self) -> None:
        base = dict(distance_m=20, under_pressure=False, bypassed=1, forward_m=12,
                    receiver_space_m=5.0)  # fmt: skip
        d0 = m.pass_difficulty(**base)  # type: ignore[arg-type]
        assert m.pass_difficulty(**{**base, "distance_m": 35}) > d0  # type: ignore[arg-type]
        assert m.pass_difficulty(**{**base, "under_pressure": True}) > d0  # type: ignore[arg-type]
        assert m.pass_difficulty(**{**base, "bypassed": 4}) > d0  # type: ignore[arg-type]
        assert m.pass_difficulty(**{**base, "receiver_space_m": 2}) > d0  # type: ignore[arg-type]

    def test_hardest_possible_pass_is_100(self) -> None:
        assert m.pass_difficulty(60, True, 8, 50, 0.5) == 100.0

    def test_backward_pass_gets_no_line_breaking_credit(self) -> None:
        assert m.pass_difficulty(20, False, 5, -10, 8) == m.pass_difficulty(20, False, 0, -10, 8)

    def test_without_tracking_uses_neutral_tightness_and_forward_distance(self) -> None:
        short = m.pass_difficulty(10, False, None, 5, None)
        assert short == pytest.approx(30 * 10 / 40 + 12.5, abs=0.1)
        long_forward = m.pass_difficulty(30, False, None, 25, None)
        assert long_forward == pytest.approx(30 * 30 / 40 + 15 + 12.5, abs=0.1)

    def test_bounded_and_rounded(self) -> None:
        v = m.pass_difficulty(23.456, True, 2, 15, 3.3)
        assert 0 <= v <= 100 and v == round(v, 1)


def test_opponents_bypassed() -> None:
    assert m.opponents_bypassed(30, 60, [10, 33, 45, 59, 70]) == 2  # 33 and 45; 59 is too close
    assert m.opponents_bypassed(50, 52, [51]) == 0
    assert m.opponents_bypassed(60, 40, [50]) == 0  # backward


def test_is_line_breaking() -> None:
    assert m.is_line_breaking(12, 3)
    assert not m.is_line_breaking(12, 2)
    assert not m.is_line_breaking(8, 5)
    assert m.is_line_breaking(20, None) and not m.is_line_breaking(19.9, None)


def test_pass_accuracy_pct() -> None:
    assert m.pass_accuracy_pct(0, 0) is None
    assert m.pass_accuracy_pct(80, 100) == 80.0
    assert m.pass_accuracy_pct(2, 3) == 66.7


def test_possession_pct() -> None:
    assert m.possession_pct(0, 0) == 50.0
    assert m.possession_pct(600, 400) == 60.0
    assert m.possession_pct(1, 2) + m.possession_pct(2, 1) == pytest.approx(100, abs=0.1)


def test_ppda() -> None:
    assert m.ppda(30, 0) is None
    assert m.ppda(30, 4) == 7.5
    assert m.in_ppda_zone(42.0) and not m.in_ppda_zone(41.9)


def test_speed_kmh() -> None:
    assert m.speed_kmh(1.0, 0.0, 200) == pytest.approx(18.0)
    assert m.speed_kmh(3.0, 4.0, 1000) == pytest.approx(18.0)
    assert m.speed_kmh(1, 1, 0) == 0.0


def test_smoothed() -> None:
    assert m.smoothed([]) == 0.0
    assert m.smoothed([30, 33, 36]) == 33.0


def test_count_sprints_needs_a_full_second() -> None:
    fast, slow = 27.0, 20.0
    assert m.count_sprints([fast] * 4) == 0  # 0.8 s
    assert m.count_sprints([fast] * 5) == 1
    assert m.count_sprints([fast] * 12) == 1  # one long sprint
    assert m.count_sprints([fast] * 5 + [slow] + [fast] * 5) == 2


class TestControlChaos:
    def test_baselines_score_zero(self) -> None:
        comps = m.momentum_components(
            m.STABILITY_BASELINE, m.TURNOVER_BASELINE, m.PRESSURE_BASELINE, m.TEMPO_BASELINE
        )
        assert all(v == 0 for v in comps.values())
        assert m.control_chaos_index(comps) == 0

    def test_directions(self) -> None:
        calm = m.momentum_components(12, 0.5, 1.0, 40)
        frantic = m.momentum_components(0.5, 8, 12, 300)
        assert all(v > 0 for v in calm.values())
        assert all(v < 0 for v in frantic.values())
        assert m.control_chaos_index(calm) > 50
        assert m.control_chaos_index(frantic) < -50

    def test_bounded(self) -> None:
        extreme = m.momentum_components(1e6, -1e6, -1e6, -1e6)
        assert all(v == 1 for v in extreme.values())
        assert m.control_chaos_index(extreme) == 100

    def test_weights_sum_to_one(self) -> None:
        assert sum(m.MOMENTUM_WEIGHTS.values()) == pytest.approx(1.0)


class TestClock:
    def test_elapsed_spans_half_time(self) -> None:
        assert m.elapsed_ms(1, 1000, 47 * 60_000) == 1000
        assert m.elapsed_ms(2, 45 * 60_000, 47 * 60_000) == 47 * 60_000
        assert m.elapsed_ms(2, 50 * 60_000, 47 * 60_000) == 52 * 60_000

    @pytest.mark.parametrize(
        ("period", "clock", "display", "minute"),
        [
            (1, 0, "00:00", "1'"),
            (1, 59_999, "00:59", "1'"),
            (1, 67_000, "01:07", "2'"),
            (1, 45 * 60_000 + 138_000, "45+02:18", "45+3'"),
            (2, 45 * 60_000, "45:00", "46'"),
            (2, 70 * 60_000 + 30_000, "70:30", "71'"),
            (2, 92 * 60_000 + 5_000, "90+02:05", "90+3'"),
        ],
    )
    def test_display(self, period: int, clock: int, display: str, minute: str) -> None:
        assert m.clock_display(period, clock) == display
        assert m.minute_label(period, clock) == minute


def test_flip_and_box() -> None:
    assert m.flip(10, 20) == (95, 48)
    assert m.in_box(90, 34) and not m.in_box(85, 34) and not m.in_box(95, 5)


def test_player_of_the_match_score() -> None:
    scorer = m.player_of_the_match_score(1, 0.4, 0, 1, 0, 0, 9.0)
    creator = m.player_of_the_match_score(0, 0.1, 2, 0, 1, 0, 11.0)
    worker = m.player_of_the_match_score(0, 0.0, 0, 0, 4, 3, 12.5)
    assert scorer > creator > m.player_of_the_match_score(0, 0, 0, 0, 0, 0, 10.0)
    assert worker > creator
    assert m.player_of_the_match_score(2, 1.1, 1, 3, 1, 1, 10.0) > scorer
