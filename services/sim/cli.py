"""Command line: python -m sim run --scenario default --seed 42 --speed 5 --sink stdout"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sim import __version__
from sim.engine import MatchConfig
from sim.runner import run_match
from sim.scenario import load_scenario, scenario_names
from sim.sinks import (
    TOPICS,
    EventHubsSink,
    FileSink,
    JsonlSink,
    PrettySink,
    Sink,
    Topic,
    WsSink,
)
from sim.world import REPO_ROOT, load_world

DEFAULT_HOME, DEFAULT_AWAY = "LAG", "HCF"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sim", description="Pitchside AI synthetic match engine."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="simulate a match and stream it to a sink")
    run.add_argument(
        "--scenario",
        default="default",
        help=f"scripted story beats: {', '.join(scenario_names())} (default: none)",
    )
    run.add_argument("--seed", type=int, default=42)
    run.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="match-clock multiplier, e.g. 1, 5, 20; 0 = unpaced",
    )
    run.add_argument("--sink", choices=["stdout", "file", "ws", "eventhubs"], default="stdout")
    run.add_argument(
        "--format", choices=["jsonl", "pretty"], default="jsonl", help="stdout sink only"
    )
    run.add_argument("--topics", default="events,tracking", help="comma-separated: events,tracking")
    run.add_argument(
        "--home", help="home team_id (see `python -m sim teams`); default: the scenario's, or LAG"
    )
    run.add_argument("--away", help="away team_id; default: the scenario's, or HCF")
    run.add_argument(
        "--match-id", help="override the derived match id (use a fresh one per live run)"
    )
    run.add_argument(
        "--out", type=Path, default=REPO_ROOT / "data" / "matches", help="file sink dir"
    )
    run.add_argument("--halftime-s", type=float, default=10.0, help="wall-clock half-time pause")
    run.add_argument(
        "--ws-url", default="ws://localhost:8000/ws/ingest", help="gateway ingest socket (ws sink)"
    )
    run.add_argument(
        "--eventhubs-namespace",
        default=os.environ.get("EVENTHUBS_NAMESPACE", ""),
        help="Event Hubs namespace (eventhubs sink)",
    )
    run.add_argument("--world", type=Path, help="world file (default: data/world.json)")

    teams = commands.add_parser("teams", help="list the fictional clubs")
    teams.add_argument("--world", type=Path)
    return parser


def _parse_topics(parser: argparse.ArgumentParser, raw: str) -> list[Topic]:
    topics: list[Topic] = []
    for name in (t.strip() for t in raw.split(",") if t.strip()):
        if name not in TOPICS:
            parser.error(f"unknown topic {name!r}; choose from {', '.join(TOPICS)}")
        topics.append("events" if name == "events" else "tracking")
    if not topics:
        parser.error("--topics needs at least one topic")
    return topics


def _cmd_teams(args: argparse.Namespace) -> int:
    world = load_world(args.world)
    for club in world.clubs:
        print(f"{club.team_id}  {club.name:<24} {club.formation:<8} {club.city}")
    return 0


def _cmd_run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.scenario not in scenario_names():
        parser.error(
            f"unknown scenario {args.scenario!r}; available: {', '.join(scenario_names())}"
        )
    if args.scenario != "default":
        scenario = load_scenario(args.scenario)
        args.home = args.home or scenario.home
        args.away = args.away or scenario.away
    args.home = args.home or DEFAULT_HOME
    args.away = args.away or DEFAULT_AWAY
    if args.speed < 0:
        parser.error("--speed must be >= 0")
    topics = _parse_topics(parser, args.topics)
    world = load_world(args.world)
    if args.sink in ("ws", "eventhubs") and not args.match_id:
        from sim.service import fresh_match_id

        # Live runs need a fresh id, or the Ingestor would drop them as duplicates.
        args.match_id = fresh_match_id(args.home, args.away, args.scenario, args.seed)
    config = MatchConfig(
        home=args.home, away=args.away, seed=args.seed, scenario=args.scenario,
        match_id=args.match_id,
    )  # fmt: skip
    try:
        match_id = config.resolved_match_id()
        known = {c.team_id for c in world.clubs}
        for team in (args.home, args.away):
            if team not in known:
                raise KeyError(f"unknown team {team!r}; known: {', '.join(sorted(known))}")
        if args.home == args.away:
            raise KeyError("--home and --away must differ")
    except KeyError as exc:
        parser.error(str(exc.args[0]))

    sink: Sink
    if args.sink in ("ws", "eventhubs"):
        from sim.live import new_match_info

        info = new_match_info(config, args.speed).model_dump(mode="json", exclude_none=True)
        if args.sink == "ws":
            try:
                sink = WsSink(args.ws_url, info)
            except OSError as exc:
                parser.error(f"cannot reach the gateway at {args.ws_url}: {exc}")
        else:
            if not args.eventhubs_namespace:
                parser.error("--sink eventhubs needs --eventhubs-namespace or EVENTHUBS_NAMESPACE")
            sink = EventHubsSink(args.eventhubs_namespace, info)
    elif args.sink == "file":
        meta = {
            "match_id": match_id,
            "seed": args.seed,
            "scenario": args.scenario,
            "home": args.home,
            "away": args.away,
            "generator": f"pitchside-sim {__version__}",
        }
        sink = FileSink(args.out, match_id, meta)
    elif args.format == "pretty":
        sink = PrettySink(sys.stdout, world, args.home, args.away)
        topics = ["events"]  # skip generating tracking nobody will see
    else:
        sink = JsonlSink(sys.stdout)

    run_match(world, config, sink, speed=args.speed, topics=topics, halftime_s=args.halftime_s)
    if args.sink == "file":
        print(f"wrote {match_id} to {args.out}", file=sys.stderr)
    elif args.sink in ("ws", "eventhubs"):
        print(f"streamed {config.resolved_match_id()} to {args.sink}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "teams":
            return _cmd_teams(args)
        return _cmd_run(parser, args)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # Downstream closed early (e.g. `| head`); silence the flush on exit.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0
