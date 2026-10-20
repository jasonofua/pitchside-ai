"""Producer eval: valid overlay contract, house rules on slots, upgrade in place, and the
latency budget (stat overlay under 1 s of the trigger)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

from evals.harness import Outcome
from evals.scoring import AgentScore, latency, rate

FULL_CARD_KINDS = {"goal", "half_time", "full_time"}
INSTANT = {"goal", "card", "half_time", "full_time", "xg", "speed", "pass_difficulty",
           "momentum_swing"}  # fmt: skip


@cache
def validator() -> Draft202012Validator:
    schema = Path(__file__).resolve().parents[1] / "schemas" / "overlay.schema.json"
    return Draft202012Validator(json.loads(schema.read_text()))


def score(outcomes: list[Outcome]) -> AgentScore:
    s = AgentScore("producer")
    valid = total = 0
    upgraded = upgradable = 0
    instant_ok = instant = 0
    for o in outcomes:
        ids: dict[str, list[str]] = {}
        for card in o.overlays:
            total += 1
            errors = list(validator().iter_errors(card.model_dump(mode="json", exclude_none=True)))
            valid += not errors
            if card.slot == "full_card":
                s.check(
                    card.kind in FULL_CARD_KINDS, f"{o.sample.sample_id}: full card for {card.kind}"
                )
            s.check(4_000 <= card.ttl_ms <= 60_000, f"{o.sample.sample_id}: ttl {card.ttl_ms}")
            ids.setdefault(card.overlay_id, []).append(card.source or "")
        for sources in ids.values():
            if "template" in sources and "agent" in sources:
                upgradable += 1
                upgraded += sources.index("template") < sources.index("agent")
        if o.trigger.kind in INSTANT:
            instant += 1
            instant_ok += o.first_overlay_s is not None and o.first_overlay_s < 1.0
    s.metrics["contract_valid"] = rate(valid, total)
    s.metrics["upgrades_in_place"] = rate(upgraded, upgradable)
    s.metrics["stat_overlay_under_1s"] = rate(instant_ok, instant)
    s.metrics["overlays"] = total
    s.metrics.update(latency([
        t.latency_ms for o in outcomes for t in o.traces_for("producer") if t.status == "ok"
    ]))  # fmt: skip
    s.check(s.metrics["contract_valid"] == 1.0, "an overlay broke the contract")
    s.check(
        float(s.metrics["upgrades_in_place"]) == 1.0, "an agent card did not replace its template"
    )
    s.check(float(s.metrics["stat_overlay_under_1s"]) >= 0.9, "stat overlays slower than 1 s")
    return s
