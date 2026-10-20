"""The eval harness itself: a quick pass over the first moments with the offline models."""

from __future__ import annotations

import asyncio

from evals.dataset import MIX, SIZE, load
from evals.run import collect, score_all


def test_eval_set_is_30_seeded_moments() -> None:
    samples = load()
    assert len(samples) == SIZE == 30
    assert len({s.sample_id for s in samples}) == 30
    kinds = {s.kind for s in samples}
    assert kinds == set(MIX)


def test_every_agent_passes_on_a_subset() -> None:
    outcomes, model = asyncio.run(collect(limit=8, verbose=False))
    assert model == "mock"
    scores = score_all(outcomes)
    assert {s.agent for s in scores} == {
        "moment_detector", "tactical_analyst", "narrator", "fan_lens", "localizer",
        "fact_checker", "producer",
    }  # fmt: skip
    failing = {s.agent: s.failures[:3] for s in scores if not s.passed}
    assert not failing, failing
