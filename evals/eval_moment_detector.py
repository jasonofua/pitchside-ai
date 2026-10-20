"""Moment Detector eval: the right moment kind for each trigger, goals and reds ranked
high, and its latency."""

from __future__ import annotations

from evals.harness import Outcome
from evals.scoring import AgentScore, latency, rate

EXPECTED = {
    "goal": "goal",
    "card": "card",
    "xg": "big_chance",
    "speed": "speed_burst",
    "pass_difficulty": "hard_pass",
    "momentum_swing": "momentum_swing",
    "half_time": "half_time",
    "full_time": "full_time",
    "tick": "spell",
}


def score(outcomes: list[Outcome]) -> AgentScore:
    s = AgentScore("moment_detector")
    hits = judged = 0
    for o in outcomes:
        if not o.moments:
            # Only ticks may be judged "not a moment".
            s.check(o.trigger.kind == "tick", f"{o.sample.sample_id}: no moment")
            continue
        m = o.moments[-1]
        judged += 1
        hits += m["kind"] == EXPECTED[o.trigger.kind]
        if o.trigger.kind == "goal":
            s.check(
                m["importance"] >= 0.9, f"{o.sample.sample_id}: goal importance {m['importance']}"
            )
        s.check(m["trace_id"] and m["moment_id"].endswith(o.trigger.trigger_id),
                f"{o.sample.sample_id}: moment ids")  # fmt: skip
    accuracy = rate(hits, judged)
    s.metrics["kind_accuracy"] = accuracy
    s.metrics.update(latency([
        t.latency_ms for o in outcomes for t in o.traces_for("moment_detector") if t.status == "ok"
    ]))  # fmt: skip
    s.check(accuracy >= 0.9, f"kind accuracy {accuracy} < 0.9")
    return s
