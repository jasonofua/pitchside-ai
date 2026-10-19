"""Local mode plumbing: in-process bus, SQLite store, Ingestor, Stats service, live runner."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from contracts import MatchInfo, StatsSnapshot, Trigger, World
from ingestor import Ingestor
from runtime.bus import LocalBus, Message
from runtime.store import SqliteStore
from sim.engine import MatchConfig, MatchEngine
from sim.live import run_live
from stats.service import StatsRegistry, StatsService

from .conftest import as_json, match_events, match_info


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


async def wait_until(cond: Callable[[], bool], timeout: float = 60.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not cond():
        if loop.time() > deadline:
            raise TimeoutError("condition not met")
        await asyncio.sleep(0.01)


# ------------------------------------------------------------------------- bus


def test_local_bus_fans_out_to_every_group() -> None:
    async def main() -> tuple[list[Message], list[Message]]:
        bus = LocalBus()
        a, b = bus.subscribe("events", "a"), bus.subscribe("events", "b")
        for i in range(3):
            await bus.publish("events", "m1", {"i": i})
        await bus.publish("tracking", "m1", {"other": True})
        await bus.close()
        return [m async for m in a], [m async for m in b]

    got_a, got_b = run(main())
    assert [m.data["i"] for m in got_a] == [0, 1, 2] == [m.data["i"] for m in got_b]
    assert all(m.key == "m1" and m.topic == "events" for m in got_a)


def test_local_bus_drops_oldest_when_a_subscriber_lags() -> None:
    async def main() -> tuple[list[int], int]:
        bus = LocalBus(maxsize=3)
        sub = bus.subscribe("tracking", "slow")
        for i in range(5):
            await bus.publish("tracking", "m", {"i": i})
        dropped = bus.dropped
        await bus.close()
        return [m.data["i"] async for m in sub], dropped

    got, dropped = run(main())
    assert dropped == 2
    assert got == [3, 4]  # the close signal also displaced frame 2


def test_local_bus_serialises_models() -> None:
    async def main() -> Message:
        bus = LocalBus()
        sub = bus.subscribe("events", "g")
        await bus.publish("events", "m", match_events()[0])
        return await anext(sub)

    msg = run(main())
    assert msg.data == as_json(match_events()[0])


# ----------------------------------------------------------------------- store


def test_sqlite_store_event_log_dedupes_and_orders() -> None:
    async def main() -> None:
        store = SqliteStore()
        events = match_events()[:20]
        for e in reversed(events):
            assert await store.append_event(e)
        assert not await store.append_event(events[3])
        got = await store.events(events[0].match_id)
        assert [e.seq for e in got] == list(range(20))
        assert [e.seq for e in await store.events(events[0].match_id, since_seq=15)] == [
            16, 17, 18, 19
        ]  # fmt: skip
        assert await store.events("nope") == []

    run(main())


def test_sqlite_store_matches_and_docs(tmp_path: Any) -> None:
    async def main() -> None:
        store = SqliteStore(tmp_path / "db" / "pitchside.sqlite")
        info = match_info("m1", "LAG", "HCF", 1)
        await store.put_match(info)
        await store.put_match(match_info("m2", "NBR", "KVA", 2))
        await store.put_match(info.model_copy(update={"status": "live"}))
        got = await store.get_match("m1")
        assert got is not None and got.status == "live"
        assert [m.match_id for m in await store.list_matches()] == ["m1", "m2"]
        assert await store.get_match("missing") is None
        for i in range(5):
            await store.put_doc("overlay", "m1", f"o{i}", {"i": i})
        await store.put_doc("overlay", "m1", "o1", {"i": 1, "replaced": True})
        docs = await store.docs("overlay", "m1")
        assert [d["i"] for d in docs] == [0, 2, 3, 4, 1]
        assert [d["i"] for d in await store.docs("overlay", "m1", limit=2)] == [4, 1]
        await store.close()

    run(main())


# -------------------------------------------------------------------- ingestor


def test_ingestor_validates_dedupes_and_republishes() -> None:
    async def main() -> tuple[Ingestor, list[Message]]:
        bus, store = LocalBus(), SqliteStore()
        ingestor = Ingestor(store, bus)
        accepted = bus.subscribe("accepted", "test")
        events = [as_json(e) for e in match_events()[:30]]
        for data in events:
            assert await ingestor.handle(data) is not None
        assert await ingestor.handle(events[5]) is None  # duplicate
        bad_pass = dict(next(d for d in events if d["type"] == "pass"))
        del bad_pass["recipient_id"]  # a pass needs a recipient (JSON Schema conditional)
        bad_pass["event_id"] = "01JZZZZZZZZZZZZZZZZZZZZZZZ"
        assert await ingestor.handle(bad_pass) is None
        assert await ingestor.handle({"type": "goal"}) is None
        await bus.close()
        return ingestor, [m async for m in accepted]

    ingestor, out = run(main())
    assert ingestor.stats.accepted == 30
    assert ingestor.stats.duplicates == 1
    assert ingestor.stats.rejected == 2
    assert "recipient_id" in ingestor.stats.last_errors[0]
    assert [m.data["seq"] for m in out] == list(range(30))


# ------------------------------------------------------------------ end to end


def test_full_match_flows_through_the_local_pipeline(world: World) -> None:
    config = MatchConfig(home="NBR", away="KVA", seed=11, match_id="local-e2e")

    async def main() -> tuple[StatsRegistry, list[Trigger], list[StatsSnapshot], SqliteStore]:
        bus, store = LocalBus(maxsize=200_000), SqliteStore()
        registry = StatsRegistry(world, store)
        triggers_sub = bus.subscribe("triggers", "test")
        stats_sub = bus.subscribe("stats", "test")
        tasks = [
            asyncio.create_task(Ingestor(store, bus).run()),
            asyncio.create_task(StatsService(registry, bus).run()),
        ]
        await asyncio.sleep(0)
        info = await run_live(world, config, bus, speed=0, halftime_s=0)
        assert info.status == "full_time"
        await wait_until(
            lambda: (e := registry.get("local-e2e")) is not None and e.status == "full_time"
        )
        await asyncio.sleep(0.05)
        for t in tasks:
            t.cancel()
        await bus.close()
        triggers = [Trigger.model_validate(m.data) async for m in triggers_sub]
        snaps = [StatsSnapshot.model_validate(m.data) async for m in stats_sub]
        return registry, triggers, snaps, store

    registry, triggers, snaps, store = run(main())
    expected = list(MatchEngine(world, config).events())
    engine = registry.get("local-e2e")
    assert engine is not None
    assert len(engine.records) == len(expected)
    goals = sum(e.type == "goal" for e in expected)
    assert sum(engine.score.values()) == goals
    assert sum(t.kind == "goal" for t in triggers) == goals
    assert any(t.kind == "speed" for t in triggers)  # tracking reached the stats engine
    assert snaps and snaps[-1].status == "full_time"
    assert engine.team_stats().teams[0].distance_km > 50

    # The event log alone rebuilds every event-derived number. Tracking-derived ones are
    # not persisted, and pass difficulty falls back to its events-only estimate.
    tracking_based = {
        "distance_km", "sprints", "top_speed_kmh", "avg_pass_difficulty",
        "difficult_passes_completed",
    }  # fmt: skip

    async def rebuild() -> None:
        fresh = StatsRegistry(world, store)
        await store.put_match(
            MatchInfo(
                match_id="local-e2e",
                home="NBR",
                away="KVA",
                scenario="default",
                seed=11,
                speed=0,
                status="full_time",
            )
        )
        again = await fresh.load("local-e2e")
        assert again is not None
        a, b = engine.team_stats().teams, again.team_stats().teams
        for x, y in zip(a, b, strict=True):
            assert x.model_dump(exclude=tracking_based) == y.model_dump(exclude=tracking_based)
        assert await fresh.load("missing") is None

    run(rebuild())


def test_live_runner_paces_by_match_clock(world: World) -> None:
    """At 600x, one minute of match clock takes about 0.1 s of wall time."""

    async def main() -> float:
        bus = LocalBus()
        sub = bus.subscribe("events", "t")
        task = asyncio.create_task(
            run_live(world, MatchConfig(home="LAG", away="HCF", seed=1), bus, speed=600)
        )
        loop = asyncio.get_running_loop()
        start = loop.time()
        async for msg in sub:
            if msg.data["clock_ms"] >= 60_000:
                break
        elapsed = loop.time() - start
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return elapsed

    assert 0.05 < run(main()) < 2.0


def test_cancelled_live_match_is_marked_aborted(world: World) -> None:
    async def main() -> list[str]:
        bus = LocalBus()
        sub = bus.subscribe("matches", "t")
        task = asyncio.create_task(
            run_live(world, MatchConfig(home="LAG", away="HCF", seed=1), bus, speed=1)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await bus.close()
        return [m.data["status"] async for m in sub]

    assert run(main()) == ["live", "aborted"]
