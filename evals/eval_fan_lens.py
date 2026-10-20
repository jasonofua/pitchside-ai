"""Fan Lens eval: one card per viewer per explained moment, mode rules respected (no jargon
for casual and kids viewers, Player Cam about the chosen player), first-draft figures
accurate (measured by how often the Fact Checker had to reject)."""

from __future__ import annotations

from evals.harness import Outcome
from evals.scoring import JARGON, AgentScore, latency, rate
from runtime.realnames import real_names_in


def score(outcomes: list[Outcome]) -> AgentScore:
    s = AgentScore("fan_lens")
    cards = jargon_free = cam_cards = cam_focused = 0
    written = rejected = 0
    for o in outcomes:
        written += sum(1 for t in o.traces_for("fan_lens") if t.status in ("ok", "regenerated"))
        rejected += sum(1 for t in o.traces_for("fact_checker") if t.status == "rejected")
        for card in o.overlays:
            if card.source != "agent":
                continue
            profile = o.profiles[card.audience_profile_hash]
            cards += 1
            text = f"{card.title} {card.body}"
            if profile.mode in ("casual", "kids"):
                clean = not JARGON.search(text)
                jargon_free += clean
                if not clean:
                    s.failures.append(f"{o.sample.sample_id}: jargon for {profile.mode}: {text}")
            else:
                jargon_free += 1
            if profile.mode == "player_cam" and profile.favorite_player:
                cam_cards += 1
                cam_focused += o.names[profile.favorite_player] in text
            s.check(not real_names_in(text), f"{o.sample.sample_id}: real-world name")
    s.metrics["agent_cards"] = cards
    s.metrics["mode_rules"] = rate(jargon_free, cards)
    s.metrics["player_cam_focus"] = rate(cam_focused, cam_cards)
    s.metrics["first_draft_accuracy"] = rate(max(written - rejected, 0), written)
    s.metrics.update(latency([
        t.latency_ms for o in outcomes for t in o.traces_for("fan_lens") if t.status == "ok"
    ]))  # fmt: skip
    s.check(cards > 0, "no agent cards reached viewers")
    s.check(float(s.metrics["mode_rules"]) >= 0.95, "mode rules below 0.95")
    s.check(float(s.metrics["player_cam_focus"]) >= 0.8, "Player Cam cards miss the player")
    return s
