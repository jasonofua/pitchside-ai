"""Persistence: the event log, match records and agent output documents.

Local mode uses SQLite (SqliteStore). Azure mode uses Cosmos DB (runtime.cosmos), with
the same containers: events (partitioned by match_id, id = event_id so a duplicate
insert conflicts), matches, and docs (overlay cards, moments, insights, recaps, traces).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Literal, Protocol

from contracts import MatchEvent, MatchInfo

DocKind = Literal["overlay", "moment", "insight", "recap", "trace", "commentary"]


class Store(Protocol):
    async def append_event(self, event: MatchEvent) -> bool:
        """Append to the event log. False if an event with this event_id already exists."""

    async def events(
        self, match_id: str, since_seq: int = -1, limit: int | None = None
    ) -> list[MatchEvent]: ...

    async def put_match(self, info: MatchInfo) -> None: ...

    async def get_match(self, match_id: str) -> MatchInfo | None: ...

    async def list_matches(self, limit: int = 20) -> list[MatchInfo]: ...

    async def put_doc(self, kind: DocKind, match_id: str, doc_id: str, doc: dict[str, Any]) -> None:
        """Insert or replace a document."""

    async def docs(self, kind: DocKind, match_id: str, limit: int = 200) -> list[dict[str, Any]]:
        """Documents of a kind for a match, oldest first (the last `limit`)."""

    async def close(self) -> None: ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_match ON events (match_id, seq);
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    updated INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS docs (
    kind TEXT NOT NULL,
    match_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    body TEXT NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (kind, match_id, doc_id)
);
CREATE INDEX IF NOT EXISTS docs_by_match ON docs (kind, match_id, n);
"""


class SqliteStore:
    """SQLite store for local mode. Calls are short and run inline on the event loop."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        # Writes run on the event loop: without this every insert waits for an fsync, and a
        # burst of trace documents stalls the live match. WAL + NORMAL never corrupts the
        # database; a power cut can lose the last few writes, which local mode can afford.
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()
        self._n = 0

    def _exec(self, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._db.execute(sql, args)

    async def append_event(self, event: MatchEvent) -> bool:
        cur = self._exec(
            "INSERT OR IGNORE INTO events (event_id, match_id, seq, body) VALUES (?, ?, ?, ?)",
            (event.event_id, event.match_id, event.seq, event.model_dump_json(exclude_none=True)),
        )
        return cur.rowcount == 1

    async def events(
        self, match_id: str, since_seq: int = -1, limit: int | None = None
    ) -> list[MatchEvent]:
        sql = "SELECT body FROM events WHERE match_id = ? AND seq > ? ORDER BY seq"
        args: tuple[Any, ...] = (match_id, since_seq)
        if limit is not None:
            sql += " LIMIT ?"
            args += (limit,)
        rows = self._exec(sql, args).fetchall()
        return [MatchEvent.model_validate_json(r[0]) for r in rows]

    async def put_match(self, info: MatchInfo) -> None:
        with self._lock:
            self._n += 1
            n = self._n
        self._exec(
            "INSERT OR REPLACE INTO matches (match_id, body, updated) VALUES (?, ?, ?)",
            (info.match_id, info.model_dump_json(exclude_none=True), n),
        )

    async def get_match(self, match_id: str) -> MatchInfo | None:
        row = self._exec("SELECT body FROM matches WHERE match_id = ?", (match_id,)).fetchone()
        return None if row is None else MatchInfo.model_validate_json(row[0])

    async def list_matches(self, limit: int = 20) -> list[MatchInfo]:
        rows = self._exec(
            "SELECT body FROM matches ORDER BY updated DESC LIMIT ?", (limit,)
        ).fetchall()
        return [MatchInfo.model_validate_json(r[0]) for r in rows]

    async def put_doc(self, kind: DocKind, match_id: str, doc_id: str, doc: dict[str, Any]) -> None:
        with self._lock:
            self._n += 1
            n = self._n
        self._exec(
            "INSERT OR REPLACE INTO docs (kind, match_id, doc_id, body, n) VALUES (?, ?, ?, ?, ?)",
            (kind, match_id, doc_id, json.dumps(doc), n),
        )

    async def docs(self, kind: DocKind, match_id: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._exec(
            "SELECT body FROM docs WHERE kind = ? AND match_id = ? ORDER BY n DESC LIMIT ?",
            (kind, match_id, limit),
        ).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    async def close(self) -> None:
        with self._lock:
            self._db.close()
