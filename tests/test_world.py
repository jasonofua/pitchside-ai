from __future__ import annotations

import importlib.util
import json
from collections import Counter
from types import ModuleType

from contracts import World
from runtime.realnames import real_names_in
from sim.formation import FORMATIONS

from .conftest import ROOT, validator

# Guard rail for the "fictional data only" rule: real leagues, governing bodies and a
# sample of well-known club names must never appear in the world file.


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_world", ROOT / "scripts" / "gen_world.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_world_file_matches_schema(world: World) -> None:
    validator("world").validate(json.loads((ROOT / "data" / "world.json").read_text()))
    assert 2 <= len(world.clubs) <= 4


def test_world_file_is_reproducible_from_generator() -> None:
    generated = _load_generator().build_world()
    assert generated == json.loads((ROOT / "data" / "world.json").read_text())


def test_squads_are_consistent(world: World) -> None:
    all_ids = [p.player_id for c in world.clubs for p in c.players]
    assert len(all_ids) == len(set(all_ids))
    for club in world.clubs:
        assert len(club.players) == 18
        numbers = Counter(p.shirt_number for p in club.players)
        assert max(numbers.values()) == 1, f"duplicate shirt number in {club.team_id}"
        assert all(p.player_id == f"{club.team_id}-{p.shirt_number:02d}" for p in club.players)
        by_id = {p.player_id: p for p in club.players}
        slots = FORMATIONS[club.formation]
        roles = [by_id[pid].position for pid in club.starting_xi]
        assert roles == [s.role for s in slots]
        bench_keepers = [
            p for p in club.players if p.position == "GK" and p.player_id not in club.starting_xi
        ]
        assert bench_keepers, f"{club.team_id} needs a substitute keeper"


def test_crests_exist(world: World) -> None:
    for club in world.clubs:
        svg = (ROOT / "data" / "crests" / f"{club.team_id}.svg").read_text()
        assert svg.startswith("<svg") and club.colors.primary in svg


def test_world_contains_no_real_league_or_club_names() -> None:
    text = (ROOT / "data" / "world.json").read_text().lower()
    hits = real_names_in(text)
    assert not hits, f"real-world names found: {hits}"
