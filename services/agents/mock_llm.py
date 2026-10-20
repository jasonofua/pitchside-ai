"""An offline stand-in for the Foundry models, for local mode without any LLM and for tests.

`MockChatClient` is a real Agent Framework chat client (function invocation, middleware
and telemetry layers on top of BaseChatClient). Each agent gets one with its role. On
each turn it reads the JSON request in the user message and the tool results so far, and
either asks for more MCP tools (as function calls, which Agent Framework executes against
the Match Stats MCP server) or answers with JSON for the agent's output model. It never
computes a statistic: every number it writes is copied from a tool result.

The mock Fan Lens writes from the phrase bank and remembers what it rendered, so the mock
Localizer can render the same phrases in the viewer's language.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Mapping, Sequence
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
)
from agent_framework.observability import ChatTelemetryLayer

from agents.i18n import PHRASES, Lang, t
from agents.mock_phrases import BODIES, GROUP, HEADLINES, LINES, WHY

JSON_BLOCK = re.compile(r"```json\s*(\{.*\})\s*```", re.S)

# Rendered English text -> (phrase key, values), so the mock Localizer can re-render it.
_RENDERED: dict[str, tuple[str, dict[str, Any]]] = {}
_LABEL_KEYS = {table["en"]: key for key, table in PHRASES.items() if key.startswith("label_")}


class ToolCalls(list[tuple[str, dict[str, Any]]]):
    """A brain's request for MCP tool calls: [(tool name, arguments), ...]."""


Results = dict[str, list[tuple[dict[str, Any], Any]]]


def _request(messages: Sequence[Message]) -> dict[str, Any]:
    for msg in reversed(messages):
        if msg.role != "user":
            continue
        m = JSON_BLOCK.search(msg.text or "")
        if m:
            parsed: dict[str, Any] = json.loads(m.group(1))
            return parsed
    return {}


def _results(messages: Sequence[Message]) -> Results:
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    out: Results = {}
    for msg in messages:
        for c in msg.contents:
            if c.type == "function_call" and c.call_id and c.name:
                calls[c.call_id] = (c.name, c.parse_arguments() or {})
            elif c.type == "function_result" and c.call_id in calls:
                name, args = calls[c.call_id]
                try:
                    value = json.loads(c.result or "null")
                except (TypeError, ValueError):
                    value = c.result
                if isinstance(value, dict) and set(value) == {"result"}:
                    value = value["result"]
                out.setdefault(name, []).append((args, value))
    return out


def _get(results: Results, tool: str, **match: Any) -> Any:
    """The tool's result for these arguments; error text counts as no result."""
    for args, value in results.get(tool, []):
        if all(args.get(k) == v for k, v in match.items()) and isinstance(value, dict | list):
            return value
    return None


def _attempts(results: Results, tool: str, **match: Any) -> int:
    return sum(
        1 for args, _ in results.get(tool, []) if all(args.get(k) == v for k, v in match.items())
    )


def _need(results: Results, wanted: list[tuple[str, dict[str, Any]]]) -> ToolCalls:
    """Tools still to call. A failed call is retried once; after that the brain writes with
    what it has (as a model would after an error result)."""
    return ToolCalls(
        (tool, args)
        for tool, args in wanted
        if _get(results, tool, **args) is None and _attempts(results, tool, **args) < 2
    )


# ----------------------------------------------------------------------------- brains


def _team_names(state: dict[str, Any]) -> dict[str, str]:
    return {
        "home": state["home"]["short_name"],
        "away": state["away"]["short_name"],
        "score": f"{state['home']['score']}-{state['away']['score']}",
    }


def _side(state: dict[str, Any], team_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if team_id == state["away"]["team_id"]:
        return state["away"], state["home"]
    return state["home"], state["away"]


def _team_line(report: dict[str, Any] | None, team_id: str | None) -> dict[str, Any]:
    if not report:
        return {}
    teams = report["teams"]
    for line in teams:
        if line["team_id"] == team_id:
            return dict(line)
    return dict(teams[0])


def moment_detector(req: dict[str, Any], res: Results) -> ToolCalls | dict[str, Any]:
    trig = req["trigger"]
    mid = trig["match_id"]
    wanted = [("get_match_state", {"match_id": mid})]
    if trig["kind"] in ("tick", "momentum_swing"):
        wanted.append(("get_team_stats", {"match_id": mid, "window": "last_5"}))
    need = _need(res, wanted)
    if need:
        return need
    kind = trig["kind"]
    state = _get(res, "get_match_state", match_id=mid) or {
        "home": {"score": 0}, "away": {"score": 0}, "cards": [],
    }  # fmt: skip
    close = abs(state["home"]["score"] - state["away"]["score"]) <= 1
    if kind == "goal":
        return {"is_moment": True, "kind": "goal", "importance": 0.95, "summary": "A goal."}
    if kind == "card":
        red = any(
            c["card_color"] != "yellow"
            for c in state["cards"]
            if c["event_id"] in trig["event_ids"]
        )
        return {
            "is_moment": True, "kind": "card", "importance": 0.9 if red else 0.35,
            "summary": "A sending-off." if red else "A booking.",
        }  # fmt: skip
    if kind in ("half_time", "full_time"):
        return {"is_moment": True, "kind": kind, "importance": 0.75, "summary": "Period ends."}
    if kind == "xg":
        imp = 0.75 if close else 0.6
        return {"is_moment": True, "kind": "big_chance", "importance": imp,
                "summary": "A big chance."}  # fmt: skip
    if kind == "speed":
        return {"is_moment": True, "kind": "speed_burst", "importance": 0.35,
                "summary": "A sprint above 32 km/h."}  # fmt: skip
    if kind == "pass_difficulty":
        return {"is_moment": True, "kind": "hard_pass", "importance": 0.4,
                "summary": "A pass of high difficulty."}  # fmt: skip
    recent = _get(res, "get_team_stats", match_id=mid, window="last_5")
    top = max(recent["teams"], key=lambda t_: t_["possession_pct"]) if recent else None
    dominant = top is not None and top["possession_pct"] >= 60
    if kind == "momentum_swing":
        return {"is_moment": True, "kind": "momentum_swing", "importance": 0.6,
                "summary": "The momentum index swung."}  # fmt: skip
    return {
        "is_moment": dominant, "kind": "spell", "importance": 0.5 if dominant else 0.1,
        "summary": "One team is dominating the ball." if dominant else "Nothing notable.",
    }  # fmt: skip


def _values(
    req: dict[str, Any], res: Results, mid: str, team_id: str | None, player_id: str | None
) -> dict[str, Any]:
    """Every value the phrase templates may use, copied from tool results."""
    state = _get(res, "get_match_state", match_id=mid) or {}
    names = _team_names(state) if state else {}
    team, opp = _side(state, team_id) if state else ({}, {})
    match_report = _get(res, "get_team_stats", match_id=mid, window="match")
    recent = _get(res, "get_team_stats", match_id=mid, window="last_10")
    last5 = _get(res, "get_team_stats", match_id=mid, window="last_5")
    tl = _team_line(match_report, team.get("team_id"))
    rl = _team_line(recent, team.get("team_id"))
    l5 = _team_line(last5, team.get("team_id"))
    player = _get(res, "get_player_stats", match_id=mid, player_id=player_id) if player_id else None
    momentum = _get(res, "get_momentum", match_id=mid, window="last_15")
    trig = req.get("trigger") or {}
    goal = next((g for g in reversed(state.get("goals", []))
                 if g["event_id"] in (req.get("moment", {}).get("evidence_event_ids") or [])),
                None)  # fmt: skip
    teams = (match_report or {}).get("teams") or [{}, {}]
    v: dict[str, Any] = {
        **names,
        "team": team.get("name", ""),
        "opp": opp.get("name", ""),
        "shots": tl.get("shots", ""),
        "xg": tl.get("xg", ""),
        "fouls": tl.get("fouls", ""),
        "ppda": tl.get("ppda", ""),
        "accuracy": tl.get("pass_accuracy_pct", ""),
        "recent_poss": rl.get("possession_pct", ""),
        "poss": l5.get("possession_pct", "") or rl.get("possession_pct", ""),
        "player": (player or {}).get("short_name") or (goal or {}).get("player_name", ""),
        "touches": (player or {}).get("touches", ""),
        "distance": (player or {}).get("distance_km", ""),
        "top_speed": (player or {}).get("top_speed_kmh", ""),
        "sprints": (player or {}).get("sprints", ""),
        "shot_xg": (goal or {}).get("xg") if goal else trig.get("value", ""),
        "index": (momentum or {}).get("now", {}).get("index", ""),
        "swing": (momentum or {}).get("now", {}).get("swing", ""),
        "home_xg": teams[0].get("xg", ""),
        "away_xg": teams[-1].get("xg", ""),
        "home_poss": teams[0].get("possession_pct", ""),
        "away_poss": teams[-1].get("possession_pct", ""),
        "home_acc": teams[0].get("pass_accuracy_pct", ""),
        "away_acc": teams[-1].get("pass_accuracy_pct", ""),
    }
    return v


def _cite(label: str, value: Any, unit: str, source: str) -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit, "source": source}


def tactical_analyst(req: dict[str, Any], res: Results) -> ToolCalls | dict[str, Any]:
    moment = req["moment"]
    mid = moment["match_id"]
    wanted = [
        ("get_match_state", {"match_id": mid}),
        ("get_team_stats", {"match_id": mid, "window": "match"}),
        ("get_team_stats", {"match_id": mid, "window": "last_10"}),
    ]
    if moment.get("player_id"):
        wanted.append(("get_player_stats", {"match_id": mid, "player_id": moment["player_id"]}))
    if moment["kind"] in ("momentum_swing", "spell"):
        wanted.append(("get_momentum", {"match_id": mid, "window": "last_15"}))
    need = _need(res, wanted)
    if need:
        return need
    v = _values(req, res, mid, moment.get("team_id"), moment.get("player_id"))
    kind = moment["kind"]
    cites = [
        _cite("Shots", v["shots"], "", "get_team_stats.match.shots"),
        _cite("xG", v["xg"], "xG", "get_team_stats.match.xg"),
        _cite(
            "Possession (last 10)", v["recent_poss"], "%", "get_team_stats.last_10.possession_pct"
        ),
    ]
    if v["distance"] != "":
        cites.append(_cite("Distance", v["distance"], "km", "get_player_stats.distance_km"))
    return {
        "headline": HEADLINES[kind].format(**v)[:120],
        "why_it_matters": WHY[kind].format(**v)[:500],
        "stats_cited": cites,
    }


def narrator(req: dict[str, Any], res: Results) -> ToolCalls | dict[str, Any]:
    moment = req["moment"]
    mid = moment["match_id"]
    wanted = [
        ("get_match_state", {"match_id": mid}),
        ("get_team_stats", {"match_id": mid, "window": "match"}),
    ]
    if moment.get("player_id"):
        wanted.append(("get_player_stats", {"match_id": mid, "player_id": moment["player_id"]}))
    need = _need(res, wanted)
    if need:
        return need
    v = _values(req, res, mid, moment.get("team_id"), moment.get("player_id"))
    kind = moment["kind"]
    text = LINES[kind].format(**v)
    if req.get("commentary_kind") in ("half_time_story", "full_time_recap"):
        text = f"{text} {WHY[kind].format(**v)}"
    return {"text": text[:900], "stats_cited": []}


def _render(key: str, lang: Lang, values: dict[str, Any], table: dict[str, dict[Lang, str]]) -> str:
    text = (table[key].get(lang) or table[key]["en"]).format(**values)
    if lang == "en":
        _RENDERED[text] = (key, dict(values))
    return text


TITLE_KEY = {
    "goal": "goal", "big_chance": "xg", "speed_burst": "speed", "hard_pass": "pass_difficulty",
    "momentum_swing": "momentum", "spell": "spell", "half_time": "half_time",
    "full_time": "full_time",
}  # fmt: skip


def fan_lens(req: dict[str, Any], res: Results) -> ToolCalls | dict[str, Any]:
    story, profile = req["story"], req["profile"]
    moment = story["moment"]
    mid = moment["match_id"]
    focus = profile.get("favorite_player") if profile["mode"] == "player_cam" else None
    player_id = focus or moment.get("player_id")
    wanted = [
        ("get_match_state", {"match_id": mid}),
        ("get_team_stats", {"match_id": mid, "window": "match"}),
        ("get_team_stats", {"match_id": mid, "window": "last_5"}),
    ]
    if player_id:
        wanted.append(("get_player_stats", {"match_id": mid, "player_id": player_id}))
    if moment["kind"] in ("momentum_swing", "spell"):
        wanted.append(("get_momentum", {"match_id": mid, "window": "last_15"}))
    need = _need(res, wanted)
    if need:
        return need
    v = _values({"moment": moment, "trigger": req.get("trigger")}, res, mid,
                moment.get("team_id"), player_id)  # fmt: skip
    v["value"] = v["shot_xg"] if moment["kind"] == "big_chance" else v.get("top_speed", "")
    if moment["kind"] == "hard_pass":
        v["value"] = (req.get("trigger") or {}).get("value", "")
    if moment["kind"] == "momentum_swing":
        v["value"] = f"{v['swing']:+g}" if isinstance(v["swing"], int | float) else v["swing"]
    kind, mode = moment["kind"], profile["mode"]
    group = GROUP[kind]
    if kind == "card":
        state = _get(res, "get_match_state", match_id=mid) or {}
        ids = moment.get("evidence_event_ids") or []
        card = next((c for c in state.get("cards", []) if c["event_id"] in ids), None)
        color = card["card_color"] if card else "yellow"
        title = _render(color, "en", {"player": card["player_name"] if card else ""}, PHRASES)
    elif kind == "big_chance" and mode in ("casual", "kids"):
        title = _render("chance_plain", "en", v, PHRASES)  # no xG for these viewers
    else:
        title_key = TITLE_KEY[kind]
        title = _render(title_key, "en", v, PHRASES)
    if mode == "player_cam":
        involved = moment.get("player_id") == focus
        body_key = "cam_involved" if involved else "cam_watching"
    else:
        body_key = f"{mode}_{group}"
        if mode == "casual" and kind == "goal" and profile.get("favorite_club") not in (
            None, moment.get("team_id")
        ):  # fmt: skip
            body_key = "casual_goal_rival"
    body = _render(body_key, "en", v, BODIES)
    stats: list[dict[str, Any]] = []
    if mode == "analyst":
        stats = [
            {"label": "xG", "value": v["xg"], "unit": "xG"},
            {"label": "Possession", "value": v["poss"], "unit": "%"},
        ]
    elif mode == "player_cam" and v["distance"] != "":
        stats = [{"label": "Distance", "value": v["distance"], "unit": "km"}]
    elif kind == "goal":
        stats = [{"label": "Score", "value": v["score"], "unit": ""}]
    stats = [s for s in stats if s["value"] not in ("", None)]
    return {"title": title[:120], "body": body[:600], "stats": stats}


def localizer(req: dict[str, Any], res: Results) -> dict[str, Any]:
    card, lang = req["card"], req["language"]

    def tr(text: str, table: dict[str, dict[Lang, str]]) -> str:
        key, values = _RENDERED.get(text, ("", {}))
        if not key or key not in table:
            return text
        return (table[key].get(lang) or table[key]["en"]).format(**values)

    title = tr(card["title"], PHRASES)
    body = tr(card["body"], BODIES)
    stats = []
    for s in card["stats"]:
        key = _LABEL_KEYS.get(s["label"])
        stats.append({**s, "label": t(key, lang) if key else s["label"]})
    return {"title": title, "body": body, "stats": stats}


def fact_checker(req: dict[str, Any], res: Results) -> dict[str, Any]:
    return {"verdict": "pass", "reason": "No contradiction with match state (offline check)."}


def producer(req: dict[str, Any], res: Results) -> dict[str, Any]:
    card = req["card"]
    full = card["kind"] in ("goal", "half_time", "full_time") and card["importance"] >= 0.8
    return {
        "slot": "full_card" if full else "lower_third",
        "priority": 5 if full else 3,
        "ttl_s": 20 if full else 14,
    }


BRAINS: dict[str, Any] = {
    "moment_detector": moment_detector,
    "tactical_analyst": tactical_analyst,
    "narrator": narrator,
    "fan_lens": fan_lens,
    "localizer": localizer,
    "fact_checker": fact_checker,
    "producer": producer,
}


class MockChatClient(
    FunctionInvocationLayer[Any],
    ChatMiddlewareLayer[Any],
    ChatTelemetryLayer[Any],
    BaseChatClient[Any],
):
    """Deterministic offline 'model' for one agent role."""

    OTEL_PROVIDER_NAME = "pitchside.mock"

    def __init__(self, role: str, model: str = "mock", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if role not in BRAINS:
            raise ValueError(f"no mock brain for {role!r}")
        self.role = role
        self.model = model

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse]:
        if stream:
            raise NotImplementedError("the mock model does not stream")

        async def respond() -> ChatResponse:
            out = BRAINS[self.role](_request(messages), _results(messages))
            if isinstance(out, ToolCalls):
                n = sum(1 for m in messages for c in m.contents if c.type == "function_call")
                contents = [
                    Content.from_function_call(call_id=f"call_{n + i}", name=name, arguments=args)
                    for i, (name, args) in enumerate(out)
                ]
                return ChatResponse(messages=[Message("assistant", contents)], model=self.model)
            text = json.dumps(out, ensure_ascii=False)
            return ChatResponse(messages=[Message("assistant", [text])], model=self.model)

        return respond()
