"""Narrator eval: commentary for every goal, card and period end, figures backed by match
state, lines short enough to read live."""

from __future__ import annotations

from evals.harness import Outcome
from evals.scoring import AgentScore, figures_ok, latency, rate
from runtime.realnames import real_names_in

MUST_NARRATE = {"goal", "card", "half_time", "full_time"}
LINE_MAX = 260


def score(outcomes: list[Outcome]) -> AgentScore:
    s = AgentScore("narrator")
    expected = produced = accurate = 0
    for o in outcomes:
        if o.trigger.kind not in MUST_NARRATE:
            continue
        expected += 1
        if not o.commentary:
            s.failures.append(f"{o.sample.sample_id}: no commentary")
            continue
        produced += 1
        c = o.commentary[-1]
        ok, bad = figures_ok(c["text"], o.facts)
        accurate += ok
        if not ok:
            s.failures.append(f"{o.sample.sample_id}: unbacked figures {bad}")
        if c["kind"] == "line":
            s.check(len(c["text"]) <= LINE_MAX, f"{o.sample.sample_id}: line too long")
        s.check(not real_names_in(c["text"]), f"{o.sample.sample_id}: real-world name")
    s.metrics["coverage"] = rate(produced, expected)
    s.metrics["number_accuracy"] = rate(accurate, produced)
    s.metrics.update(latency([
        t.latency_ms for o in outcomes for t in o.traces_for("narrator") if t.status == "ok"
    ]))  # fmt: skip
    s.check(s.metrics["coverage"] == 1.0, "a goal, card or period end went unnarrated")
    s.check(float(s.metrics["number_accuracy"]) >= 0.9, "number accuracy below 0.9")
    return s
