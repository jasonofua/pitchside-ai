"""Everything one trigger's workflow run shares: the trigger, the moment, the viewers'
profiles at trigger time, MCP data for templates and fact-checking, and publishing."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agents.crew import Crew
from agents.numbers import Facts
from agents.producer_rules import is_stale, rule_plan, to_overlay
from agents.stats_client import StatsToolError
from agents.templates import MomentContext, template_card
from agents.tracing import Step
from contracts import OverlayCard, Profile, Trigger
from contracts.agents import CardDraft, Moment, ProducerPlan, Story

log = logging.getLogger(__name__)

# Trigger kind -> (moment kind, baseline importance) when the model is not consulted.
BASELINE: dict[str, tuple[str, float]] = {
    "goal": ("goal", 0.95),
    "card": ("card", 0.35),
    "half_time": ("half_time", 0.75),
    "full_time": ("full_time", 0.8),
    "xg": ("big_chance", 0.65),
    "speed": ("speed_burst", 0.35),
    "pass_difficulty": ("hard_pass", 0.4),
    "momentum_swing": ("momentum_swing", 0.6),
    "tick": ("spell", 0.2),
}
# Triggers that get an immediate stats-only card (under 1 s from the event).
INSTANT = frozenset(
    {"goal", "card", "half_time", "full_time", "xg", "speed", "pass_difficulty", "momentum_swing"}
)


def provisional_moment(trigger: Trigger, trace_id: str) -> Moment:
    kind, importance = BASELINE[trigger.kind]
    optional: dict[str, Any] = {}
    if trigger.team_id:
        optional["team_id"] = trigger.team_id
    if trigger.player_id:
        optional["player_id"] = trigger.player_id
    from stats.metrics import minute_label

    return Moment(
        moment_id=f"m:{trigger.trigger_id}",
        match_id=trigger.match_id,
        trace_id=trace_id,
        trigger_id=trigger.trigger_id,
        kind=kind,
        period=trigger.period,
        clock_ms=trigger.clock_ms,
        minute=minute_label(trigger.period, trigger.clock_ms),
        importance=importance,
        summary=f"{trigger.kind.replace('_', ' ')} trigger",
        evidence_event_ids=list(trigger.event_ids),
        **optional,
    )


@dataclass
class Run:
    crew: Crew
    trigger: Trigger
    trace_id: str
    moment: Moment
    profiles: dict[str, Profile]
    started: float = field(default_factory=time.monotonic)
    _ctx: dict[str, MomentContext] = field(default_factory=dict)
    _facts: Facts | None = None
    _facts_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    recorded: list[Any] = field(default_factory=list)  # MCP results the writers saw
    templated: set[str] = field(default_factory=set)  # profile hashes with a template card
    story: Story | None = None  # set by the Fan Lens, used to regenerate rejected cards
    memory: dict[str, tuple[int, int]] = field(default_factory=dict)  # per match, shared

    @property
    def match_id(self) -> str:
        return self.trigger.match_id

    def step(self, agent: str, profile_hash: str | None = None) -> Step:
        return Step(
            agent=agent,
            model=self.crew.model_name(agent) if agent in self.crew.prompts else "code",
            trace_id=self.trace_id,
            match_id=self.match_id,
            moment_id=self.moment.moment_id,
            profile_hash=profile_hash,
            clock_ms=self.trigger.clock_ms,
        )

    # --------------------------------------------------------------- MCP data

    async def _call(self, tool: str, **args: Any) -> Any:
        try:
            return await self.crew.stats.call(tool, match_id=self.match_id, **args)
        except StatsToolError:
            return None

    async def context(self, focus_player: str | None = None) -> MomentContext:
        """Tool results for templates, fetched once per run (per focus player)."""
        key = focus_player or ""
        if key in self._ctx:
            return self._ctx[key]
        base = self._ctx.get("")
        if base is None:
            pid = self.moment.player_id
            state, team, recent, player, momentum, events = await asyncio.gather(
                self._call("get_match_state"),
                self._call("get_team_stats", window="match"),
                self._call("get_team_stats", window="last_5"),
                self._call("get_player_stats", player_id=pid) if pid else _none(),
                self._call("get_momentum", window="last_15"),
                self._call("get_events", since=max(self.trigger.seq - 3, -1), limit=4),
            )
            event = None
            ids = set(self.moment.evidence_event_ids)
            for e in reversed(events or []):
                if e["event_id"] in ids:
                    event = e
                    break
            base = MomentContext(
                match_state=state or {}, team_stats=team, recent_stats=recent, player=player,
                momentum=momentum, event=event,
                trigger=self.trigger.model_dump(mode="json", exclude_none=True),
            )  # fmt: skip
            self._ctx[""] = base
        if not focus_player:
            return base
        focus = await self._call("get_player_stats", player_id=focus_player)
        ctx = MomentContext(**{**base.__dict__, "focus_player": focus})
        self._ctx[key] = ctx
        return ctx

    async def facts(self) -> Facts:
        """Numbers known to be true now: fresh MCP reads plus what the writers were given."""
        async with self._facts_lock:
            if self._facts is None:
                ctx = await self.context()
                halves, last10, last15 = await asyncio.gather(
                    self._call("compare_periods"),
                    self._call("get_team_stats", window="last_10"),
                    self._call("get_team_stats", window="last_15"),
                )
                players = [p.favorite_player for p in self.profiles.values() if p.favorite_player]
                focus = await asyncio.gather(
                    *(self._call("get_player_stats", player_id=p) for p in set(players))
                )
                self._facts = Facts.from_payloads(
                    [*ctx.payloads(), halves, last10, last15, *focus, *self.recorded]
                )
            else:
                for payload in self.recorded:
                    self._facts.absorb(payload)
            return self._facts

    # ------------------------------------------------------------- publishing

    async def publish(self, card: CardDraft, plan: ProducerPlan) -> OverlayCard:
        state = (await self.context()).match_state
        clock = state.get("clock_ms", self.trigger.clock_ms) if state else self.trigger.clock_ms
        overlay = to_overlay(card, plan, clock)
        await self.crew.bus.publish("overlays", self.match_id, overlay)
        await self.crew.store.put_doc(
            "overlay", self.match_id, overlay.overlay_id, overlay.model_dump(mode="json")
        )
        return overlay

    async def is_stale(self, ttl_s: int) -> bool:
        state = await self._call("get_match_state")
        if not state:
            return False
        return is_stale(
            self.moment.clock_ms, state["clock_ms"], ttl_s, state["period"] == self.moment.period
        )

    async def template_cards(self, only: set[str] | None = None) -> None:
        """Publish the stats-only card for each viewer (once per viewer per run)."""
        if self.trigger.kind not in INSTANT or not self.profiles:
            return
        step = self.step("producer")
        step.model = "code"
        sent = 0
        for h, profile in self.profiles.items():
            if h in self.templated or (only is not None and h not in only):
                continue
            ctx = await self.context(profile.favorite_player)
            if not ctx.match_state:
                continue
            draft = template_card(
                self.moment, profile, h, ctx, draft_id=f"{self.moment.moment_id}:{h}:t"
            )
            await self.publish(draft, rule_plan(draft))
            self.templated.add(h)
            sent += 1
        if sent:
            step.detail = f"stats-only {self.moment.kind} card for {sent} viewer(s)"
            await self.crew.tracer.emit(step)

    def template_for(self, profile_hash: str, ctx: MomentContext) -> CardDraft:
        profile = self.profiles[profile_hash]
        return template_card(
            self.moment, profile, profile_hash, ctx,
            draft_id=f"{self.moment.moment_id}:{profile_hash}:t",
        )  # fmt: skip


async def _none() -> None:
    return None
