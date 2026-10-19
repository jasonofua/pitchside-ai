"""The code half of the Fact Checker: every figure in a card must exist in match state.

`Facts` collects the numbers the Match Stats MCP server returned, grouped by unit.
`check_text` finds each figure a card writes (42%, 33.1 km/h, 0.34 xG, 71', 2-1, 17
passes) and reports those that match nothing of the same kind, allowing for rounding
to the precision the card used. Agents may quote numbers but never derive new ones, so a
difference or a sum the tools did not return is rejected too.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from contracts.agents import Mismatch

# Figures cards may use without a tool result: thresholds and window lengths in our own
# templates ("above 32 km/h", "last 5 minutes"), half lengths and the 0-100 scale.
ALWAYS_ALLOWED = frozenset({5.0, 10.0, 15.0, 30.0, 32.0, 45.0, 80.0, 90.0, 100.0})

SCORE = re.compile(r"(?<![\d.])(\d{1,2})\s?[-–]\s?(\d{1,2})(?![\d.%])")  # noqa: RUF001
MINUTE = re.compile(r"(?<![\d.])(\d{1,3})(?:\+(\d{1,2}))?(?:'|’|′|(?:st|nd|rd|th)\b)")  # noqa: RUF001
NUMBER = re.compile(
    r"(?<![\w.])([+-]?\d+(?:[.,]\d+)?)\s?(%|km/h|kmh|km|m\b|metres|meters|xG|/100|pts)?",
    re.IGNORECASE,
)

UNIT_ALIASES = {
    "%": "pct",
    "km/h": "kmh",
    "kmh": "kmh",
    "km": "km",
    "m": "m",
    "metres": "m",
    "meters": "m",
    "xg": "xg",
    "/100": "difficulty",
    "pts": "index",
}


def _unit_of_key(key: str) -> str | None:
    k = key.lower()
    if k.endswith("_pct") or k in ("home_share",):
        return "pct"
    if k.endswith("_kmh") or k == "value_kmh":
        return "kmh"
    if k.endswith("_km"):
        return "km"
    if k.endswith("_m"):
        return "m"
    if k == "xg" or k.endswith("_xg"):
        return "xg"
    if "difficulty" in k:
        return "difficulty"
    if k in ("index", "swing"):
        return "index"
    return None


@dataclass
class Facts:
    """Numbers known to be true for this moment, by unit, plus minutes and scorelines."""

    by_unit: dict[str, set[float]] = field(default_factory=dict)
    minutes: set[int] = field(default_factory=set)
    scores: set[tuple[int, int]] = field(default_factory=set)

    def add(self, unit: str, value: float) -> None:
        self.by_unit.setdefault(unit, set()).add(float(value))
        self.by_unit.setdefault("any", set()).add(float(value))
        if unit == "pct" and 0 <= value <= 1:
            self.by_unit["pct"].add(round(value * 100, 1))  # home_share as a percentage

    def add_minute_label(self, label: str) -> None:
        m = re.match(r"^(\d{1,3})(?:\+(\d{1,2}))?'$", label)
        if m:
            self.minutes.add(int(m.group(1)))
            if m.group(2):
                self.minutes.add(int(m.group(1)) + int(m.group(2)))

    def absorb(self, payload: Any, key: str = "") -> None:
        """Walk a tool result (any JSON) and remember every number by its field's unit."""
        if isinstance(payload, Mapping):
            value, unit = payload.get("value"), payload.get("unit")
            if isinstance(value, int | float) and not isinstance(value, bool) and unit:
                # A trigger or stat item: {"value": 0.76, "unit": "xG"} is an xG figure.
                self.add(UNIT_ALIASES.get(str(unit).lower(), "count"), float(value))
            for k, v in payload.items():
                self.absorb(v, str(k))
            home, away = payload.get("home"), payload.get("away")
            if isinstance(home, Mapping) and isinstance(away, Mapping):
                hs, as_ = home.get("score"), away.get("score")
                if isinstance(hs, int) and isinstance(as_, int):
                    self.scores.add((hs, as_))
        elif isinstance(payload, list):
            for item in payload:
                self.absorb(item, key)
        elif isinstance(payload, bool):
            return
        elif isinstance(payload, int | float):
            self.add(_unit_of_key(key) or "count", float(payload))
        elif isinstance(payload, str):
            if key in ("minute",):
                self.add_minute_label(payload)
            elif key == "score_after":
                m = SCORE.fullmatch(payload)
                if m:
                    self.scores.add((int(m.group(1)), int(m.group(2))))

    @classmethod
    def from_payloads(cls, payloads: Iterable[Any]) -> Facts:
        facts = cls()
        for p in payloads:
            facts.absorb(p)
        return facts


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def _matches(cited: float, decimals: int, candidates: Iterable[float]) -> bool:
    tol = 0.5 * 10**-decimals + 1e-9
    return any(abs(cited - c) <= tol for c in candidates)


def _closest(cited: float, candidates: Iterable[float]) -> float | None:
    pool = list(candidates)
    return min(pool, key=lambda c: abs(c - cited)) if pool else None


def check_text(text: str, facts: Facts) -> tuple[int, list[Mismatch]]:
    """(figures checked, mismatches) for one piece of card text."""
    mismatches: list[Mismatch] = []
    checked = 0
    consumed: list[tuple[int, int]] = []

    for m in SCORE.finditer(text):
        checked += 1
        consumed.append(m.span())
        pair = (int(m.group(1)), int(m.group(2)))
        if pair not in facts.scores and pair[::-1] not in facts.scores:
            known = ", ".join(f"{a}-{b}" for a, b in sorted(facts.scores)) or "none"
            mismatches.append(
                Mismatch(cited=m.group(0), expected=known, reason="scoreline not in match state")
            )

    for m in MINUTE.finditer(text):
        if any(a <= m.start() < b for a, b in consumed):
            continue
        checked += 1
        consumed.append(m.span())
        minute = int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0)
        if int(m.group(1)) not in facts.minutes and minute not in facts.minutes:
            mismatches.append(Mismatch(cited=m.group(0), reason="minute not in match state"))

    for m in NUMBER.finditer(text):
        if any(a <= m.start() < b for a, b in consumed):
            continue
        raw = m.group(1).replace(",", ".")
        cited = float(raw)
        unit = UNIT_ALIASES.get((m.group(2) or "").lower())
        checked += 1
        if cited in ALWAYS_ALLOWED or abs(cited) in ALWAYS_ALLOWED:
            continue
        pool = facts.by_unit.get(unit or "any", set())
        if unit == "index":
            pool = pool | {abs(v) for v in pool}
        if _matches(cited, _decimals(raw), pool) or (
            unit is None and _matches(abs(cited), _decimals(raw), facts.by_unit.get("any", set()))
        ):
            continue
        near = _closest(cited, pool)
        mismatches.append(Mismatch(
            cited=m.group(0).strip(),
            expected=None if near is None else f"{near:g}{m.group(2) or ''}",
            reason=f"no {unit or 'matching'} figure like this in match state",
        ))  # fmt: skip
    return checked, mismatches


def corrupt_first_figure(text: str, facts: Facts) -> str:
    """Change the first unit-bearing figure into a wrong one (the demo's fault injection)."""
    for m in NUMBER.finditer(text):
        unit = UNIT_ALIASES.get((m.group(2) or "").lower())
        if unit is None:
            continue
        raw = m.group(1).replace(",", ".")
        value = float(raw)
        pool = facts.by_unit.get(unit, set())
        bumped = value
        for step in (17, 23, 29, 31):
            bumped = round(value + step if unit != "xg" else value + step / 100, _decimals(raw))
            if not _matches(bumped, _decimals(raw), pool):
                break
        text_value = f"{bumped:.{_decimals(raw)}f}"
        return text[: m.start(1)] + text_value + text[m.end(1) :]
    return text
