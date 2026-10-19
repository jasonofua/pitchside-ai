"""Where simulator output goes: stdout (JSON lines or a readable log) or files."""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
from typing import IO, Any, Literal, Protocol

from contracts import MatchEvent, TrackingFrame, World
from sim.world import players_by_id

Topic = Literal["events", "tracking"]
TOPICS: tuple[Topic, ...] = ("events", "tracking")


class Sink(Protocol):
    def emit(self, topic: Topic, item: MatchEvent | TrackingFrame) -> None: ...

    def close(self) -> None: ...


class JsonlSink:
    """One envelope per line: {"topic": "events" | "tracking", "data": {...}}."""

    def __init__(self, stream: IO[str]) -> None:
        self.stream = stream

    def emit(self, topic: Topic, item: MatchEvent | TrackingFrame) -> None:
        data = item.model_dump_json(exclude_none=True)
        self.stream.write(f'{{"topic":"{topic}","data":{data}}}\n')
        self.stream.flush()

    def close(self) -> None:
        self.stream.flush()


class PrettySink:
    """A readable match log for terminals. Tracking frames are ignored."""

    def __init__(self, stream: IO[str], world: World, home: str, away: str) -> None:
        self.stream = stream
        self.players = players_by_id(world)
        self.home, self.away = home, away
        self.score = {home: 0, away: 0}

    def _clock(self, event: MatchEvent) -> str:
        base = 45 if event.period == 1 else 90
        minutes, seconds = divmod(event.clock_ms // 1000, 60)
        if minutes >= base:
            return f"{base}+{minutes - base:02d}:{seconds:02d}"
        return f"   {minutes:02d}:{seconds:02d}"

    def _who(self, player_id: str | None) -> str:
        if player_id is None:
            return ""
        p = self.players[player_id]
        return f"#{p.shirt_number} {p.short_name}"

    def _scoreline(self) -> str:
        return f"{self.home} {self.score[self.home]}-{self.score[self.away]} {self.away}"

    def emit(self, topic: Topic, item: MatchEvent | TrackingFrame) -> None:
        if not isinstance(item, MatchEvent):
            return
        e = item
        label = e.type.replace("_", " ")
        detail = ""
        if e.type == "pass":
            label = "pass" if e.outcome == "complete" else "pass x"
            detail = f"-> {self._who(e.recipient_id)}  {e.ball_speed_kmh:.0f} km/h"
        elif e.type == "shot":
            label = "SHOT"
            detail = f"{e.outcome}  {e.body_part}  {e.ball_speed_kmh:.0f} km/h"
        elif e.type == "goal" and e.team_id:
            self.score[e.team_id] += 1
            label = "GOAL"
            detail = f"*** {self._scoreline()} ***"
        elif e.type == "card":
            label = f"{(e.card_color or '').replace('_', ' ')} card".upper()
        elif e.type == "substitution":
            detail = f"on: {self._who(e.recipient_id)}"
        elif e.type in ("tackle", "interception"):
            detail = e.outcome or ""
        elif e.type == "period_end":
            label = "HALF TIME" if e.period == 1 else "FULL TIME"
            detail = self._scoreline()
        team = e.team_id or "   "
        line = f"{self._clock(e)}  {team}  {label:<17} {self._who(e.player_id):<24} {detail}"
        self.stream.write(line.rstrip() + "\n")
        self.stream.flush()

    def close(self) -> None:
        self.stream.flush()


class FileSink:
    """Writes <match_id>.events.jsonl, <match_id>.tracking.jsonl.gz and <match_id>.meta.json."""

    def __init__(self, out_dir: Path, match_id: str, meta: dict[str, Any]) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir = out_dir
        self.match_id = match_id
        self.meta = dict(meta)
        self.counts = {"events": 0, "tracking": 0}
        self.score = {team: 0 for team in (meta.get("home"), meta.get("away")) if team}
        self._events = (out_dir / f"{match_id}.events.jsonl").open("w")
        self._tracking: io.TextIOWrapper | None = None

    def emit(self, topic: Topic, item: MatchEvent | TrackingFrame) -> None:
        line = item.model_dump_json(exclude_none=True) + "\n"
        if topic == "events":
            self._events.write(line)
            if isinstance(item, MatchEvent) and item.type == "goal" and item.team_id:
                self.score[item.team_id] = self.score.get(item.team_id, 0) + 1
        else:
            if self._tracking is None:
                path = self.out_dir / f"{self.match_id}.tracking.jsonl.gz"
                # mtime=0 keeps the gzip bytes reproducible.
                raw = gzip.GzipFile(path, "wb", mtime=0)
                self._tracking = io.TextIOWrapper(raw, encoding="utf-8")
            self._tracking.write(line)
        self.counts[topic] += 1

    def close(self) -> None:
        self._events.close()
        if self._tracking is not None:
            self._tracking.close()
        meta = {**self.meta, "counts": self.counts, "score": self.score}
        meta_path = self.out_dir / f"{self.match_id}.meta.json"
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")


class WsSink:
    """Streams envelopes to a running gateway's /ws/ingest socket (the CLI's `--sink ws`).

    The first message is the MatchInfo, so the gateway's services know the teams.
    """

    def __init__(self, url: str, info: dict[str, Any]) -> None:
        from websockets.sync.client import connect

        self.ws = connect(url, max_size=None)
        self.ws.send(json.dumps({"topic": "match", "data": info}))

    def emit(self, topic: Topic, item: MatchEvent | TrackingFrame) -> None:
        data = item.model_dump_json(exclude_none=True)
        self.ws.send(f'{{"topic":"{topic}","data":{data}}}')

    def close(self) -> None:
        self.ws.close()


class EventHubsSink:
    """Publishes to Azure Event Hubs (the CLI's `--sink eventhubs`), authenticating with
    DefaultAzureCredential (managed identity, or `az login` on a laptop)."""

    def __init__(self, namespace: str, info: dict[str, Any]) -> None:
        from azure.eventhub import EventData, EventHubProducerClient
        from azure.identity import DefaultAzureCredential

        self._event = EventData
        fqns = namespace if "." in namespace else f"{namespace}.servicebus.windows.net"
        credential = DefaultAzureCredential()
        self.key = str(info["match_id"])
        self.producers = {
            name: EventHubProducerClient(
                fully_qualified_namespace=fqns, eventhub_name=name, credential=credential,
                buffered_mode=True, max_wait_time=0.05, on_error=self._on_error,
                on_success=self._on_success,
            )
            for name in ("matches", "events", "tracking")
        }  # fmt: skip
        live = {**info, "status": "live"}
        self.producers["matches"].send_event(EventData(json.dumps(live)), partition_key=self.key)

    @staticmethod
    def _on_error(events: Any, partition: str | None, error: Exception) -> None:
        raise RuntimeError(f"event hubs send failed: {error}")

    @staticmethod
    def _on_success(events: Any, partition: str | None) -> None:
        return None

    def emit(self, topic: Topic, item: MatchEvent | TrackingFrame) -> None:
        body = item.model_dump_json(exclude_none=True)
        self.producers[topic].send_event(self._event(body), partition_key=self.key)

    def close(self) -> None:
        for producer in self.producers.values():
            producer.close(flush=True)
