"""Run every agent eval over the 30 seeded moments.

    uv run python -m evals.run                  # offline mock models
    FOUNDRY_ENDPOINT=... MODEL_LARGE=... MODEL_SMALL=... uv run python -m evals.run

Writes evals/results/<model>.json and .md, plus language_samples.md (Pidgin and
Yoruba cards for the native-speaker review). Exits 1 if any agent fails its thresholds.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from evals import (
    eval_fact_checker,
    eval_fan_lens,
    eval_localizer,
    eval_moment_detector,
    eval_narrator,
    eval_producer,
    eval_tactical_analyst,
)
from evals.dataset import load
from evals.harness import EvalHarness, Outcome
from evals.scoring import AgentScore

EVALS = (
    eval_moment_detector,
    eval_tactical_analyst,
    eval_narrator,
    eval_fan_lens,
    eval_localizer,
    eval_fact_checker,
    eval_producer,
)
RESULTS = Path(__file__).with_name("results")


async def collect(limit: int | None, verbose: bool) -> tuple[list[Outcome], str]:
    samples = load(limit)
    outcomes = []
    async with EvalHarness() as harness:
        model: str = harness.settings.llm
        if model != "mock":
            model = f"{harness.settings.model_large}+{harness.settings.model_small}"
        for n, sample in enumerate(samples, 1):
            outcome = await harness.run(sample)
            outcomes.append(outcome)
            if verbose:
                agent_cards = sum(c.source == "agent" for c in outcome.overlays)
                print(f"[{n:>2}/{len(samples)}] {sample.sample_id:<34} "
                      f"{outcome.seconds:5.1f}s  cards {len(outcome.overlays)} "
                      f"(agent {agent_cards})")  # fmt: skip
    return outcomes, model


def score_all(outcomes: list[Outcome]) -> list[AgentScore]:
    return [module.score(outcomes) for module in EVALS]


def language_samples(outcomes: list[Outcome]) -> str:
    lines = [
        "# Pidgin and Yoruba samples for native-speaker review",
        "",
        "Mark each line OK, or write the correction. Corrections become few-shot examples in",
        "`services/agents/prompts/localizer.v*.md` and fixes to `services/agents/i18n.py`.",
        "",
    ]
    for lang, name in (("pcm", "Nigerian Pidgin"), ("yo", "Yoruba")):
        lines += [f"## {name}", "", "| # | Moment | Card | OK / correction |", "|---|---|---|---|"]
        n = 0
        for o in outcomes:
            for card in o.overlays:
                if o.profiles[card.audience_profile_hash].language != lang or n >= 20:
                    continue
                n += 1
                text = f"**{card.title}** {card.body}".replace("|", "/")
                lines.append(f"| {n} | {o.sample.sample_id} ({card.source}) | {text} | |")
        lines.append("")
    return "\n".join(lines)


def report(scores: list[AgentScore], model: str, n: int) -> str:
    lines = [f"# Agent evals: {model}, {n} moments", "", "| Agent | Pass | Metrics |",
             "|---|---|---|"]  # fmt: skip
    for s in scores:
        metrics = ", ".join(f"{k} {v}" for k, v in s.metrics.items())
        lines.append(f"| {s.agent} | {'yes' if s.passed else '**no**'} | {metrics} |")
    for s in scores:
        if s.failures:
            lines += ["", f"## {s.agent}: failures", *(f"- {f}" for f in s.failures[:20])]
    return "\n".join(lines) + "\n"


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    for noisy in ("httpx", "mcp", "agent_framework"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="only the first N moments")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    outcomes, model = asyncio.run(collect(args.limit, not args.quiet))
    scores = score_all(outcomes)
    md = report(scores, model, len(outcomes))
    print("\n" + md)
    if not args.no_write:
        RESULTS.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        slug = model.replace("/", "_").replace("+", "_")
        (RESULTS / f"{slug}.json").write_text(
            json.dumps({"run_at": stamp, "scores": [asdict(s) for s in scores]}, indent=2) + "\n"
        )
        (RESULTS / f"{slug}.md").write_text(md + f"\nRun at {stamp}.\n")
        (RESULTS / "language_samples.md").write_text(language_samples(outcomes) + "\n")
    return 0 if all(s.passed for s in scores) else 1


if __name__ == "__main__":
    sys.exit(main())
