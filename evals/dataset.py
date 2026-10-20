"""The eval set: 30 seeded moments, reproducible from (scenario, seed, trigger kind, n).

`build()` regenerates `evals/data/moments.jsonl` by playing seeded matches through the
Stats Engine and picking a spread of trigger kinds; `load()` reads the committed file.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from contracts import MatchEvent, MatchInfo
from sim.engine import MatchConfig, MatchEngine
from sim.scenario import load_scenario
from sim.tracking import TrackingGenerator
from sim.world import load_world
from stats import StatsEngine

DATA = Path(__file__).with_name("data") / "moments.jsonl"
SIZE = 30

# (scenario, seed, with tracking) — tracking makes sprint and hard-pass triggers possible.
MATCHES: list[tuple[str, int, bool]] = [
    ("comeback", 7, True),
    ("late_winner", 7, False),
    ("red_card", 7, False),
    ("pressing_collapse", 7, False),
    ("default", 11, True),
]
# How many of each trigger kind to take per match, in order of interest.
QUOTA = {
    "goal": 2, "card": 1, "xg": 1, "momentum_swing": 1, "pass_difficulty": 1, "speed": 1,
    "half_time": 1, "full_time": 1, "tick": 1,
}  # fmt: skip


# The 30-moment mix.
MIX = {
    "goal": 6, "card": 4, "xg": 4, "momentum_swing": 4, "pass_difficulty": 2, "speed": 2,
    "half_time": 3, "full_time": 3, "tick": 2,
}  # fmt: skip


@dataclass(frozen=True)
class Sample:
    sample_id: str
    scenario: str
    seed: int
    home: str
    away: str
    tracking: bool
    kind: str
    nth: int  # the nth trigger of this kind in the match (1-based)

    @property
    def match_id(self) -> str:
        # One match id per sample: the same seeded match, stopped at a different moment.
        return f"ev-{self.sample_id}".lower().replace("_", "-")


def _teams(scenario: str) -> tuple[str, str]:
    if scenario == "default":
        return "NBR", "LAG"
    sc = load_scenario(scenario)
    assert sc.home and sc.away
    return sc.home, sc.away


def play(sample: Sample, stop_at_trigger: bool = True) -> tuple[StatsEngine, object | None]:
    """Feed the sample's match into a fresh StatsEngine up to (and including) its trigger."""
    world = load_world()
    config = MatchConfig(home=sample.home, away=sample.away, seed=sample.seed,
                         scenario=sample.scenario, match_id=sample.match_id)  # fmt: skip
    engine = MatchEngine(world, config)
    stats = StatsEngine(world, MatchInfo(match_id=sample.match_id, home=sample.home,
                                         away=sample.away, scenario=sample.scenario,
                                         seed=sample.seed, speed=0, status="live"))  # fmt: skip
    stream = (
        TrackingGenerator(world, sample.match_id, sample.home, sample.away, sample.seed).stream(
            engine.events()
        )
        if sample.tracking
        else engine.events()
    )
    seen = 0
    for item in stream:
        fired = stats.on_event(item) if isinstance(item, MatchEvent) else stats.on_frame(item)
        for trig in fired:
            if trig.kind == sample.kind:
                seen += 1
                if seen == sample.nth and stop_at_trigger:
                    return stats, trig
    return stats, None


def build() -> list[Sample]:
    per_match: list[list[Sample]] = []
    for scenario, seed, tracking in MATCHES:
        home, away = _teams(scenario)
        match_id = f"eval-{scenario}-s{seed}"
        world = load_world()
        engine = MatchEngine(world, MatchConfig(home=home, away=away, seed=seed,
                                                scenario=scenario, match_id=match_id))  # fmt: skip
        stats = StatsEngine(world, MatchInfo(match_id=match_id, home=home, away=away,
                                             scenario=scenario, seed=seed, speed=0,
                                             status="live"))  # fmt: skip
        stream = (
            TrackingGenerator(world, match_id, home, away, seed).stream(engine.events())
            if tracking
            else engine.events()
        )
        counts: Counter[str] = Counter()
        for item in stream:
            fired = stats.on_event(item) if isinstance(item, MatchEvent) else stats.on_frame(item)
            counts.update(t.kind for t in fired)
        picked: list[Sample] = []
        for kind, quota in QUOTA.items():
            available = counts[kind]
            if kind == "tick":  # one tick well into the first half
                picks = [min(40, available)] if available else []
            else:
                picks = list(range(1, min(quota, available) + 1))
            for nth in picks:
                picked.append(Sample(f"{scenario}-s{seed}-{kind}-{nth}", scenario, seed, home,
                                     away, tracking, kind, nth))  # fmt: skip
        per_match.append(picked)
    # Take a fixed mix of kinds, round-robin across matches, so all are represented.
    out: list[Sample] = []
    for kind, wanted in MIX.items():
        pool = [[x for x in m if x.kind == kind] for m in per_match]
        taken = 0
        for i in range(max((len(p) for p in pool), default=0)):
            for p in pool:
                if i < len(p) and taken < wanted:
                    out.append(p[i])
                    taken += 1
    return out[:SIZE]


def save(samples: list[Sample]) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text("".join(json.dumps(asdict(s)) + "\n" for s in samples))


def load(limit: int | None = None) -> list[Sample]:
    rows = [Sample(**json.loads(line)) for line in DATA.read_text().splitlines() if line.strip()]
    return rows[:limit] if limit else rows


if __name__ == "__main__":
    built = build()
    save(built)
    print(f"wrote {len(built)} samples to {DATA}")
    print(Counter(s.kind for s in built))
