"""The Producer's code half: slot, priority and timing rules, staleness and de-duplication.

The Producer model proposes a plan for important agent cards; these rules give the plan
for everything else, and clamp every plan to what the overlay contract and the screen
allow.
"""

from __future__ import annotations

from contracts import OverlayCard
from contracts.agents import CardDraft, ProducerPlan
from contracts.overlay import StatItem as OverlayStat

FULL_CARD_KINDS = frozenset({"goal", "half_time", "full_time"})

# kind -> (slot, priority, ttl seconds) for the immediate stats-only card.
TEMPLATE_PLAN: dict[str, tuple[str, int, int]] = {
    "goal": ("full_card", 5, 12),
    "card": ("ticker", 3, 12),
    "speed_burst": ("player_tag", 3, 8),
    "hard_pass": ("player_tag", 3, 8),
    "big_chance": ("lower_third", 4, 12),
    "momentum_swing": ("corner_bug", 3, 20),
    "spell": ("ticker", 2, 12),
    "half_time": ("full_card", 5, 30),
    "full_time": ("full_card", 5, 45),
}


def reading_ttl_s(card: CardDraft) -> int:
    """Long enough to read the card aloud twice at about 3 words a second."""
    words = len(f"{card.title} {card.body}".split())
    return max(8, min(30, round(2 * words / 3)))


def rule_plan(card: CardDraft) -> ProducerPlan:
    if card.source == "template":
        slot, priority, ttl = TEMPLATE_PLAN.get(card.kind, ("ticker", 2, 10))
        if card.kind == "card" and card.importance >= 0.8:  # a sending-off
            slot, priority = "lower_third", 4
    else:
        slot, priority, ttl = "lower_third", 3, reading_ttl_s(card)
        if card.kind in ("goal", "full_time", "half_time"):
            priority, ttl = 5, max(ttl, 20)
        elif card.kind in ("speed_burst", "hard_pass") and card.importance < 0.5:
            slot, priority = "player_tag", 3
        elif card.kind == "spell" or card.importance < 0.45:
            slot, priority = "ticker", 2
    if card.mode in ("casual", "kids") and card.importance < 0.5 and slot == "lower_third":
        slot, priority = "ticker", 1
    return ProducerPlan(slot=slot, priority=priority, ttl_s=ttl)


def clamp_plan(plan: ProducerPlan, card: CardDraft) -> ProducerPlan:
    """Keep a model's plan within the house rules."""
    slot = plan.slot
    if slot == "full_card" and (card.kind not in FULL_CARD_KINDS or card.importance < 0.8):
        slot = "lower_third"
    if slot == "player_tag" and not card.player_id:
        slot = "lower_third"
    priority = max(1, min(5, plan.priority))
    ttl = max(4, min(60, plan.ttl_s))
    return ProducerPlan(slot=slot, priority=priority, ttl_s=ttl)


def overlay_id(card: CardDraft) -> str:
    """Template and agent cards for the same moment and viewer share an id, so the upgraded
    card replaces the template on screen."""
    return f"{card.moment_id}:{card.profile_hash}"


def to_overlay(card: CardDraft, plan: ProducerPlan, clock_ms: int) -> OverlayCard:
    return OverlayCard(
        overlay_id=overlay_id(card),
        match_id=card.match_id,
        clock_ms=clock_ms,
        slot=plan.slot,
        priority=plan.priority,
        ttl_ms=plan.ttl_s * 1000,
        audience_profile_hash=card.profile_hash,
        lang=card.lang,
        title=card.title[:120],
        body=card.body[:600],
        stats=[
            OverlayStat(label=s.label, value=s.value, **({"unit": s.unit} if s.unit else {}))
            for s in card.stats
        ],
        evidence_event_ids=list(card.evidence_event_ids),
        trace_id=card.trace_id,
        kind=card.kind,
        source=card.source,
        **({"player_id": card.player_id} if card.player_id else {}),
        **({"team_id": card.team_id} if card.team_id else {}),
    )


def is_stale(moment_clock_ms: int, now_clock_ms: int, ttl_s: int, same_period: bool) -> bool:
    """A card is stale once the match clock has moved past its moment by more than its ttl."""
    if not same_period:
        return True
    return now_clock_ms - moment_clock_ms > ttl_s * 1000
