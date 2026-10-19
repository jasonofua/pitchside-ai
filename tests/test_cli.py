from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

import pytest

from contracts import MatchEvent, TrackingFrame
from sim.cli import main
from sim.sinks import FileSink, JsonlSink

from .conftest import ROOT, match_with_tracking


def test_run_streams_jsonl_envelopes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--seed", "3", "--speed", "0", "--topics", "events"]) == 0
    lines = capsys.readouterr().out.splitlines()
    envelopes = [json.loads(line) for line in lines]
    assert {e["topic"] for e in envelopes} == {"events"}
    events = [MatchEvent.model_validate(e["data"]) for e in envelopes]
    assert events[0].type == "kickoff" and events[-1].type == "period_end"
    assert events[0].match_id == "lag-hcf-default-s3"


def test_pretty_format(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--seed", "3", "--speed", "0", "--format", "pretty"]) == 0
    out = capsys.readouterr().out
    assert "HALF TIME" in out and "FULL TIME" in out and "kickoff" in out


def test_file_sink_writes_events_and_meta(tmp_path: Path) -> None:
    args = ["run", "--seed", "4", "--speed", "0", "--sink", "file", "--topics", "events"]
    assert main([*args, "--home", "NBR", "--away", "KVA", "--out", str(tmp_path)]) == 0
    match_id = "nbr-kva-default-s4"
    lines = (tmp_path / f"{match_id}.events.jsonl").read_text().splitlines()
    meta = json.loads((tmp_path / f"{match_id}.meta.json").read_text())
    assert meta["counts"]["events"] == len(lines)
    goals = sum(json.loads(line)["type"] == "goal" for line in lines)
    assert sum(meta["score"].values()) == goals
    assert meta["seed"] == 4 and meta["home"] == "NBR"


def test_file_sink_compresses_tracking(tmp_path: Path) -> None:
    sink = FileSink(tmp_path, "m1", {"match_id": "m1"})
    items = match_with_tracking()[:50]
    for item in items:
        sink.emit("events" if isinstance(item, MatchEvent) else "tracking", item)
    sink.close()
    with gzip.open(tmp_path / "m1.tracking.jsonl.gz", "rt") as fh:
        frames = [TrackingFrame.model_validate_json(line) for line in fh]
    assert len(frames) == sum(isinstance(i, TrackingFrame) for i in items)


def test_jsonl_sink_envelope(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    with path.open("w") as fh:
        sink = JsonlSink(fh)
        for item in match_with_tracking()[:3]:
            sink.emit("events" if isinstance(item, MatchEvent) else "tracking", item)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["topic"] for r in rows] == ["events", "tracking", "tracking"]
    assert "end_x" not in rows[0]["data"]  # absent optional fields are omitted, not null


@pytest.mark.parametrize(
    "args",
    [
        ["run", "--sink", "ws"],
        ["run", "--sink", "eventhubs"],
        ["run", "--scenario", "nope"],
        ["run", "--home", "XYZ"],
        ["run", "--home", "LAG", "--away", "LAG"],
        ["run", "--topics", "odds"],
        ["run", "--speed", "-1"],
    ],
)
def test_bad_arguments_exit_with_usage_error(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "sim", "run", "--speed", "0", "--topics", "events", "--seed", "1"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    assert result.stdout.count("\n") > 1000
