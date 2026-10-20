// REST client for the gateway. In local mode the gateway also serves this site, so the
// API is same-origin; `pnpm dev` on :3000 talks to the gateway on :8000; Azure builds set
// NEXT_PUBLIC_API_URL to the gateway's URL.
import type {
  AgentTrace,
  MatchInfo,
  MatchState,
  Momentum,
  OverlayCard,
  PeriodComparison,
  PlayerStats,
  Profile,
  TeamStatsReport,
  Window,
  World,
} from "./contracts";
import type { AnalystReport, MatchEventLite, Moments, Recap, ScenarioInfo } from "./types";

export function apiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_URL;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location.port === "3000") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const m = (id: string) => `/api/matches/${encodeURIComponent(id)}`;

export const api = {
  health: () => call<{ ok: boolean; mode: string; llm: string }>("/api/health"),
  world: () => call<World>("/api/world"),
  crestUrl: (teamId: string) => `${apiBase()}/api/crests/${teamId}.svg`,
  scenarios: () => call<ScenarioInfo[]>("/api/scenarios"),
  matches: () => call<MatchInfo[]>("/api/matches"),
  start: (body: { scenario: string; seed?: number; speed: number; home?: string; away?: string }) =>
    call<{ match_id: string }>("/api/matches", { method: "POST", body: JSON.stringify(body) }),
  stop: (id: string) => call<unknown>(`${m(id)}/stop`, { method: "POST" }),
  match: (id: string) => call<MatchInfo>(m(id)),
  state: (id: string) => call<MatchState>(`${m(id)}/state`),
  teamStats: (id: string, window: Window = "match") =>
    call<TeamStatsReport>(`${m(id)}/stats?window=${window}`),
  player: (id: string, playerId: string, window: Window = "match") =>
    call<PlayerStats>(`${m(id)}/players/${playerId}?window=${window}`),
  momentum: (id: string, window: Window = "match") => call<Momentum>(`${m(id)}/momentum?window=${window}`),
  events: (id: string, since = -1, types?: string[], limit = 50) =>
    call<MatchEventLite[]>(
      `${m(id)}/events?since=${since}&limit=${limit}${types ? `&types=${types.join(",")}` : ""}`,
    ),
  compare: (id: string) => call<PeriodComparison>(`${m(id)}/compare`),
  analyst: (id: string) => call<AnalystReport>(`${m(id)}/analyst`),
  overlays: (id: string, profileHash?: string) =>
    call<OverlayCard[]>(`${m(id)}/overlays${profileHash ? `?profile_hash=${profileHash}` : ""}`),
  moments: (id: string) => call<Moments>(`${m(id)}/moments`),
  recap: (id: string) => call<Recap>(`${m(id)}/recap`),
  trace: (id: string) => call<AgentTrace[]>(`${m(id)}/trace`),
  chaos: (agent: string, seconds: number) =>
    call<unknown>("/api/admin/chaos", { method: "POST", body: JSON.stringify({ agent, seconds }) }),
  fault: (count = 1) =>
    call<unknown>("/api/admin/fault", { method: "POST", body: JSON.stringify({ kind: "wrong_number", count }) }),
  adminStatus: () => call<Record<string, unknown>>("/api/admin/status"),
  negotiate: (id: string, profile: Profile, admin = false) =>
    call<{ url: string; protocol: "plain" | "json.webpubsub.azure.v1"; profile_hash: string }>(
      `/api/negotiate?match_id=${encodeURIComponent(id)}&profile=${encodeURIComponent(JSON.stringify(profile))}${admin ? "&admin=true" : ""}`,
    ),
};
