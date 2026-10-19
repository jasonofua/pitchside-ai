"""Scenario scripts: story beats injected into the match engine at set minutes.

A scenario (sim/scenarios/<name>.yaml, validated against schemas/scenario.schema.json)
can change team modifiers, schedule goals and force a straight red card. The engine asks
the ScenarioDirector at each decision; the director itself uses no randomness, so a
scenario run is as reproducible as a default one.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

import yaml

from contracts import Scenario

SCENARIO_DIR = Path(__file__).with_name("scenarios")
HALF_MS = 45 * 60_000

# A goal beat starts tilting play towards the scoring team this long before its minute,
# and the team's first shot from FORCE_FROM_MS before the minute goes in.
GOAL_LEAD_MS = 100_000
FORCE_FROM_MS = 30_000

Side = Literal["home", "away", "favourite", "underdog"]


def scenario_names() -> list[str]:
    return ["default", *sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml"))]


@cache
def load_scenario(name: str) -> Scenario:
    path = SCENARIO_DIR / f"{name}.yaml"
    if not path.is_file():
        raise KeyError(f"unknown scenario {name!r}; choose from {', '.join(scenario_names())}")
    scenario = Scenario.model_validate(yaml.safe_load(path.read_text()))
    if scenario.name != name:
        raise ValueError(f"{path.name}: name {scenario.name!r} does not match the file name")
    return scenario


def beat_time(at: str) -> tuple[Literal[1, 2], int]:
    """'34' -> (1, 34:00); '71' -> (2, 71:00); '45+1' -> (1, 46:00); '90+2' -> (2, 92:00)."""
    if "+" in at:
        base, extra = (int(part) for part in at.split("+"))
        if base not in (45, 90):
            raise ValueError(f"stoppage beats must be 45+N or 90+N, got {at!r}")
        return (1 if base == 45 else 2), (base + extra) * 60_000
    minute = int(at)
    return (1 if minute < 45 else 2), minute * 60_000


@dataclass(slots=True)
class ScriptedBeat:
    kind: Literal["goal", "red_card", "modifiers"]
    team_id: str
    period: Literal[1, 2]
    clock_ms: int
    modifiers: dict[str, float]
    done: bool = False

    def reached(self, period: int, clock_ms: int, lead_ms: int = 0) -> bool:
        return (period, clock_ms) >= (self.period, self.clock_ms - lead_ms)


class ScenarioDirector:
    """Answers the engine's questions about the script for one match."""

    def __init__(self, scenario: Scenario, home: str, away: str) -> None:
        self.scenario = scenario
        venue = {"home": home, "away": away}
        favourite = scenario.favourite or "home"
        underdog = "away" if favourite == "home" else "home"
        roles = {**venue, "favourite": venue[favourite], "underdog": venue[underdog]}
        self.beats: list[ScriptedBeat] = []
        for beat in scenario.beats:
            period, clock = beat_time(beat.at)
            mods = beat.modifiers.model_dump(exclude_none=True) if beat.modifiers else {}
            self.beats.append(ScriptedBeat(beat.kind, roles[beat.team], period, clock, mods))
        self.beats.sort(key=lambda b: (b.period, b.clock_ms))

    @classmethod
    def for_name(cls, name: str, home: str, away: str) -> ScenarioDirector | None:
        if name == "default":
            return None
        return cls(load_scenario(name), home, away)

    @property
    def scripted(self) -> bool:
        return self.scenario.scoring == "scripted"

    def stoppage_range_s(self, period: int) -> tuple[int, int] | None:
        stoppage = self.scenario.stoppage_s
        rng = None if stoppage is None else (stoppage.p1 if period == 1 else stoppage.p2)
        return None if rng is None else (rng[0], rng[1])

    def due_modifiers(self, period: int, clock_ms: int) -> list[ScriptedBeat]:
        """Modifier beats that have just been reached; each is returned once."""
        out = []
        for beat in self.beats:
            if beat.kind == "modifiers" and not beat.done and beat.reached(period, clock_ms):
                beat.done = True
                out.append(beat)
        return out

    def _pending(self, kind: str, team_id: str) -> ScriptedBeat | None:
        return next(
            (b for b in self.beats if b.kind == kind and b.team_id == team_id and not b.done),
            None,
        )

    def goal_due(self, team_id: str, period: int, clock_ms: int) -> bool:
        """True while play should tilt towards `team_id` scoring a scripted goal."""
        beat = self._pending("goal", team_id)
        return beat is not None and beat.reached(period, clock_ms, GOAL_LEAD_MS)

    def shot_must_score(self, team_id: str, period: int, clock_ms: int) -> bool:
        beat = self._pending("goal", team_id)
        return beat is not None and beat.reached(period, clock_ms, FORCE_FROM_MS)

    def goal_allowed(self, team_id: str, period: int, clock_ms: int) -> bool:
        """Whether an unforced shot that beats the keeper may count."""
        return not self.scripted

    def goal_scored(self, team_id: str, period: int, clock_ms: int) -> None:
        """Mark the team's next goal beat done if the goal came in its window."""
        if self.goal_due(team_id, period, clock_ms):
            beat = self._pending("goal", team_id)
            assert beat is not None
            beat.done = True

    def red_card_due(self, team_id: str, period: int, clock_ms: int) -> bool:
        beat = self._pending("red_card", team_id)
        return beat is not None and beat.reached(period, clock_ms)

    def red_card_given(self, team_id: str) -> None:
        beat = self._pending("red_card", team_id)
        if beat is not None:
            beat.done = True
