"use client";

// Live match data over a WebSocket: the gateway's own socket in local mode, Azure Web
// PubSub in Azure mode (the gateway's /api/negotiate says which). Tracking frames go into
// a ref so the pitch can animate at 60 fps without re-rendering React; everything else is
// React state.
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type {
  AgentTrace,
  MatchEvent,
  MatchInfo,
  OverlayCard,
  Profile,
  StatsSnapshot,
  TrackingFrame,
} from "./contracts";
import type { Hello, StreamMessage } from "./types";

export interface LiveOverlay extends OverlayCard {
  receivedAt: number; // performance.now()
  expiresAt: number;
}

export interface FrameBuffer {
  prev: TrackingFrame | null;
  curr: TrackingFrame | null;
  receivedAt: number;
  intervalMs: number; // wall ms between the last two frames
}

export interface MatchStream {
  status: "connecting" | "live" | "closed" | "error";
  match: MatchInfo | null;
  stats: StatsSnapshot | null;
  events: MatchEvent[];
  overlays: LiveOverlay[];
  traces: AgentTrace[];
  profileHash: string | null;
  frames: React.MutableRefObject<FrameBuffer>;
  lastEvent: MatchEvent | null;
}

const MAX_EVENTS = 60;
const MAX_TRACES = 120;
const MAX_DISPLAY_MS = 30_000;
const HEARTBEAT_MS = 30_000; // the gateway forgets a Web PubSub viewer after 90 s of silence

function displayMs(card: OverlayCard, speed: number): number {
  // ttl_ms is match time (reading time x playback speed); show the reading time.
  return Math.min(MAX_DISPLAY_MS, Math.max(6_000, card.ttl_ms / Math.max(speed, 1)));
}

export function useMatchStream(
  matchId: string | null,
  profile: Profile | null,
  opts: { admin?: boolean } = {},
): MatchStream {
  const [status, setStatus] = useState<MatchStream["status"]>("connecting");
  const [match, setMatch] = useState<MatchInfo | null>(null);
  const [stats, setStats] = useState<StatsSnapshot | null>(null);
  const [events, setEvents] = useState<MatchEvent[]>([]);
  const [overlays, setOverlays] = useState<LiveOverlay[]>([]);
  const [traces, setTraces] = useState<AgentTrace[]>([]);
  const [profileHash, setProfileHash] = useState<string | null>(null);
  const [lastEvent, setLastEvent] = useState<MatchEvent | null>(null);
  const frames = useRef<FrameBuffer>({ prev: null, curr: null, receivedAt: 0, intervalMs: 200 });
  const speed = useRef(1);
  const profileKey = useMemo(() => (profile ? JSON.stringify(profile) : ""), [profile]);
  const admin = !!opts.admin;

  // Expire overlays.
  useEffect(() => {
    const t = setInterval(() => {
      const now = performance.now();
      setOverlays((list) => (list.some((o) => o.expiresAt <= now) ? list.filter((o) => o.expiresAt > now) : list));
    }, 500);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!matchId || !profileKey) return;
    const prof = JSON.parse(profileKey) as Profile;
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let heartbeat: ReturnType<typeof setInterval> | null = null;
    const stopHeartbeat = () => {
      if (heartbeat) clearInterval(heartbeat);
      heartbeat = null;
    };

    const addOverlay = (card: OverlayCard, receivedAt = performance.now()) => {
      setOverlays((list) => {
        const rest = list.filter((o) => o.overlay_id !== card.overlay_id);
        return [...rest, { ...card, receivedAt, expiresAt: receivedAt + displayMs(card, speed.current) }];
      });
    };

    const pushFrame = (frame: TrackingFrame) => {
      const buf = frames.current;
      const now = performance.now();
      const interval = buf.receivedAt ? Math.min(1000, Math.max(16, now - buf.receivedAt)) : 200;
      frames.current = { prev: buf.curr, curr: frame, receivedAt: now, intervalMs: interval };
    };

    const handle = (msg: StreamMessage) => {
      switch (msg.type) {
        case "hello": {
          const h: Hello = msg.data;
          setProfileHash(h.profile_hash);
          if (h.match) {
            setMatch(h.match);
            speed.current = h.match.speed || 1;
          }
          if (h.stats) setStats(h.stats);
          if (h.frame) pushFrame(h.frame);
          setEvents(h.events.slice(-MAX_EVENTS));
          setLastEvent(h.events[h.events.length - 1] ?? null);
          const now = performance.now();
          // Old cards get a short life so a late joiner sees the latest, not a backlog.
          for (const o of h.overlays.slice(-3)) addOverlay(o, now - Math.max(0, displayMs(o, speed.current) - 4000));
          if (h.traces.length) setTraces(h.traces.slice(-MAX_TRACES));
          break;
        }
        case "tracking":
          pushFrame(msg.data);
          break;
        case "event":
          setEvents((list) => [...list.slice(-(MAX_EVENTS - 1)), msg.data]);
          setLastEvent(msg.data);
          break;
        case "stats":
          setStats(msg.data);
          break;
        case "overlay":
          addOverlay(msg.data);
          break;
        case "trace":
          setTraces((list) => [...list.slice(-(MAX_TRACES - 1)), msg.data]);
          break;
        case "match":
          setMatch(msg.data);
          speed.current = msg.data.speed || 1;
          break;
      }
    };

    const connect = async () => {
      try {
        setStatus("connecting");
        const neg = await api.negotiate(matchId, prof, admin);
        if (closed) return;
        setProfileHash(neg.profile_hash);
        ws = neg.protocol === "plain" ? new WebSocket(neg.url) : new WebSocket(neg.url, neg.protocol);
        ws.onopen = async () => {
          retry = 0;
          setStatus("live");
          if (neg.protocol !== "plain") {
            // The gateway cannot see Web PubSub connections: tell it every 30 s that this
            // viewer is still here, or the agents stop writing cards for this profile.
            stopHeartbeat();
            heartbeat = setInterval(() => void api.heartbeat(matchId, prof).catch(() => undefined), HEARTBEAT_MS);
            // Web PubSub does not push a hello; fetch the same snapshot over REST.
            try {
              const res = await fetch(
                `${(await import("./api")).apiBase()}/api/matches/${encodeURIComponent(matchId)}/live?profile_hash=${neg.profile_hash}${admin ? "&admin=true" : ""}`,
              );
              if (res.ok) handle({ type: "hello", data: (await res.json()) as Hello });
            } catch {
              /* hello is best effort */
            }
          }
        };
        ws.onmessage = (ev: MessageEvent<string>) => {
          let parsed: unknown;
          try {
            parsed = JSON.parse(ev.data);
          } catch {
            return;
          }
          const outer = parsed as { type?: string; data?: unknown };
          // Web PubSub wraps our envelope: {type:"message", data:{type, data}}.
          const inner = outer.type === "message" ? (outer.data as StreamMessage) : (parsed as StreamMessage);
          if (inner && typeof inner === "object" && "type" in inner) handle(inner);
        };
        ws.onclose = () => {
          stopHeartbeat();
          if (closed) return;
          setStatus("closed");
          retry += 1;
          timer = setTimeout(connect, Math.min(10_000, 500 * 2 ** retry));
        };
        ws.onerror = () => setStatus("error");
      } catch {
        if (closed) return;
        setStatus("error");
        retry += 1;
        timer = setTimeout(connect, Math.min(10_000, 500 * 2 ** retry));
      }
    };
    void connect();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      stopHeartbeat();
      ws?.close();
      setOverlays([]);
      setEvents([]);
      setTraces([]);
    };
  }, [matchId, profileKey, admin]);

  return { status, match, stats, events, overlays, traces, profileHash, frames, lastEvent };
}
