"""Rule 3: no real clubs, leagues, players or governing bodies anywhere in the repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from runtime import realnames
from runtime.realnames import real_names_in

ROOT = Path(__file__).resolve().parents[1]
TEXT = {".py", ".ts", ".tsx", ".mjs", ".md", ".json", ".jsonl", ".yaml", ".yml", ".svg",
        ".bicep", ".css", ".toml", ".sh"}  # fmt: skip
SKIP = {"uv.lock", "web/pnpm-lock.yaml"}


def _tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [
        ROOT / f for f in out.stdout.splitlines()
        if Path(f).suffix in TEXT and f not in SKIP and (ROOT / f).is_file()
    ]  # fmt: skip


def test_the_guard_matches_phrases_case_insensitively(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = realnames._digest("kestrel rovers")  # a made-up name stands in for a real one
    monkeypatch.setattr(realnames, "DENY_HASHES", frozenset({fake}))
    assert real_names_in("A night for KESTREL Rovers fans") == ["kestrel rovers"]
    assert real_names_in("Kestrel Vale Athletic v Northbank Rovers") == []


def test_no_real_names_in_tracked_files() -> None:
    files = _tracked()
    assert len(files) > 50
    offenders = {str(f.relative_to(ROOT)): hits for f in files
                 if (hits := real_names_in(f.read_text(errors="ignore")))}  # fmt: skip
    assert not offenders, offenders
