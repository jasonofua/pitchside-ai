// Response shapes that wrap generated contracts (lib/contracts.ts).
import type {
  AnalystReport as GeneratedAnalystReport,
  AgentTrace,
  Commentary,
  Insight,
  MatchEvent,
  MatchInfo,
  Moment,
  OverlayCard,
  StatsSnapshot,
  TrackingFrame,
} from "./contracts";

export type AnalystReport = GeneratedAnalystReport;
export type MatchEventLite = MatchEvent;

export interface ScenarioInfo {
  name: string;
  description: string;
  home: string;
  away: string;
}

export interface Moments {
  moments: Moment[];
  insights: Insight[];
  commentary: Commentary[];
}

export interface RecapMoment {
  moment_id: string;
  minute: string;
  kind: string;
  headline: string;
  why_it_matters: string;
  evidence_event_ids: string[];
}

export interface Recap {
  match_id: string;
  headline: Record<string, string>;
  story: Record<string, string>;
  final_score: string;
  key_moments: RecapMoment[];
  player_of_the_match: {
    player_id: string;
    name: string;
    team_id: string;
    stats: { label: string; value: number | string; unit?: string }[];
  } | null;
  stat_cards: { label: string; home: number | string | null; away: number | string | null; unit?: string }[];
  languages: string[];
  generated_by: string;
}

export interface Hello {
  match_id: string;
  profile_hash: string;
  match: MatchInfo | null;
  stats: StatsSnapshot | null;
  frame: TrackingFrame | null;
  events: MatchEvent[];
  overlays: OverlayCard[];
  traces: AgentTrace[];
}

export type StreamMessage =
  | { type: "hello"; data: Hello }
  | { type: "tracking"; data: TrackingFrame }
  | { type: "event"; data: MatchEvent }
  | { type: "stats"; data: StatsSnapshot }
  | { type: "overlay"; data: OverlayCard }
  | { type: "trace"; data: AgentTrace }
  | { type: "match"; data: MatchInfo };
