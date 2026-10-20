"""Stats-only template cards.

Used three ways: as the immediate stat overlay for a trigger (well under 1 s from the
event), as the fallback when an agent is slow, failing or switched off, and as the last
resort when a card fails fact-checking twice. Every number comes from Match Stats MCP
tool results gathered in a `MomentContext`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.i18n import Lang, t
from contracts import Profile
from contracts.agents import CardDraft, Moment, StatItem


@dataclass
class MomentContext:
    """Tool results for one moment. Keys follow the MCP tool names."""

    match_state: dict[str, Any]
    team_stats: dict[str, Any] | None = None  # get_team_stats(match)
    recent_stats: dict[str, Any] | None = None  # get_team_stats(last_5)
    player: dict[str, Any] | None = None  # get_player_stats(moment.player_id)
    focus_player: dict[str, Any] | None = None  # get_player_stats(profile.favorite_player)
    momentum: dict[str, Any] | None = None  # get_momentum(last_15)
    event: dict[str, Any] | None = None  # the moment's last evidence event (get_events)
    trigger: dict[str, Any] | None = None  # the Stats Engine trigger behind the moment
    extra: list[dict[str, Any]] = field(default_factory=list)

    def payloads(self) -> list[dict[str, Any]]:
        out = [self.match_state]
        for p in (
            self.team_stats, self.recent_stats, self.player, self.focus_player, self.momentum,
            self.event, self.trigger,
        ):  # fmt: skip
            if p:
                out.append(p)
        return out + self.extra

    # ---------------------------------------------------------------- lookups

    def team(self, team_id: str | None) -> dict[str, Any]:
        for side in ("home", "away"):
            line = self.match_state[side]
            if line["team_id"] == team_id:
                return dict(line)
        return dict(self.match_state["home"])

    def teams_stats(self, report: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        if not report:
            return {}, {}
        teams = report["teams"]
        return teams[0], teams[1]

    def score(self) -> str:
        return f"{self.match_state['home']['score']}-{self.match_state['away']['score']}"

    def goal(self, event_ids: list[str]) -> dict[str, Any] | None:
        for g in reversed(self.match_state.get("goals", [])):
            if g["event_id"] in event_ids:
                return dict(g)
        goals = self.match_state.get("goals", [])
        return dict(goals[-1]) if goals else None

    def card(self, event_ids: list[str]) -> dict[str, Any] | None:
        for c in reversed(self.match_state.get("cards", [])):
            if c["event_id"] in event_ids:
                return dict(c)
        return None


def _stat(label_key: str, lang: Lang, value: float | str, unit: str = "") -> StatItem:
    return StatItem(label=t(label_key, lang), value=value, unit=unit)


def _limit(stats: list[StatItem], profile: Profile) -> list[StatItem]:
    keep = {"analyst": 4, "casual": 2, "player_cam": 3, "kids": 1}[profile.mode]
    return stats[:keep]


def _player_name(ctx: MomentContext) -> str:
    if ctx.player:
        return str(ctx.player.get("short_name") or ctx.player.get("name"))
    return ""


def render(moment: Moment, profile: Profile, ctx: MomentContext) -> tuple[str, str, list[StatItem]]:
    """(title, body, stats) for a moment in the profile's language and mode."""
    lang: Lang = profile.language
    kind = moment.kind
    home, away = ctx.match_state["home"], ctx.match_state["away"]
    names = {"home": home["short_name"], "away": away["short_name"], "score": ctx.score()}
    stats: list[StatItem] = []
    title = body = ""

    if kind == "goal":
        goal = ctx.goal(list(moment.evidence_event_ids)) or {}
        team = ctx.team(goal.get("team_id") or moment.team_id)
        title = t("goal", lang, team=team["name"])
        body = t("goal_body", lang, player=goal.get("player_name", ""),
                 minute=goal.get("minute", moment.minute), **names)  # fmt: skip
        if goal.get("xg") is not None:
            stats.append(_stat("label_xg", lang, round(float(goal["xg"]), 2), "xG"))
        if goal.get("shot_speed_kmh") is not None:
            stats.append(_stat("label_shot_speed", lang, goal["shot_speed_kmh"], "km/h"))
        stats.append(_stat("label_score", lang, ctx.score()))
    elif kind == "card":
        card = ctx.card(list(moment.evidence_event_ids)) or {}
        color = card.get("card_color", "yellow")
        title = t(color, lang, player=card.get("player_name", _player_name(ctx)))
        body = t("card_body", lang, team=ctx.team(card.get("team_id"))["name"],
                 minute=card.get("minute", moment.minute))  # fmt: skip
    elif kind == "speed_burst" and ctx.player:
        top = ctx.player.get("top_speed_kmh")
        title = t("speed", lang, player=_player_name(ctx), value=top)
        body = t("speed_body", lang)
        if top is not None:
            stats.append(_stat("label_top_speed", lang, top, "km/h"))
        stats.append(_stat("label_distance", lang, ctx.player["distance_km"], "km"))
    elif kind == "big_chance":
        ev = ctx.event or {}
        xg_value = _trigger_value(ctx)
        outcome = t(f"outcome_{ev.get('outcome', 'saved')}", lang)
        plain = profile.mode in ("casual", "kids")
        title = (
            t("chance_plain", lang, team=ctx.team(moment.team_id)["name"])
            if plain
            else t("xg", lang, value=xg_value)
        )
        body = t("xg_body", lang, player=_player_name(ctx),
                 team=ctx.team(moment.team_id)["short_name"], outcome=outcome)  # fmt: skip
        if ev.get("ball_speed_kmh") is not None:
            stats.append(_stat("label_shot_speed", lang, ev["ball_speed_kmh"], "km/h"))
        h, a = ctx.teams_stats(ctx.team_stats)
        if h and not plain:
            stats.append(_stat("label_xg", lang, f"{h['xg']} - {a['xg']}"))
    elif kind == "hard_pass":
        value = _trigger_value(ctx)
        title = t("pass_difficulty", lang, value=value)
        body = t("pass_difficulty_body", lang, player=_player_name(ctx))
        if ctx.player and ctx.player.get("pass_accuracy_pct") is not None:
            stats.append(_stat("label_pass_accuracy", lang, ctx.player["pass_accuracy_pct"], "%"))
    elif kind == "momentum_swing" and ctx.momentum:
        now = ctx.momentum["now"]
        swing = now["swing"]
        title = t("momentum", lang, value=f"{swing:+g}")
        # The direction of the swing decides the story: towards control or towards chaos.
        key = "momentum_body_control" if swing >= 0 else "momentum_body_chaos"
        body = t(key, lang, index=f"{now['index']:+g}")
        stats.append(_stat("label_momentum", lang, now["index"]))
    elif kind == "spell":
        h, a = ctx.teams_stats(ctx.recent_stats)
        top = h if h and h["possession_pct"] >= a["possession_pct"] else a
        title = t("spell", lang, team=top.get("short_name", ""))
        body = t("spell_body", lang, poss=top.get("possession_pct", ""))
        if top:
            stats.append(_stat("label_possession", lang, top["possession_pct"], "%"))
    elif kind in ("half_time", "full_time"):
        h, a = ctx.teams_stats(ctx.team_stats)
        title = t(kind, lang, **names)
        if h:
            body = t("period_body", lang, home_poss=h["possession_pct"],
                     away_poss=a["possession_pct"], home_shots=h["shots"],
                     away_shots=a["shots"])  # fmt: skip
            stats.append(_stat("label_xg", lang, f"{h['xg']} - {a['xg']}"))
            accuracy = f"{h['pass_accuracy_pct']}% - {a['pass_accuracy_pct']}%"
            stats.append(_stat("label_pass_accuracy", lang, accuracy))
    if not title:
        title = moment.summary[:120] or t("label_score", lang)
        body = body or ""

    if profile.mode == "player_cam" and ctx.focus_player:
        fp = ctx.focus_player
        stats.insert(0, _stat("label_touches", lang, fp["touches"]))
        stats.insert(1, _stat("label_distance", lang, fp["distance_km"], "km"))
    return title[:120], body[:600], _limit(stats, profile)


def _trigger_value(ctx: MomentContext) -> Any:
    """The measured value behind the moment (xG of the shot, pass difficulty, ...)."""
    value = (ctx.trigger or {}).get("value")
    return "" if value is None else value


def template_card(
    moment: Moment, profile: Profile, profile_hash: str, ctx: MomentContext, *, draft_id: str
) -> CardDraft:
    title, body, stats = render(moment, profile, ctx)
    optional: dict[str, Any] = {}
    if moment.player_id:
        optional["player_id"] = moment.player_id
    if moment.team_id:
        optional["team_id"] = moment.team_id
    return CardDraft(
        draft_id=draft_id,
        moment_id=moment.moment_id,
        match_id=moment.match_id,
        trace_id=moment.trace_id,
        profile_hash=profile_hash,
        mode=profile.mode,
        lang=profile.language,
        kind=moment.kind,
        title=title,
        body=body,
        stats=stats,
        evidence_event_ids=list(moment.evidence_event_ids),
        importance=moment.importance,
        source="template",
        **optional,
    )
