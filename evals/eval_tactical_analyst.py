"""Tactical Analyst eval: an insight for every important moment, every figure in it backed
by match state, cited stats real, and a short headline."""

from __future__ import annotations

from evals.harness import Outcome
from evals.scoring import AgentScore, figures_ok, latency, rate


def score(outcomes: list[Outcome]) -> AgentScore:
    s = AgentScore("tactical_analyst")
    expected = produced = accurate = cited_ok = cited_total = 0
    for o in outcomes:
        if not o.moments or o.moments[-1]["importance"] < 0.5:
            continue
        expected += 1
        if not o.insights:
            s.failures.append(f"{o.sample.sample_id}: no insight")
            continue
        produced += 1
        ins = o.insights[-1]
        ok, bad = figures_ok(f"{ins['headline']} {ins['why_it_matters']}", o.facts)
        accurate += ok
        if not ok:
            s.failures.append(f"{o.sample.sample_id}: unbacked figures {bad}")
        s.check(len(ins["headline"].split()) <= 14, f"{o.sample.sample_id}: long headline")
        for c in ins["stats_cited"]:
            cited_total += 1
            ok_c, _ = figures_ok(f"{c['value']}{c.get('unit', '')}", o.facts)
            cited_ok += ok_c
    s.metrics["coverage"] = rate(produced, expected)
    s.metrics["number_accuracy"] = rate(accurate, produced)
    s.metrics["citations_backed"] = rate(cited_ok, cited_total)
    s.metrics.update(latency([
        t.latency_ms for o in outcomes for t in o.traces_for("tactical_analyst") if t.status == "ok"
    ]))  # fmt: skip
    s.check(s.metrics["coverage"] == 1.0, "an important moment went unexplained")
    s.check(float(s.metrics["number_accuracy"]) >= 0.9, "number accuracy below 0.9")
    return s
