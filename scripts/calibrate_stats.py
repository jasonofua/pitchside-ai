"""Calibrate the Control vs Chaos baselines and check trigger rates.

Runs default-scenario matches through the Stats Engine and prints, for each raw momentum
input, the median and standard deviation over all 30-second ticks, plus the distribution
of pass difficulty and how often each trigger fires. The baselines in stats/metrics.py are
set from this output: baseline = median, scale = about 5 standard deviations.

    uv run python scripts/calibrate_stats.py --matches 12 --tracking 4
"""

from __future__ import annotations

import argparse
import itertools
import statistics
from collections import Counter

from contracts import MatchEvent, MatchInfo
from sim.engine import MatchConfig, MatchEngine
from sim.tracking import TrackingGenerator
from sim.world import load_world
from stats import StatsEngine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=12, help="event-only matches")
    parser.add_argument("--tracking", type=int, default=4, help="matches with tracking")
    args = parser.parse_args()

    world = load_world()
    pairs = list(itertools.permutations([c.team_id for c in world.clubs], 2))
    raw: dict[str, list[float]] = {}
    index: list[float] = []
    swings: list[float] = []
    triggers: Counter[str] = Counter()
    difficulty: list[float] = []
    n_tracking = 0

    for n in range(args.matches):
        home, away = pairs[n % len(pairs)]
        seed = 1000 + n
        engine = MatchEngine(world, MatchConfig(home=home, away=away, seed=seed))
        info = MatchInfo(
            match_id=engine.match_id, home=home, away=away, scenario="default", seed=seed,
            speed=0, status="scheduled",
        )  # fmt: skip
        stats = StatsEngine(world, info)
        with_tracking = n < args.tracking
        if with_tracking:
            stream = TrackingGenerator(world, engine.match_id, home, away, seed).stream(
                engine.events()
            )
            n_tracking += 1
        else:
            stream = iter(engine.events())
        for item in stream:
            if isinstance(item, MatchEvent):
                fired = stats.on_event(item)
                for trig in fired:
                    if trig.kind == "tick":
                        _, _, values = stats.momentum_inputs(stats.t)
                        if values:
                            for k, v in values.items():
                                raw.setdefault(k, []).append(v)
            else:
                fired = stats.on_frame(item)
            for trig in fired:
                if trig.kind != "speed" or with_tracking:
                    triggers[trig.kind] += 1
        index.extend(p.index for p in stats.momentum_points)
        back = 10
        pts = stats.momentum_points
        swings.extend(pts[i].index - pts[i - back].index for i in range(back, len(pts)))
        if with_tracking:
            difficulty.extend(
                r.difficulty
                for r in stats.records
                if r.difficulty is not None and r.ev.outcome == "complete"
            )

    print(f"{args.matches} matches ({n_tracking} with tracking)\n")
    print(f"{'input':24} {'median':>8} {'stdev':>8} {'p10':>8} {'p90':>8}")
    for k, vals in raw.items():
        q = statistics.quantiles(vals, n=10)
        print(
            f"{k:24} {statistics.median(vals):8.2f} {statistics.pstdev(vals):8.2f} "
            f"{q[0]:8.2f} {q[-1]:8.2f}"
        )
    q = statistics.quantiles(index, n=20)
    print(f"\nindex: mean {statistics.mean(index):.1f}, stdev {statistics.pstdev(index):.1f}, "
          f"p5 {q[0]:.1f}, p95 {q[-1]:.1f}")  # fmt: skip
    big = sum(1 for s in swings if abs(s) >= 30) / max(len(swings), 1)
    print(f"share of ticks with |5-min swing| >= 30: {big:.1%}")
    if difficulty:
        q = statistics.quantiles(difficulty, n=100)
        over = sum(1 for d in difficulty if d > 80) / n_tracking
        print(f"\npass difficulty (completed): p50 {q[49]:.1f}, p90 {q[89]:.1f}, "
              f"p99 {q[98]:.1f}; > 80 per match: {over:.1f}")  # fmt: skip
    print("\ntriggers per match:")
    for kind, count in sorted(triggers.items()):
        denom = n_tracking if kind == "speed" else args.matches
        print(f"  {kind:16} {count / denom:6.1f}")


if __name__ == "__main__":
    main()
