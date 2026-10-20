// Generated from /schemas by web/scripts/gen-types.mjs. Do not edit.
/* eslint-disable */

// ---- event.schema.json
/**
 * One on-ball or match-control event from the synthetic match engine. Coordinates are in metres on a 105 x 68 pitch, relative to the acting team (team_id) attacking left to right: x=0 is their own goal line, x=105 the opponent's, y=0 is the touchline on their left. See docs/DECISIONS.md.
 */
export type MatchEvent = {
  /**
   * ULID, unique and lexicographically sortable in emission order.
   */
  event_id: string;
  match_id: string;
  /**
   * Strictly increasing per match, starting at 0.
   */
  seq: number;
  /**
   * Displayed match clock in ms. Period 2 starts at 2700000 (45:00); stoppage time runs past 45:00 / 90:00.
   */
  clock_ms: number;
  period: 1 | 2;
  type: EventType;
  /**
   * Acting team. Absent only for period_end.
   */
  team_id?: string;
  /**
   * Acting player. For substitution, the player leaving the pitch. Absent only for period_end.
   */
  player_id?: string;
  x: PitchX;
  y: PitchY;
  end_x?: PitchX;
  end_y?: PitchY;
  outcome?: Outcome;
  /**
   * True when an opponent applied pressure on the actor immediately before this event.
   */
  under_pressure: boolean;
  /**
   * Initial ball speed for passes and shots.
   */
  ball_speed_kmh?: number;
  /**
   * Intended receiver of a pass, or the player coming on for a substitution.
   */
  recipient_id?: string;
  body_part?: BodyPart;
  card_color?: CardColor;
};
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "EventType".
 */
export type EventType =
  | "pass"
  | "carry"
  | "shot"
  | "tackle"
  | "interception"
  | "pressure"
  | "foul"
  | "card"
  | "substitution"
  | "goal"
  | "possession_change"
  | "out_of_play"
  | "kickoff"
  | "period_end";
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "PitchX".
 */
export type PitchX = number;
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "PitchY".
 */
export type PitchY = number;
/**
 * For shots, 'complete' means the shot was scored (a goal event follows).
 *
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "Outcome".
 */
export type Outcome = "complete" | "incomplete" | "saved" | "blocked" | "off_target" | "won" | "lost";
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "BodyPart".
 */
export type BodyPart = "right_foot" | "left_foot" | "head" | "other";
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "CardColor".
 */
export type CardColor = "yellow" | "second_yellow" | "red";

// ---- tracking.schema.json
/**
 * Positions of every on-pitch player and the ball, sampled at 5 Hz. Unlike events, coordinates are absolute: the home team attacks left to right (towards x=105) for the whole match.
 */
export interface TrackingFrame {
  match_id: string;
  /**
   * Displayed match clock in ms, on a 200 ms grid.
   */
  clock_ms: number;
  /**
   * Needed because stoppage time in period 1 overlaps the period 2 clock.
   */
  period: 1 | 2;
  /**
   * @maxItems 22
   */
  players: PlayerPosition[];
  ball: BallPosition;
}
/**
 * This interface was referenced by `TrackingFrame`'s JSON-Schema
 * via the `definition` "PlayerPosition".
 */
export interface PlayerPosition {
  player_id: string;
  x: number;
  y: number;
}
/**
 * This interface was referenced by `TrackingFrame`'s JSON-Schema
 * via the `definition` "BallPosition".
 */
export interface BallPosition {
  x: number;
  y: number;
}

// ---- overlay.schema.json
/**
 * This interface was referenced by `OverlayCard`'s JSON-Schema
 * via the `definition` "Slot".
 */
export type Slot = "lower_third" | "corner_bug" | "player_tag" | "full_card" | "ticker";
/**
 * en = English, pcm = Nigerian Pidgin, yo = Yoruba, fr = French, es = Spanish.
 *
 * This interface was referenced by `OverlayCard`'s JSON-Schema
 * via the `definition` "Lang".
 */
export type Lang = "en" | "pcm" | "yo" | "fr" | "es";

/**
 * A timed, renderer-agnostic overlay card emitted by the Producer agent. Any broadcast renderer can consume it.
 */
export interface OverlayCard {
  overlay_id: string;
  match_id: string;
  /**
   * Match clock at which the card should appear.
   */
  clock_ms: number;
  slot: Slot;
  /**
   * 1 = lowest, 5 = must show now.
   */
  priority: number;
  /**
   * How long the card stays valid after clock_ms.
   */
  ttl_ms: number;
  /**
   * Hash of the personalization profile this card was written for.
   */
  audience_profile_hash: string;
  lang: Lang;
  title: string;
  body: string;
  stats: StatItem[];
  evidence_event_ids: string[];
  trace_id: string;
  /**
   * What kind of moment the card is about (goal, big_chance, speed_burst, ...), for renderers that style by kind.
   */
  kind?: string;
  /**
   * The player a player_tag (or Player Cam card) is attached to.
   */
  player_id?: string;
  /**
   * The club the card is about, for club colours.
   */
  team_id?: string;
  /**
   * agent: written by the agent crew. template: the stats-only fallback.
   */
  source?: "agent" | "template";
}
/**
 * This interface was referenced by `OverlayCard`'s JSON-Schema
 * via the `definition` "StatItem".
 */
export interface StatItem {
  label: string;
  value: number | string;
  unit?: string;
}

// ---- world.schema.json
/**
 * This interface was referenced by `World`'s JSON-Schema
 * via the `definition` "HexColor".
 */
export type HexColor = string;
/**
 * This interface was referenced by `World`'s JSON-Schema
 * via the `definition` "Formation".
 */
export type Formation = "4-3-3" | "4-4-2" | "4-2-3-1" | "3-5-2";
/**
 * This interface was referenced by `World`'s JSON-Schema
 * via the `definition` "Position".
 */
export type Position =
  "GK" | "RB" | "CB" | "LB" | "RWB" | "LWB" | "DM" | "CM" | "AM" | "RM" | "LM" | "RW" | "LW" | "ST";
/**
 * This interface was referenced by `World`'s JSON-Schema
 * via the `definition` "Rating".
 */
export type Rating = number;

/**
 * The fictional football world: invented clubs, squads and crests. Nothing here may reference a real club, league, player or broadcaster.
 */
export interface World {
  version: number;
  /**
   * @minItems 2
   * @maxItems 4
   */
  clubs: [Club, Club] | [Club, Club, Club] | [Club, Club, Club, Club];
}
/**
 * This interface was referenced by `World`'s JSON-Schema
 * via the `definition` "Club".
 */
export interface Club {
  team_id: string;
  name: string;
  short_name: string;
  city: string;
  colors: Colors;
  crest: Crest;
  formation: Formation;
  /**
   * Player ids in formation slot order (see services/sim/formation.py).
   *
   * @minItems 11
   * @maxItems 11
   */
  starting_xi: [string, string, string, string, string, string, string, string, string, string, string];
  /**
   * @minItems 18
   * @maxItems 18
   */
  players: [
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player,
    Player
  ];
}
/**
 * This interface was referenced by `World`'s JSON-Schema
 * via the `definition` "Colors".
 */
export interface Colors {
  primary: HexColor;
  secondary: HexColor;
}
/**
 * Parameters for the generated SVG crest in data/crests/.
 *
 * This interface was referenced by `World`'s JSON-Schema
 * via the `definition` "Crest".
 */
export interface Crest {
  shape: "shield" | "circle" | "hexagon" | "diamond";
  motif: "stripe" | "chevron" | "star" | "wave" | "ring";
}
/**
 * This interface was referenced by `World`'s JSON-Schema
 * via the `definition` "Player".
 */
export interface Player {
  player_id: string;
  name: string;
  short_name: string;
  shirt_number: number;
  position: Position;
  attributes: Attributes;
}
/**
 * This interface was referenced by `World`'s JSON-Schema
 * via the `definition` "Attributes".
 */
export interface Attributes {
  pace: Rating;
  passing: Rating;
  finishing: Rating;
  pressing: Rating;
  stamina: Rating;
}

// ---- match.schema.json
/**
 * This interface was referenced by `MatchInfo`'s JSON-Schema
 * via the `definition` "MatchStatus".
 */
export type MatchStatus = "scheduled" | "live" | "half_time" | "full_time" | "aborted";

/**
 * Metadata for one simulated match, published before kickoff so downstream services know which team is home (tracking frames are in the home team's frame).
 */
export interface MatchInfo {
  match_id: string;
  home: string;
  away: string;
  scenario: string;
  seed: number;
  /**
   * Match-clock speed multiplier; 0 means unpaced.
   */
  speed: number;
  status: MatchStatus;
  /**
   * ISO 8601 wall-clock time the match was started.
   */
  created_at?: string;
}

// ---- trigger.schema.json
/**
 * speed: a player above 32 km/h. pass_difficulty: a completed pass above 80. xg: a shot above 0.3 xG. momentum_swing: the Control vs Chaos index moved 30+ points in 5 minutes. tick: 30 s of match time passed.
 *
 * This interface was referenced by `Trigger`'s JSON-Schema
 * via the `definition` "TriggerKind".
 */
export type TriggerKind =
  "speed" | "pass_difficulty" | "xg" | "goal" | "card" | "half_time" | "full_time" | "momentum_swing" | "tick";

/**
 * Raised by the Stats Engine when a threshold is crossed, a key event happens, or 30 s of match time pass. The Moment Detector runs on every trigger.
 */
export interface Trigger {
  /**
   * Deterministic: '<match_id>:<kind>:<seq or frame clock>'.
   */
  trigger_id: string;
  match_id: string;
  kind: TriggerKind;
  /**
   * seq of the last event the Stats Engine had processed when the trigger fired.
   */
  seq: number;
  clock_ms: number;
  period: 1 | 2;
  team_id?: string;
  player_id?: string;
  /**
   * The measured value, e.g. 33.4 for a 33.4 km/h sprint.
   */
  value?: number;
  threshold?: number;
  unit?: string;
  /**
   * Evidence: the events behind the trigger (most recent last).
   */
  event_ids: string[];
}

// ---- stats.schema.json
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "MatchStatus".
 */
export type ClockDisplay = string;
/**
 * Football minute, e.g. "68'" or "90+3'".
 *
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "Minute".
 */
export type Minute = string;
/**
 * Time window for stats: the whole match, one half, or the last N minutes of playing time.
 *
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "Window".
 */
export type Window = "match" | "first_half" | "second_half" | "last_5" | "last_10" | "last_15";

/**
 * Published by the Stats Engine after events that change the numbers (throttled). Feeds the scoreboard, corner stat bug, momentum ribbon and player tags. The $defs are the payloads of the Match Stats MCP tools.
 */
export interface StatsSnapshot {
  match_id: string;
  seq: number;
  status: MatchStatus;
  period: 1 | 2;
  clock_ms: number;
  clock_display: ClockDisplay;
  minute: Minute;
  /**
   * Home first.
   *
   * @minItems 2
   * @maxItems 2
   */
  teams: [TeamStats, TeamStats];
  momentum: MomentumNow;
  players: PlayerLine[];
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "TeamStats".
 */
export interface TeamStats {
  team_id: string;
  name: string;
  short_name: string;
  goals: number;
  shots: number;
  shots_on_target: number;
  /**
   * Sum of shot xG, 2 dp.
   */
  xg: number;
  max_shot_speed_kmh: number | null;
  passes: number;
  passes_completed: number;
  pass_accuracy_pct: number | null;
  avg_pass_distance_m: number | null;
  avg_pass_speed_kmh: number | null;
  /**
   * Mean pass difficulty, 0-100.
   */
  avg_pass_difficulty: number | null;
  /**
   * Completed passes with difficulty above 80.
   */
  difficult_passes_completed: number;
  /**
   * Share of ball-in-play time, 1 dp.
   */
  possession_pct: number;
  pressures: number;
  tackles: number;
  tackles_won: number;
  interceptions: number;
  fouls: number;
  yellow_cards: number;
  red_cards: number;
  corners: number;
  /**
   * Possessions lost other than by shooting.
   */
  turnovers: number;
  /**
   * Opponent passes allowed per defensive action in the opponent's first 60% of the pitch. Lower means a more intense press. Null when there were no defensive actions.
   */
  ppda: number | null;
  distance_km: number;
  sprints: number;
  top_speed_kmh: number | null;
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "MomentumNow".
 */
export interface MomentumNow {
  /**
   * Control vs Chaos index over the last 5 minutes: +100 = full control, -100 = full chaos.
   */
  index: number;
  /**
   * Change in the index over the last 5 minutes.
   */
  swing: number;
  /**
   * Team with more than 55% of ball-in-play possession in the window; null when the split is closer.
   */
  dominant_team_id: string | null;
}
/**
 * Compact live line per player for the match screen and player tags.
 *
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "PlayerLine".
 */
export interface PlayerLine {
  player_id: string;
  team_id: string;
  on_pitch: boolean;
  touches: number;
  passes: number;
  passes_completed: number;
  shots: number;
  goals: number;
  xg: number;
  distance_km: number;
  top_speed_kmh: number | null;
  /**
   * Current speed, smoothed over 0.6 s.
   */
  speed_kmh: number;
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "PlayerStats".
 */
export interface PlayerStats {
  player_id: string;
  name: string;
  short_name: string;
  team_id: string;
  shirt_number: number;
  position: string;
  on_pitch: boolean;
  minutes_played: number;
  touches: number;
  passes: number;
  passes_completed: number;
  pass_accuracy_pct: number | null;
  avg_pass_difficulty: number | null;
  max_pass_difficulty: number | null;
  /**
   * Completed passes after which the receiver's next action was a shot.
   */
  key_passes: number;
  shots: number;
  shots_on_target: number;
  goals: number;
  xg: number;
  max_shot_speed_kmh: number | null;
  pressures: number;
  tackles_won: number;
  interceptions: number;
  fouls: number;
  yellow_cards: number;
  red_cards: number;
  distance_km: number;
  sprints: number;
  top_speed_kmh: number | null;
  heatmap?: Heatmap;
}
/**
 * Share of tracked time in each zone, in the player's attacking frame (towards x=105). cells is row-major, rows from y=0, values sum to 1.
 *
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "Heatmap".
 */
export interface Heatmap {
  cols: number;
  rows: number;
  cells: number[];
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "TeamLine".
 */
export interface TeamLine {
  team_id: string;
  name: string;
  short_name: string;
  score: number;
  red_cards: number;
  color: string;
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "GoalItem".
 */
export interface GoalItem {
  event_id: string;
  team_id: string;
  player_id: string;
  player_name: string;
  minute: Minute;
  period: 1 | 2;
  clock_ms: number;
  xg?: number | null;
  shot_speed_kmh?: number | null;
  /**
   * Home-away, e.g. '2-1'.
   */
  score_after: string;
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "CardItem".
 */
export interface CardItem {
  event_id: string;
  team_id: string;
  player_id: string;
  player_name: string;
  minute: Minute;
  card_color: "yellow" | "second_yellow" | "red";
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "MatchState".
 */
export interface MatchState {
  match_id: string;
  status: MatchStatus;
  scenario: string;
  period: 1 | 2;
  clock_ms: number;
  clock_display: ClockDisplay;
  minute: Minute;
  /**
   * Last processed event seq, -1 before kickoff.
   */
  seq: number;
  home: TeamLine;
  away: TeamLine;
  possession_team_id: string | null;
  goals: GoalItem[];
  cards: CardItem[];
  momentum: MomentumNow;
}
/**
 * Each component in [-1, 1]; positive pulls towards control.
 *
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "MomentumComponents".
 */
export interface MomentumComponents {
  stability: number;
  turnovers: number;
  pressure: number;
  tempo: number;
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "MomentumPoint".
 */
export interface MomentumPoint {
  period: 1 | 2;
  clock_ms: number;
  minute: Minute;
  index: number;
  /**
   * Home share of ball-in-play possession in the 5-minute window, 0-1.
   */
  home_share: number;
  components: MomentumComponents;
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "Momentum".
 */
export interface Momentum {
  match_id: string;
  window: Window;
  now: MomentumNow;
  /**
   * The index every 30 s of match time inside the requested window.
   */
  points: MomentumPoint[];
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "TeamStatsReport".
 */
export interface TeamStatsReport {
  match_id: string;
  window: Window;
  minute: Minute;
  /**
   * Home first.
   */
  teams: TeamStats[];
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "PeriodComparison".
 */
export interface PeriodComparison {
  match_id: string;
  first_half: TeamStats[];
  second_half: TeamStats[];
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "ShotMapItem".
 */
export interface ShotMapItem {
  event_id: string;
  team_id: string;
  player_id: string;
  player_name: string;
  minute: Minute;
  /**
   * Shooting team's frame (towards x=105).
   */
  x: number;
  y: number;
  outcome: "complete" | "saved" | "blocked" | "off_target";
  xg: number;
  body_part: string;
  speed_kmh: number;
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "NetworkNode".
 */
export interface NetworkNode {
  player_id: string;
  short_name: string;
  shirt_number: number;
  /**
   * Mean position of the player's passes and receptions, team frame.
   */
  x: number;
  y: number;
  /**
   * Completed passes made.
   */
  passes: number;
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "NetworkEdge".
 */
export interface NetworkEdge {
  source: string;
  target: string;
  count: number;
}
/**
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "PassNetwork".
 */
export interface PassNetwork {
  team_id: string;
  nodes: NetworkNode[];
  /**
   * Completed passes between two players (either direction), at least 3.
   */
  edges: NetworkEdge[];
}
/**
 * Pass counts per 10-point difficulty bin (0-10, 10-20, ... 90-100).
 *
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "DifficultyHistogram".
 */
export interface DifficultyHistogram {
  team_id: string;
  /**
   * @minItems 10
   * @maxItems 10
   */
  completed: [number, number, number, number, number, number, number, number, number, number];
  /**
   * @minItems 10
   * @maxItems 10
   */
  incomplete: [number, number, number, number, number, number, number, number, number, number];
}
/**
 * Everything the Analyst dashboard draws, computed by the Stats Engine.
 *
 * This interface was referenced by `StatsSnapshot`'s JSON-Schema
 * via the `definition` "AnalystReport".
 */
export interface AnalystReport {
  match_id: string;
  minute: Minute;
  shots: ShotMapItem[];
  /**
   * Home first.
   */
  networks: PassNetwork[];
  /**
   * Home first.
   */
  histograms: DifficultyHistogram[];
  momentum: MomentumPoint[];
}

// ---- profile.schema.json
/**
 * A viewer's personalization profile, set in the onboarding sheet, kept in the browser and sent with the WebSocket subscription. Cards are written per profile hash.
 */
export interface Profile {
  /**
   * analyst: dense, tactical. casual: short, emotional, no jargon. player_cam: everything about one player. kids: simple and upbeat.
   */
  mode: "analyst" | "casual" | "player_cam" | "kids";
  /**
   * en = English, pcm = Nigerian Pidgin, yo = Yoruba, fr = French, es = Spanish.
   */
  language: "en" | "pcm" | "yo" | "fr" | "es";
  favorite_club?: string;
  favorite_player?: string;
  /**
   * The one stat shown in a persistent bug.
   */
  focus_metric?: "shot_speed" | "top_speed" | "distance" | "possession" | "xg" | "pass_accuracy" | "momentum";
}

// ---- agents.schema.json
/**
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "AgentName".
 */
export type AgentName =
  "moment_detector" | "tactical_analyst" | "narrator" | "fan_lens" | "localizer" | "fact_checker" | "producer";
/**
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "Lang".
 */
export type Mode = "analyst" | "casual" | "player_cam" | "kids";
/**
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "Ulid".
 */
export type Ulid = string;
/**
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "MomentKind".
 */
export type MomentKind =
  "goal" | "big_chance" | "card" | "speed_burst" | "hard_pass" | "momentum_swing" | "spell" | "half_time" | "full_time";

/**
 * One step of the agent workflow, as shown in the Director panel's live trace. The $defs are the typed messages agents hand to each other; every handoff carries trace_id and moment_id.
 */
export interface AgentTrace {
  trace_id: string;
  match_id: string;
  moment_id?: string;
  agent: AgentName;
  /**
   * Deployment used: the large or small model name, 'code' for deterministic steps, or 'mock' offline.
   */
  model: string;
  status: "ok" | "skipped" | "timeout" | "error" | "fallback" | "rejected" | "regenerated" | "circuit_open" | "dropped";
  latency_ms: number;
  /**
   * Match clock when the step finished.
   */
  clock_ms: number;
  /**
   * Wall-clock ISO 8601 time the step finished.
   */
  at: string;
  detail?: string;
  /**
   * MCP tools the agent called.
   */
  tools?: string[];
  profile_hash?: string;
}
/**
 * Output of the Moment Detector.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "Moment".
 */
export interface Moment {
  moment_id: string;
  match_id: string;
  trace_id: string;
  trigger_id: string;
  kind: MomentKind;
  period: 1 | 2;
  clock_ms: number;
  minute: string;
  importance: number;
  team_id?: string;
  player_id?: string;
  /**
   * One factual line, no numbers beyond the trigger's own value.
   */
  summary: string;
  evidence_event_ids: Ulid[];
}
/**
 * A number an agent used, with where it came from.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "StatCitation".
 */
export interface StatCitation {
  label: string;
  value: number | string;
  /**
   * Unit such as %, km/h, km, xG; empty string when none.
   */
  unit: string;
  /**
   * MCP tool and field, e.g. 'get_team_stats.LAG.possession_pct'.
   */
  source: string;
}
/**
 * Output of the Tactical Analyst.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "Insight".
 */
export interface Insight {
  insight_id: string;
  moment_id: string;
  match_id: string;
  trace_id: string;
  headline: string;
  why_it_matters: string;
  stats_cited: StatCitation[];
  team_id?: string;
  player_id?: string;
}
/**
 * Output of the Narrator.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "Commentary".
 */
export interface Commentary {
  commentary_id: string;
  moment_id: string;
  match_id: string;
  trace_id: string;
  kind: "line" | "half_time_story" | "full_time_recap";
  text: string;
  stats_cited: StatCitation[];
}
/**
 * A profile-specific card from the Fan Lens, localised by the Localizer, checked by the Fact Checker.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "CardDraft".
 */
export interface CardDraft {
  draft_id: string;
  moment_id: string;
  match_id: string;
  trace_id: string;
  profile_hash: string;
  mode: Mode;
  lang: Lang;
  kind: MomentKind;
  title: string;
  body: string;
  stats: StatItem[];
  evidence_event_ids: Ulid[];
  importance: number;
  player_id?: string;
  team_id?: string;
  /**
   * agent: written by models. template: the stats-only fallback.
   */
  source: "agent" | "template";
  /**
   * draft_id of a template card this upgraded card replaces.
   */
  replaces?: string;
}
/**
 * Same shape as the overlay contract's StatItem, but unit is always present (empty when none).
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "StatItem".
 */
export interface Mismatch {
  /**
   * The figure as written in the card.
   */
  cited: string;
  /**
   * What match state says, if known.
   */
  expected?: string;
  reason: string;
}
/**
 * Output of the Fact Checker.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "FactCheck".
 */
export interface FactCheck {
  draft_id: string;
  verdict: "pass" | "reject";
  numbers_checked: number;
  mismatches: Mismatch[];
}
/**
 * What flows from the Narrator to the Fan Lens: the moment, plus the insight and commentary when they exist.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "Story".
 */
export interface Story {
  moment: Moment;
  insight?: Insight;
  commentary?: Commentary;
}
/**
 * Structured output of the Moment Detector model. Model output: no length or range keywords (strict structured outputs reject some), so code clamps values.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "MomentDecision".
 */
export interface MomentDecision {
  is_moment: boolean;
  kind: MomentKind;
  importance: number;
  summary: string;
}
/**
 * Structured output of the Tactical Analyst model. Model output: no length or range keywords (strict structured outputs reject some), so code clamps values.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "InsightDraft".
 */
export interface InsightDraft {
  headline: string;
  why_it_matters: string;
  stats_cited: StatCitation[];
}
/**
 * Structured output of the Narrator model. Model output: no length or range keywords (strict structured outputs reject some), so code clamps values.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "CommentaryDraft".
 */
export interface CommentaryDraft {
  text: string;
  stats_cited: StatCitation[];
}
/**
 * Structured output of the Fan Lens and Localizer models. Model output: no length or range keywords (strict structured outputs reject some), so code clamps values.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "CardText".
 */
export interface CardText {
  title: string;
  body: string;
  stats: StatItem[];
}
/**
 * Structured output of the Fact Checker model (qualitative claims; numbers are checked in code). Model output: no length or range keywords (strict structured outputs reject some), so code clamps values.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "ClaimCheck".
 */
export interface ClaimCheck {
  verdict: "pass" | "reject";
  reason: string;
}
/**
 * Structured output of the Producer model: where and how long a card shows. Model output: no length or range keywords (strict structured outputs reject some), so code clamps values.
 *
 * This interface was referenced by `AgentTrace`'s JSON-Schema
 * via the `definition` "ProducerPlan".
 */
export interface ProducerPlan {
  slot: "lower_third" | "corner_bug" | "player_tag" | "full_card" | "ticker";
  priority: number;
  ttl_s: number;
}
