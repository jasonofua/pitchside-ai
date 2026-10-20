"""Shared scoring helpers for the per-agent evals."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from agents.numbers import Facts, check_text

JARGON = re.compile(r"\b(xG|PPDA|half-spaces?|low block|rest defence|progressive|xT)\b", re.I)
PIDGIN = re.compile(
    r"\b(don|dey|na|wey|dem|am|oya|sef|abi|wahala|well well|comot|una|wetin|sabi|o)\b", re.I
)
YORUBA_MARKS = re.compile(r"[àáèéìíòóùúẹọṣ̀́]")
FRENCH = re.compile(r"\b(le|la|les|des|du|est|une|un|pour|à|au|sur)\b", re.I)
SPANISH = re.compile(r"\b(el|la|los|las|del|es|una|un|para|en|por|con)\b", re.I)
ENGLISH_ONLY = re.compile(r"\b(the|and|is|with|from|they|their|have)\b", re.I)
REAL_NAMES = re.compile(
    r"\b(Premier League|La Liga|Serie A|Bundesliga|Ligue 1|Champions League|Arsenal|Chelsea|"
    r"Liverpool|Barcelona|Real Madrid|Juventus|Bayern|PSG|Manchester|Messi|Ronaldo|Mbapp[eé]|"
    r"Haaland|Super Eagles|NPFL|Enyimba)\b",
    re.I,
)


@dataclass
class AgentScore:
    agent: str
    metrics: dict[str, float | int | str] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    passed: bool = True

    def check(self, ok: bool, message: str) -> None:
        if not ok:
            self.passed = False
            self.failures.append(message)


def figures_ok(text: str, facts: Facts) -> tuple[bool, list[str]]:
    _, bad = check_text(text, facts)
    return not bad, [m.cited for m in bad]


def rate(hits: int, total: int) -> float:
    return round(hits / total, 3) if total else 1.0


def latency(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"p50_ms": 0, "p95_ms": 0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    return {"p50_ms": int(statistics.median(ordered)), "p95_ms": p95}


def language_ok(lang: str, text: str) -> bool:
    """A loose check that a card reads as the target language."""
    if not text.strip():
        return True
    if lang == "yo":
        return bool(YORUBA_MARKS.search(text))
    if lang == "pcm":
        return bool(PIDGIN.search(text))
    if lang == "fr":
        return bool(FRENCH.search(text)) or not ENGLISH_ONLY.search(text)
    if lang == "es":
        return bool(SPANISH.search(text)) or not ENGLISH_ONLY.search(text)
    return True
