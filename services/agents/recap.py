"""The full-time recap: headline, story, five key moments, player of the match and stat
cards, in every supported language, stored for the Recap page and its JSON export."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agents.i18n import LANGS, t
from agents.localizer import LANG_NAMES
from agents.numbers import Facts, check_text
from agents.run import Run
from agents.stats_client import StatsToolError
from contracts.agents import CardText
from runtime.config import Settings
from sim.world import load_world
from stats.metrics import player_of_the_match_score

log = logging.getLogger(__name__)

TASK = "Translate this full-time recap into the target language."


async def _call(run: Run, tool: str, **args: Any) -> Any:
    try:
        return await run.crew.stats.call(tool, match_id=run.match_id, **args)
    except StatsToolError:
        return None


async def _player_of_the_match(run: Run, home: str, away: str) -> dict[str, Any] | None:
    world = load_world()
    ids = [p.player_id for c in world.clubs if c.team_id in (home, away) for p in c.players]
    stats = await asyncio.gather(*(_call(run, "get_player_stats", player_id=pid) for pid in ids))
    played = [s for s in stats if s and s["minutes_played"] > 0]
    if not played:
        return None
    best = max(
        played,
        key=lambda s: player_of_the_match_score(
            s["goals"], s["xg"], s["key_passes"], s["shots_on_target"], s["tackles_won"],
            s["interceptions"], s["distance_km"],
        ),
    )  # fmt: skip
    return {
        "player_id": best["player_id"],
        "name": best["name"],
        "team_id": best["team_id"],
        "stats": [
            {"label": "Goals", "value": best["goals"]},
            {"label": "xG", "value": best["xg"]},
            {"label": "Key passes", "value": best["key_passes"]},
            {"label": "Distance", "value": best["distance_km"], "unit": "km"},
            *(
                [{"label": "Top speed", "value": best["top_speed_kmh"], "unit": "km/h"}]
                if best["top_speed_kmh"] is not None
                else []
            ),
        ],
    }


async def _localize(run: Run, title: str, body: str, lang: str, facts: Facts) -> tuple[str, str]:
    if lang == "en" or not body:
        return title, body
    step = run.step("localizer")
    payload = {"card": {"title": title, "body": body, "stats": []}, "language": lang,
               "language_name": LANG_NAMES[lang]}  # fmt: skip
    try:
        with run.crew.tracer.span(step):
            text, _ = await run.crew.run("localizer", TASK, payload, CardText, step)
        for piece in (text.title, text.body):
            _, bad = check_text(piece, facts)
            if bad:
                raise ValueError(f"recap translation changed a figure: {bad[0].cited}")
        step.detail = f"recap {LANG_NAMES[lang]}"
        return text.title[:200] or title, text.body[:1500] or body
    except Exception as exc:
        step.status, step.detail = "fallback", f"recap {lang}: {type(exc).__name__}; English kept"
        return title, body
    finally:
        await run.crew.tracer.emit(step)


async def build_recap(run: Run) -> dict[str, Any]:
    crew, mid = run.crew, run.match_id
    state, report = await asyncio.gather(
        _call(run, "get_match_state"), _call(run, "get_team_stats", window="match")
    )
    if not state or not report:
        return {}
    home, away = state["home"], state["away"]
    score = f"{home['score']}-{away['score']}"
    moments = await crew.store.docs("moment", mid, limit=500)
    insights = {i["moment_id"]: i for i in await crew.store.docs("insight", mid, limit=500)}
    commentary = await crew.store.docs("commentary", mid, limit=500)
    recap_text = next(
        (c["text"] for c in reversed(commentary) if c["kind"] == "full_time_recap"), ""
    )
    key = sorted(moments, key=lambda m: (-m["importance"], m["period"], m["clock_ms"]))[:5]
    key.sort(key=lambda m: (m["period"], m["clock_ms"]))
    key_moments = [
        {
            "moment_id": m["moment_id"],
            "minute": m["minute"],
            "kind": m["kind"],
            "headline": insights.get(m["moment_id"], {}).get("headline", m["summary"]),
            "why_it_matters": insights.get(m["moment_id"], {}).get("why_it_matters", ""),
            "evidence_event_ids": m["evidence_event_ids"],
        }
        for m in key
    ]
    h, a = report["teams"]
    cards = [
        {"label": "Possession", "home": h["possession_pct"], "away": a["possession_pct"],
         "unit": "%"},
        {"label": "Shots", "home": h["shots"], "away": a["shots"]},
        {"label": "xG", "home": h["xg"], "away": a["xg"]},
        {"label": "Pass accuracy", "home": h["pass_accuracy_pct"], "away": a["pass_accuracy_pct"],
         "unit": "%"},
        {"label": "Distance (km)", "home": h["distance_km"], "away": a["distance_km"]},
        {"label": "PPDA", "home": h["ppda"], "away": a["ppda"]},
    ]  # fmt: skip
    names = {"home": home["short_name"], "away": away["short_name"], "score": score}
    english_story = recap_text or t("period_body", "en", home_poss=h["possession_pct"],
                                    away_poss=a["possession_pct"], home_shots=h["shots"],
                                    away_shots=a["shots"])  # fmt: skip
    facts = await run.facts()
    facts.absorb(report)
    headlines: dict[str, str] = {}
    stories: dict[str, str] = {}
    results = await asyncio.gather(
        *(
            _localize(run, t("full_time", lang, **names), english_story, lang, facts)
            for lang in LANGS
        )
    )
    for lang, (title, body) in zip(LANGS, results, strict=True):
        headlines[lang] = t("full_time", lang, **names)  # code template: always correct
        if lang != "en" and body == english_story:
            # The translation did not happen (offline models, or it failed its check): tell
            # the story with the stats-only phrases in the viewer's language instead.
            body = t("period_body", lang, home_poss=h["possession_pct"],
                     away_poss=a["possession_pct"], home_shots=h["shots"],
                     away_shots=a["shots"])  # fmt: skip
        stories[lang] = body
        del title
    doc = {
        "match_id": mid,
        "headline": headlines,
        "story": stories,
        "final_score": f"{home['short_name']} {score} {away['short_name']}",
        "key_moments": key_moments,
        "player_of_the_match": await _player_of_the_match(run, home["team_id"], away["team_id"]),
        "stat_cards": cards,
        "languages": list(LANGS),
        "generated_by": _generated_by(crew.settings),
    }
    await crew.store.put_doc("recap", mid, "recap", doc)
    return doc


def _generated_by(settings: Settings) -> str:
    if settings.llm == "mock":
        return "the Pitchside agent crew (offline mock models)"
    return f"the Pitchside agent crew ({settings.model_large} / {settings.model_small})"
