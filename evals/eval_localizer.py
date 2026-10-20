"""Localizer eval: every card a viewer sees is in their language, with figures intact.

Language is checked loosely (Yoruba tone marks, Pidgin markers, French and Spanish function
words). Quality needs people: `evals/run.py` writes Pidgin and Yoruba samples to
evals/results/language_samples.md for the native-speaker review.
"""

from __future__ import annotations

from evals.harness import Outcome
from evals.scoring import AgentScore, figures_ok, language_ok, latency, rate


def score(outcomes: list[Outcome]) -> AgentScore:
    s = AgentScore("localizer")
    by_lang: dict[str, list[int]] = {}
    lang: str
    figures_total = figures_good = 0
    for o in outcomes:
        for card in o.overlays:
            lang = o.profiles[card.audience_profile_hash].language
            s.check(card.lang == lang, f"{o.sample.sample_id}: card in {card.lang}, viewer {lang}")
            hits = by_lang.setdefault(lang, [0, 0])
            hits[1] += 1
            hits[0] += language_ok(lang, f"{card.title} {card.body}")
            figures_total += 1
            ok, _ = figures_ok(f"{card.title} {card.body}", o.facts)
            figures_good += ok
    for lang, (good, total) in sorted(by_lang.items()):
        s.metrics[f"lang_{lang}"] = rate(good, total)
        s.check(good / total >= 0.8 if total else True, f"{lang} cards do not read as {lang}")
    s.metrics["figures_intact"] = rate(figures_good, figures_total)
    s.metrics.update(latency([
        t.latency_ms for o in outcomes for t in o.traces_for("localizer") if t.status == "ok"
    ]))  # fmt: skip
    s.check(float(s.metrics["figures_intact"]) == 1.0, "a published card has an unbacked figure")
    return s
