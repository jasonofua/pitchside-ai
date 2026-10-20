"""Fact Checker eval: nothing unbacked gets through, nothing true is stopped.

Recall: every published agent card has one figure corrupted (the same fault the Director
panel injects) and must be rejected. False positives: every published card, as is, must
pass. Plus the live verdicts from the run.
"""

from __future__ import annotations

from agents.numbers import check_text, corrupt_first_figure
from evals.harness import Outcome
from evals.scoring import AgentScore, latency, rate


def score(outcomes: list[Outcome]) -> AgentScore:
    s = AgentScore("fact_checker")
    corrupted = caught = clean = passed = 0
    for o in outcomes:
        for card in o.overlays:
            texts = [card.title, card.body, *(f"{x.value}{x.unit or ''}" for x in card.stats)]
            clean += 1
            bad = [m.cited for t in texts for m in check_text(t, o.facts)[1]]
            passed += not bad
            if bad:
                s.failures.append(f"{o.sample.sample_id} {card.source} {card.lang}: {bad} in "
                                  f"{card.title} | {card.body}")  # fmt: skip
            if card.source != "agent":
                continue
            wrong = corrupt_first_figure(card.body, o.facts)
            if wrong == card.body:
                continue  # no unit-bearing figure to corrupt
            corrupted += 1
            caught += bool(check_text(wrong, o.facts)[1])
    verdicts: dict[str, int] = {}
    for o in outcomes:
        for t in o.traces_for("fact_checker"):
            verdicts[t.status] = verdicts.get(t.status, 0) + 1
    s.metrics["recall_on_injected_errors"] = rate(caught, corrupted)
    s.metrics["injected"] = corrupted
    s.metrics["clean_pass_rate"] = rate(passed, clean)
    s.metrics["verdicts"] = ", ".join(f"{k}={v}" for k, v in sorted(verdicts.items()))
    s.metrics.update(latency([
        t.latency_ms for o in outcomes for t in o.traces_for("fact_checker") if t.status == "ok"
    ]))  # fmt: skip
    s.check(float(s.metrics["recall_on_injected_errors"]) == 1.0, "missed an injected error")
    s.check(float(s.metrics["clean_pass_rate"]) == 1.0, "rejected a true card")
    return s
