"""Unit tests for the agents' deterministic parts: number checking, resilience, producer
rules, prompts, phrase tables and template cards."""

from __future__ import annotations

import asyncio
import re
import string
from typing import Any

import pytest

from agents import prompts
from agents.i18n import LANGS, PHRASES
from agents.mock_phrases import BODIES
from agents.numbers import Facts, check_text, corrupt_first_figure
from agents.producer_rules import clamp_plan, is_stale, overlay_id, rule_plan, to_overlay
from agents.resilience import AgentUnavailableError, ChaosSwitch, CircuitBreaker, Guard
from agents.run import BASELINE, INSTANT, provisional_moment
from agents.templates import MomentContext, render, template_card
from contracts import OverlayCard, Profile, Trigger
from contracts import agents as agent_contracts
from contracts.agents import CardDraft, ProducerPlan, StatItem
from mcp_stats.server import build_server
from runtime.profiles import DEMO_PROFILES, profile_hash
from runtime.store import SqliteStore
from stats.service import StatsRegistry

from .conftest import stats_with_tracking

# --------------------------------------------------------------------- numbers


def _facts() -> Facts:
    return Facts.from_payloads([
        {"home": {"score": 2, "team_id": "LAG"}, "away": {"score": 1, "team_id": "HCF"},
         "goals": [{"minute": "71'", "score_after": "1-1", "xg": 0.342}]},
        {"teams": [{"possession_pct": 57.6, "xg": 1.28, "shots": 13, "top_speed_kmh": 33.1,
                    "distance_km": 112.43}]},
        {"value": 0.76, "unit": "xG"},
    ])  # fmt: skip


@pytest.mark.parametrize(
    "text",
    [
        "Lagos have 58% of the ball",  # rounded from 57.6
        "57.6% possession and 13 shots",
        "1.3 xG so far",  # rounded from 1.28
        "A 0.34 xG chance",  # rounded from 0.342
        "a 0.76 xG penalty",  # from the trigger's value/unit
        "Top speed 33.1 km/h",
        "112.4 km covered",
        "It is 2-1 now",
        "It is 2 - 1 now",
        "scored in the 71'",
        "the 71st minute",
        "above 32 km/h in the last 5 minutes",
    ],
)
def test_true_figures_pass(text: str) -> None:
    checked, bad = check_text(text, _facts())
    assert checked >= 1 and bad == [], bad


@pytest.mark.parametrize(
    ("text", "cited"),
    [
        ("Lagos have 85% of the ball", "85%"),
        ("2.4 xG so far", "2.4 xG"),
        ("Top speed 35.2 km/h", "35.2 km/h"),
        ("It is 3-1 now", "3-1"),
        ("scored in the 64'", "64'"),
        ("16 more passes than their rivals", "16"),  # a derived number
    ],
)
def test_wrong_figures_are_caught(text: str, cited: str) -> None:
    _, bad = check_text(text, _facts())
    assert [m.cited for m in bad] == [cited]


def test_mismatch_suggests_the_closest_true_value() -> None:
    _, bad = check_text("They have 60% of the ball", _facts())
    assert bad[0].expected == "57.6%"


def test_corrupted_figure_is_always_caught() -> None:
    facts = _facts()
    for text in ("58% of the ball", "0.34 xG chance", "Top speed 33.1 km/h"):
        wrong = corrupt_first_figure(text, facts)
        assert wrong != text
        assert check_text(wrong, facts)[1], wrong


# ------------------------------------------------------------------ resilience


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_circuit_breaker_opens_and_recovers() -> None:
    clock = FakeClock()
    b = CircuitBreaker(clock=clock)
    for _ in range(2):
        b.failure()
    assert b.allow()
    b.failure()
    assert not b.allow()
    clock.t += 31
    assert b.allow()
    b.success()
    assert b.failures == []


def test_failures_outside_the_window_do_not_count() -> None:
    clock = FakeClock()
    b = CircuitBreaker(clock=clock)
    b.failure()
    b.failure()
    clock.t += 61
    b.failure()
    assert b.allow()


def test_chaos_switch() -> None:
    clock = FakeClock()
    chaos = ChaosSwitch(clock=clock)
    chaos.kill("narrator", 20)
    assert chaos.is_killed("narrator") and not chaos.is_killed("fan_lens")
    clock.t += 21
    assert not chaos.is_killed("narrator")
    chaos.wrong_numbers = 1
    assert chaos.take_wrong_number() and not chaos.take_wrong_number()


def test_guard_soft_timeout_publishes_then_waits_for_the_upgrade() -> None:
    async def main() -> tuple[str, list[str]]:
        guard = Guard(timeout_s=0.05)
        events: list[str] = []

        async def slow() -> str:
            await asyncio.sleep(0.15)
            return "upgraded"

        async def on_slow() -> None:
            events.append("template")

        result = await guard.call("narrator", slow, hard_s=1.0, on_slow=on_slow)
        return result, events

    assert asyncio.run(main()) == ("upgraded", ["template"])


def test_guard_hard_timeout_and_breaker() -> None:
    async def main() -> None:
        guard = Guard(timeout_s=0.01)

        async def never() -> str:
            await asyncio.sleep(10)
            return ""

        for _ in range(3):
            with pytest.raises(TimeoutError):
                await guard.call("producer", never, hard_s=0.02)
        with pytest.raises(AgentUnavailableError, match="circuit open"):
            await guard.call("producer", never)
        guard.chaos.kill("narrator", 5)
        with pytest.raises(AgentUnavailableError, match="chaos"):
            await guard.call("narrator", never)

    asyncio.run(main())


# ------------------------------------------------------------- producer rules


def _draft(**kw: Any) -> CardDraft:
    base: dict[str, Any] = dict(
        draft_id="d", moment_id="m:x", match_id="m", trace_id="t", profile_hash="abc123def456",
        mode="analyst", lang="en", kind="goal", title="GOAL!", body="A fine finish.",
        stats=[StatItem(label="xG", value=0.3, unit="xG"), StatItem(label="Score", value="1-0",
                                                                     unit="")],
        evidence_event_ids=["01M5Z8MDPZ6R8WGNNZHGDTPSQ7"], importance=0.95, source="template",
    )  # fmt: skip
    base.update(kw)
    return CardDraft(**base)


def test_rule_plans() -> None:
    assert rule_plan(_draft()).slot == "full_card"
    assert rule_plan(_draft(source="agent")).slot == "lower_third"
    assert rule_plan(_draft(kind="speed_burst", importance=0.35)).slot == "player_tag"
    assert rule_plan(_draft(kind="card", importance=0.95)).slot == "lower_third"
    casual = rule_plan(_draft(kind="spell", importance=0.3, source="agent", mode="casual"))
    assert casual.slot == "ticker"


def test_clamp_plan_enforces_house_rules() -> None:
    plan = ProducerPlan(slot="full_card", priority=9, ttl_s=500)
    clamped = clamp_plan(plan, _draft(kind="speed_burst", importance=0.9))
    assert (clamped.slot, clamped.priority, clamped.ttl_s) == ("lower_third", 5, 60)
    tag = clamp_plan(ProducerPlan(slot="player_tag", priority=3, ttl_s=8), _draft())
    assert tag.slot == "lower_third"  # no player to attach to


def test_overlay_cards_validate_and_share_ids() -> None:
    template = _draft()
    upgraded = _draft(source="agent", draft_id="d2")
    assert overlay_id(template) == overlay_id(upgraded)
    card = to_overlay(template, rule_plan(template), 61_000)
    OverlayCard.model_validate(card.model_dump())
    assert card.stats[1].unit is None  # empty units are dropped
    assert card.source == "template" and card.kind == "goal"


def test_staleness() -> None:
    assert not is_stale(60_000, 70_000, 12, True)
    assert is_stale(60_000, 80_000, 12, True)
    assert is_stale(60_000, 61_000, 12, False)


# --------------------------------------------------------------- prompts, i18n


@pytest.mark.parametrize("agent", prompts.AGENTS)
def test_every_agent_has_a_versioned_prompt(agent: str) -> None:
    p = prompts.load(agent)
    assert p.version >= 1 and p.model in ("large", "small")
    assert hasattr(agent_contracts, p.output)
    assert ("JSON" in p.text and "fictional" in p.text.lower()) or agent in (
        "localizer", "producer", "fact_checker",
    )  # fmt: skip


def test_prompt_tools_exist_on_the_mcp_server() -> None:
    mcp = build_server(StatsRegistry(_world(), SqliteStore()))
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    for agent in prompts.AGENTS:
        assert set(prompts.load(agent).tools) <= names, agent


def _world() -> Any:
    from sim.world import load_world

    return load_world()


def _fields(template: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}


@pytest.mark.parametrize("key", sorted(PHRASES))
def test_phrases_cover_every_language_with_the_same_fields(key: str) -> None:
    table = PHRASES[key]
    assert set(table) == set(LANGS)
    assert len({frozenset(_fields(text)) for text in table.values()}) == 1


@pytest.mark.parametrize("key", sorted(BODIES))
def test_mock_bodies_cover_every_language(key: str) -> None:
    table = BODIES[key]
    assert set(table) == set(LANGS)
    assert len({frozenset(_fields(text)) for text in table.values()}) == 1


def test_yoruba_lines_carry_tone_marks() -> None:
    marked = re.compile(r"[àáèéìíòóùúẹọṣ́̀]")
    texts = [t["yo"] for k, t in PHRASES.items() if not k.startswith("label_xg")]
    assert sum(bool(marked.search(t)) for t in texts) / len(texts) > 0.7


# --------------------------------------------------------------- templates


def _context(stats: Any, trigger: Trigger) -> MomentContext:
    def dump(model: Any) -> dict[str, Any]:
        return dict(model.model_dump(mode="json"))

    return MomentContext(
        match_state=dump(stats.match_state()),
        team_stats=dump(stats.team_stats("match")),
        recent_stats=dump(stats.team_stats("last_5")),
        player=dump(stats.player_stats(trigger.player_id)) if trigger.player_id else None,
        focus_player=dump(stats.player_stats("LAG-09")),
        momentum=dump(stats.momentum("last_15")),
        trigger=trigger.model_dump(mode="json", exclude_none=True),
    )


@pytest.mark.parametrize("profile", [*DEMO_PROFILES, Profile(mode="kids", language="fr"),
                                     Profile(mode="casual", language="es")])  # fmt: skip
def test_template_cards_pass_their_own_fact_check(profile: Profile) -> None:
    stats, triggers = stats_with_tracking()
    seen: set[str] = set()
    for trig in triggers:
        if trig.kind not in INSTANT or trig.kind in seen:
            continue
        seen.add(trig.kind)
        ctx = _context(stats, trig)
        moment = provisional_moment(trig, "t-test")
        card = template_card(moment, profile, profile_hash(profile), ctx, draft_id="d")
        assert card.title and card.lang == profile.language
        facts = Facts.from_payloads(ctx.payloads())
        for text in (card.title, card.body, *(f"{s.value}{s.unit}" for s in card.stats)):
            _, bad = check_text(text, facts)
            assert not bad, (trig.kind, profile.language, text, bad)
    assert seen >= {"goal", "speed", "half_time", "full_time"}


def test_every_trigger_kind_has_a_baseline() -> None:
    kinds = Trigger.model_fields["kind"].annotation.__args__  # type: ignore[union-attr]
    assert set(kinds) == set(BASELINE)


def test_render_never_leaves_placeholders() -> None:
    stats, triggers = stats_with_tracking()
    for trig in triggers[:40]:
        moment = provisional_moment(trig, "t")
        for lang in LANGS:
            title, body, _ = render(moment, Profile(mode="analyst", language=lang),
                                    _context(stats, trig))  # fmt: skip
            assert "{" not in title + body
