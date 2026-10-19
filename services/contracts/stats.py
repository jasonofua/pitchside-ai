# Generated from schemas/stats.schema.json by scripts/gen_models.sh. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class TeamStats(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    team_id: Annotated[str, Field(pattern="^[A-Z]{3}$")]
    name: str
    short_name: str
    goals: Annotated[int, Field(ge=0)]
    shots: Annotated[int, Field(ge=0)]
    shots_on_target: Annotated[int, Field(ge=0)]
    xg: Annotated[float, Field(ge=0.0)]
    """
    Sum of shot xG, 2 dp.
    """
    max_shot_speed_kmh: float | None
    passes: Annotated[int, Field(ge=0)]
    passes_completed: Annotated[int, Field(ge=0)]
    pass_accuracy_pct: float | None
    avg_pass_distance_m: float | None
    avg_pass_speed_kmh: float | None
    avg_pass_difficulty: float | None
    """
    Mean pass difficulty, 0-100.
    """
    difficult_passes_completed: Annotated[int, Field(ge=0)]
    """
    Completed passes with difficulty above 80.
    """
    possession_pct: Annotated[float, Field(ge=0.0, le=100.0)]
    """
    Share of ball-in-play time, 1 dp.
    """
    pressures: Annotated[int, Field(ge=0)]
    tackles: Annotated[int, Field(ge=0)]
    tackles_won: Annotated[int, Field(ge=0)]
    interceptions: Annotated[int, Field(ge=0)]
    fouls: Annotated[int, Field(ge=0)]
    yellow_cards: Annotated[int, Field(ge=0)]
    red_cards: Annotated[int, Field(ge=0)]
    corners: Annotated[int, Field(ge=0)]
    turnovers: Annotated[int, Field(ge=0)]
    """
    Possessions lost other than by shooting.
    """
    ppda: float | None
    """
    Opponent passes allowed per defensive action in the opponent's first 60% of the pitch. Lower means a more intense press. Null when there were no defensive actions.
    """
    distance_km: Annotated[float, Field(ge=0.0)]
    sprints: Annotated[int, Field(ge=0)]
    top_speed_kmh: float | None


type Cell = Annotated[float, Field(ge=0.0)]


class Heatmap(BaseModel):
    """
    Share of tracked time in each zone, in the player's attacking frame (towards x=105). cells is row-major, rows from y=0, values sum to 1.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    cols: Annotated[int, Field(ge=1)]
    rows: Annotated[int, Field(ge=1)]
    cells: list[Cell]


class PlayerLine(BaseModel):
    """
    Compact live line per player for the match screen and player tags.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    player_id: str
    team_id: str
    on_pitch: bool
    touches: Annotated[int, Field(ge=0)]
    passes: Annotated[int, Field(ge=0)]
    passes_completed: Annotated[int, Field(ge=0)]
    shots: Annotated[int, Field(ge=0)]
    goals: Annotated[int, Field(ge=0)]
    xg: Annotated[float, Field(ge=0.0)]
    distance_km: Annotated[float, Field(ge=0.0)]
    top_speed_kmh: float | None
    speed_kmh: Annotated[float, Field(ge=0.0)]
    """
    Current speed, smoothed over 0.6 s.
    """


class TeamLine(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    team_id: str
    name: str
    short_name: str
    score: Annotated[int, Field(ge=0)]
    red_cards: Annotated[int, Field(ge=0)]
    color: str


class GoalItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    event_id: str
    team_id: str
    player_id: str
    player_name: str
    minute: Annotated[str, Field(pattern="^[0-9]{1,3}'$|^(45|90)\\+[0-9]{1,2}'$")]
    """
    Football minute, e.g. "68'" or "90+3'".
    """
    period: Literal[1, 2]
    clock_ms: int
    xg: float | None = None
    shot_speed_kmh: float | None = None
    score_after: str
    """
    Home-away, e.g. '2-1'.
    """


class CardItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    event_id: str
    team_id: str
    player_id: str
    player_name: str
    minute: Annotated[str, Field(pattern="^[0-9]{1,3}'$|^(45|90)\\+[0-9]{1,2}'$")]
    """
    Football minute, e.g. "68'" or "90+3'".
    """
    card_color: Literal["yellow", "second_yellow", "red"]


class MomentumNow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    index: Annotated[float, Field(ge=-100.0, le=100.0)]
    """
    Control vs Chaos index over the last 5 minutes: +100 = full control, -100 = full chaos.
    """
    swing: float
    """
    Change in the index over the last 5 minutes.
    """
    dominant_team_id: str | None
    """
    Team with more than 55% of ball-in-play possession in the window; null when the split is closer.
    """


class MomentumComponents(BaseModel):
    """
    Each component in [-1, 1]; positive pulls towards control.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    stability: Annotated[float, Field(ge=-1.0, le=1.0)]
    turnovers: Annotated[float, Field(ge=-1.0, le=1.0)]
    pressure: Annotated[float, Field(ge=-1.0, le=1.0)]
    tempo: Annotated[float, Field(ge=-1.0, le=1.0)]


class MomentumPoint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    period: Literal[1, 2]
    clock_ms: int
    minute: Annotated[str, Field(pattern="^[0-9]{1,3}'$|^(45|90)\\+[0-9]{1,2}'$")]
    """
    Football minute, e.g. "68'" or "90+3'".
    """
    index: Annotated[float, Field(ge=-100.0, le=100.0)]
    home_share: Annotated[float, Field(ge=0.0, le=1.0)]
    """
    Home share of ball-in-play possession in the 5-minute window, 0-1.
    """
    components: MomentumComponents


class Momentum(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    match_id: str
    window: Literal["match", "first_half", "second_half", "last_5", "last_10", "last_15"]
    """
    Time window for stats: the whole match, one half, or the last N minutes of playing time.
    """
    now: MomentumNow
    points: list[MomentumPoint]
    """
    The index every 30 s of match time inside the requested window.
    """


class TeamStatsReport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    match_id: str
    window: Literal["match", "first_half", "second_half", "last_5", "last_10", "last_15"]
    """
    Time window for stats: the whole match, one half, or the last N minutes of playing time.
    """
    minute: Annotated[str, Field(pattern="^[0-9]{1,3}'$|^(45|90)\\+[0-9]{1,2}'$")]
    """
    Football minute, e.g. "68'" or "90+3'".
    """
    teams: list[TeamStats]
    """
    Home first.
    """


class PeriodComparison(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    match_id: str
    first_half: list[TeamStats]
    second_half: list[TeamStats]


class ShotMapItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    event_id: str
    team_id: str
    player_id: str
    player_name: str
    minute: Annotated[str, Field(pattern="^[0-9]{1,3}'$|^(45|90)\\+[0-9]{1,2}'$")]
    """
    Football minute, e.g. "68'" or "90+3'".
    """
    x: float
    """
    Shooting team's frame (towards x=105).
    """
    y: float
    outcome: Literal["complete", "saved", "blocked", "off_target"]
    xg: Annotated[float, Field(ge=0.0, le=1.0)]
    body_part: str
    speed_kmh: float


class NetworkNode(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    player_id: str
    short_name: str
    shirt_number: int
    x: float
    """
    Mean position of the player's passes and receptions, team frame.
    """
    y: float
    passes: Annotated[int, Field(ge=0)]
    """
    Completed passes made.
    """


class NetworkEdge(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source: str
    target: str
    count: Annotated[int, Field(ge=1)]


class PassNetwork(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    team_id: str
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]
    """
    Completed passes between two players (either direction), at least 3.
    """


class DifficultyHistogram(BaseModel):
    """
    Pass counts per 10-point difficulty bin (0-10, 10-20, ... 90-100).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    team_id: str
    completed: Annotated[list[int], Field(max_length=10, min_length=10)]
    incomplete: Annotated[list[int], Field(max_length=10, min_length=10)]


class AnalystReport(BaseModel):
    """
    Everything the Analyst dashboard draws, computed by the Stats Engine.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    match_id: str
    minute: Annotated[str, Field(pattern="^[0-9]{1,3}'$|^(45|90)\\+[0-9]{1,2}'$")]
    """
    Football minute, e.g. "68'" or "90+3'".
    """
    shots: list[ShotMapItem]
    networks: list[PassNetwork]
    """
    Home first.
    """
    histograms: list[DifficultyHistogram]
    """
    Home first.
    """
    momentum: list[MomentumPoint]


class StatsSnapshot(BaseModel):
    """
    Published by the Stats Engine after events that change the numbers (throttled). Feeds the scoreboard, corner stat bug, momentum ribbon and player tags. The $defs are the payloads of the Match Stats MCP tools.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    match_id: Annotated[str, Field(min_length=1)]
    seq: Annotated[int, Field(ge=0)]
    status: Literal["scheduled", "live", "half_time", "full_time", "aborted"]
    period: Literal[1, 2]
    clock_ms: Annotated[int, Field(ge=0, le=7200000)]
    clock_display: Annotated[
        str, Field(pattern="^[0-9]{2,3}:[0-9]{2}$|^(45|90)\\+[0-9]{2}:[0-9]{2}$")
    ]
    """
    Broadcast clock, e.g. '67:12' or '45+02:18' in stoppage time.
    """
    minute: Annotated[str, Field(pattern="^[0-9]{1,3}'$|^(45|90)\\+[0-9]{1,2}'$")]
    """
    Football minute, e.g. "68'" or "90+3'".
    """
    teams: Annotated[list[TeamStats], Field(max_length=2, min_length=2)]
    """
    Home first.
    """
    momentum: MomentumNow
    players: list[PlayerLine]


class PlayerStats(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    player_id: Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{2}$")]
    name: str
    short_name: str
    team_id: Annotated[str, Field(pattern="^[A-Z]{3}$")]
    shirt_number: int
    position: str
    on_pitch: bool
    minutes_played: Annotated[int, Field(ge=0)]
    touches: Annotated[int, Field(ge=0)]
    passes: Annotated[int, Field(ge=0)]
    passes_completed: Annotated[int, Field(ge=0)]
    pass_accuracy_pct: float | None
    avg_pass_difficulty: float | None
    max_pass_difficulty: float | None
    key_passes: Annotated[int, Field(ge=0)]
    """
    Completed passes after which the receiver's next action was a shot.
    """
    shots: Annotated[int, Field(ge=0)]
    shots_on_target: Annotated[int, Field(ge=0)]
    goals: Annotated[int, Field(ge=0)]
    xg: Annotated[float, Field(ge=0.0)]
    max_shot_speed_kmh: float | None
    pressures: Annotated[int, Field(ge=0)]
    tackles_won: Annotated[int, Field(ge=0)]
    interceptions: Annotated[int, Field(ge=0)]
    fouls: Annotated[int, Field(ge=0)]
    yellow_cards: Annotated[int, Field(ge=0)]
    red_cards: Annotated[int, Field(ge=0)]
    distance_km: Annotated[float, Field(ge=0.0)]
    sprints: Annotated[int, Field(ge=0)]
    top_speed_kmh: float | None
    heatmap: Heatmap | None = None


class MatchState(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    match_id: str
    status: Literal["scheduled", "live", "half_time", "full_time", "aborted"]
    scenario: str
    period: Literal[1, 2]
    clock_ms: Annotated[int, Field(ge=0)]
    clock_display: Annotated[
        str, Field(pattern="^[0-9]{2,3}:[0-9]{2}$|^(45|90)\\+[0-9]{2}:[0-9]{2}$")
    ]
    """
    Broadcast clock, e.g. '67:12' or '45+02:18' in stoppage time.
    """
    minute: Annotated[str, Field(pattern="^[0-9]{1,3}'$|^(45|90)\\+[0-9]{1,2}'$")]
    """
    Football minute, e.g. "68'" or "90+3'".
    """
    seq: int
    """
    Last processed event seq, -1 before kickoff.
    """
    home: TeamLine
    away: TeamLine
    possession_team_id: str | None
    goals: list[GoalItem]
    cards: list[CardItem]
    momentum: MomentumNow
