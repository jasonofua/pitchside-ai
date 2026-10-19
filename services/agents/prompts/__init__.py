"""Versioned agent prompts: prompts/<agent>.v<N>.md with a small front-matter header.

The highest version is used unless PITCHSIDE_PROMPT_<AGENT>=<N> pins another, so a prompt
change is a new file and old versions stay reproducible.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent
AGENTS = (
    "moment_detector",
    "tactical_analyst",
    "narrator",
    "fan_lens",
    "localizer",
    "fact_checker",
    "producer",
)


@dataclass(frozen=True)
class Prompt:
    agent: str
    version: int
    model: str  # "large" or "small"
    output: str  # contracts.agents model name
    tools: tuple[str, ...]
    text: str

    @property
    def ref(self) -> str:
        return f"{self.agent}.v{self.version}"


def _parse(path: Path) -> Prompt:
    raw = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise ValueError(f"{path.name}: missing front matter")
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    tools = tuple(t.strip() for t in meta.get("tools", "[]").strip("[]").split(",") if t.strip())
    return Prompt(
        agent=meta["agent"],
        version=int(meta["version"]),
        model=meta["model"],
        output=meta["output"],
        tools=tools,
        text=m.group(2).strip(),
    )


def versions(agent: str) -> list[int]:
    return sorted(int(p.stem.split(".v")[1]) for p in PROMPT_DIR.glob(f"{agent}.v*.md"))


@cache
def load(agent: str, version: int | None = None) -> Prompt:
    if version is None:
        pinned = os.environ.get(f"PITCHSIDE_PROMPT_{agent.upper()}")
        available = versions(agent)
        if not available:
            raise KeyError(f"no prompt for {agent!r}")
        version = int(pinned) if pinned else available[-1]
    prompt = _parse(PROMPT_DIR / f"{agent}.v{version}.md")
    if prompt.agent != agent or prompt.version != version:
        raise ValueError(f"{agent}.v{version}.md: front matter does not match the file name")
    return prompt
