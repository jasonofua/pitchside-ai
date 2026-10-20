"use client";

// Analyst dashboard: pass network, shot map with xG, pass difficulty histogram and a
// momentum timeline whose moments open the agent's explanation and evidence events.
import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Crest } from "@/components/Scoreboard";
import { api } from "@/lib/api";
import type { Insight, MatchEvent, Moment, MomentumPoint, PassNetwork } from "@/lib/contracts";
import type { AnalystReport, Moments } from "@/lib/types";
import { useMatchId } from "@/lib/useMatchId";
import { useWorld, type WorldIndex } from "@/lib/world";

const L = 105;
const W = 68;

function PitchFrame({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox={`-2 -2 ${L + 4} ${W + 4}`} className="w-full rounded-lg bg-pitch">
      <rect x={0} y={0} width={L} height={W} fill="none" stroke="rgba(255,255,255,.45)" strokeWidth={0.3} />
      <line x1={L / 2} x2={L / 2} y1={0} y2={W} stroke="rgba(255,255,255,.45)" strokeWidth={0.3} />
      <circle cx={L / 2} cy={W / 2} r={9.15} fill="none" stroke="rgba(255,255,255,.45)" strokeWidth={0.3} />
      <rect x={L - 16.5} y={13.84} width={16.5} height={40.32} fill="none" stroke="rgba(255,255,255,.45)" strokeWidth={0.3} />
      <rect x={0} y={13.84} width={16.5} height={40.32} fill="none" stroke="rgba(255,255,255,.45)" strokeWidth={0.3} />
      {children}
    </svg>
  );
}

function Network({ net, color }: { net: PassNetwork; color: string }) {
  const nodes = new Map(net.nodes.map((n) => [n.player_id, n]));
  const max = Math.max(1, ...net.edges.map((e) => e.count));
  const maxPasses = Math.max(1, ...net.nodes.map((n) => n.passes));
  return (
    <PitchFrame>
      {net.edges.map((e) => {
        const a = nodes.get(e.source);
        const b = nodes.get(e.target);
        if (!a || !b) return null;
        return (
          <line key={`${e.source}-${e.target}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={color}
            strokeOpacity={0.25 + 0.6 * (e.count / max)} strokeWidth={0.3 + 1.6 * (e.count / max)} />
        );
      })}
      {net.nodes.map((n) => (
        <g key={n.player_id}>
          <circle cx={n.x} cy={n.y} r={1.2 + 1.8 * (n.passes / maxPasses)} fill={color} stroke="#fff" strokeWidth={0.25} />
          <text x={n.x} y={n.y + 0.6} fontSize={1.7} textAnchor="middle" fill="#fff" fontWeight={700}>
            {n.shirt_number}
          </text>
        </g>
      ))}
    </PitchFrame>
  );
}

function ShotMap({ report, world }: { report: AnalystReport; world: WorldIndex | null }) {
  const home = report.networks[0]?.team_id;
  return (
    <PitchFrame>
      {report.shots.map((s) => {
        // Show home shots attacking right and away shots attacking left.
        const x = s.team_id === home ? s.x : L - s.x;
        const y = s.team_id === home ? s.y : W - s.y;
        const color = world?.clubs.get(s.team_id)?.colors.primary ?? "#ccc";
        const goal = s.outcome === "complete";
        return (
          <circle key={s.event_id} cx={x} cy={y} r={0.8 + 4 * s.xg} fill={goal ? color : "none"} stroke={color}
            strokeWidth={goal ? 0.4 : 0.35} fillOpacity={goal ? 0.9 : 0}>
            <title>{`${s.minute} ${s.player_name}: ${s.xg} xG, ${s.outcome.replace("_", " ")}, ${s.speed_kmh} km/h`}</title>
          </circle>
        );
      })}
    </PitchFrame>
  );
}

function Histogram({ report, world }: { report: AnalystReport; world: WorldIndex | null }) {
  const max = Math.max(1, ...report.histograms.flatMap((h) => h.completed.map((c, i) => c + (h.incomplete[i] ?? 0))));
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {report.histograms.map((h) => {
        const color = world?.clubs.get(h.team_id)?.colors.primary ?? "#ccc";
        return (
          <div key={h.team_id}>
            <div className="mb-1 text-sm text-muted">{world?.clubs.get(h.team_id)?.short_name}</div>
            <div className="flex h-32 items-end gap-1">
              {h.completed.map((c, i) => {
                const inc = h.incomplete[i] ?? 0;
                return (
                  <div key={i} className="flex h-full flex-1 flex-col justify-end" title={`${i * 10}-${i * 10 + 10}: ${c} completed, ${inc} missed`}>
                    <div style={{ height: `${(inc / max) * 100}%`, background: color, opacity: 0.35 }} />
                    <div style={{ height: `${(c / max) * 100}%`, background: color }} />
                  </div>
                );
              })}
            </div>
            <div className="mt-1 flex justify-between text-[0.65rem] text-muted">
              <span>easy 0</span>
              <span>difficulty</span>
              <span>100 hard</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Dashboard() {
  const id = useMatchId();
  const world = useWorld();
  const [report, setReport] = useState<AnalystReport | null>(null);
  const [moments, setMoments] = useState<Moments | null>(null);
  const [picked, setPicked] = useState<Moment | null>(null);
  const [evidence, setEvidence] = useState<MatchEvent[]>([]);

  useEffect(() => {
    if (!id) return;
    const load = () => {
      api.analyst(id).then(setReport).catch(() => undefined);
      api.moments(id).then(setMoments).catch(() => undefined);
    };
    load();
    const t = setInterval(load, 10_000);
    return () => clearInterval(t);
  }, [id]);

  const insights = useMemo(() => new Map((moments?.insights ?? []).map((i: Insight) => [i.moment_id, i])), [moments]);

  useEffect(() => {
    if (!id || !picked) return;
    api
      .events(id, -1, undefined, 500)
      .then((evs) => setEvidence(evs.filter((e) => picked.evidence_event_ids.includes(e.event_id))))
      .catch(() => setEvidence([]));
  }, [id, picked]);

  if (!id) return <main className="p-8 text-muted">No match selected. <Link className="text-accent" href="/">Start one</Link>.</main>;
  if (!report) return <main className="p-8 text-muted">Loading…</main>;
  const [home, away] = report.networks;
  const color = (t?: string) => (t ? world?.clubs.get(t)?.colors.primary ?? "#ccc" : "#ccc");
  const pointMoment = (p: MomentumPoint) =>
    (moments?.moments ?? []).filter((m) => m.period === p.period && Math.abs(m.clock_ms - p.clock_ms) < 60_000)[0] ?? null;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <h1 className="display text-3xl font-bold">Analyst dashboard <span className="text-muted">· {report.minute}</span></h1>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {[home, away].map((net) =>
          net ? (
            <section key={net.team_id} className="glass rounded-xl p-3">
              <h2 className="mb-2 flex items-center gap-2 font-semibold">
                <Crest teamId={net.team_id} size={22} /> Pass network · {world?.clubs.get(net.team_id)?.short_name}
              </h2>
              <Network net={net} color={color(net.team_id)} />
              <p className="mt-1 text-xs text-muted">Average pass and reception positions in the team&apos;s attacking direction; links with 3+ completed passes.</p>
            </section>
          ) : null,
        )}
        <section className="glass rounded-xl p-3">
          <h2 className="mb-2 font-semibold">Shot map (circle size = xG, filled = goal)</h2>
          <ShotMap report={report} world={world} />
        </section>
        <section className="glass rounded-xl p-3">
          <h2 className="mb-2 font-semibold">Pass difficulty</h2>
          <Histogram report={report} world={world} />
        </section>
      </div>
      <section className="glass mt-4 rounded-xl p-3">
        <h2 className="mb-2 font-semibold">Momentum timeline · click a bar for the moment behind it</h2>
        <svg viewBox="0 0 1000 120" preserveAspectRatio="none" className="h-32 w-full">
          <line x1={0} x2={1000} y1={60} y2={60} stroke="var(--color-line)" />
          {report.momentum.map((p, i) => {
            const n = Math.max(report.momentum.length, 190);
            const v = (p.index / 100) * 56;
            const m = pointMoment(p);
            return (
              <rect key={i} x={(i / n) * 1000} width={1000 / n + 0.5} y={v >= 0 ? 60 - v : 60} height={Math.max(1, Math.abs(v))}
                fill={p.home_share > 0.55 ? color(home?.team_id) : p.home_share < 0.45 ? color(away?.team_id) : "#8b98a9"}
                stroke={m ? "#d4ff3a" : undefined} strokeWidth={m ? 1 : 0} style={{ cursor: "pointer" }}
                onClick={() => setPicked(m)}>
                <title>{`${p.minute}: ${p.index}`}</title>
              </rect>
            );
          })}
        </svg>
        <div className="mt-3 flex flex-wrap gap-2">
          {(moments?.moments ?? []).filter((m) => m.importance >= 0.5).map((m) => (
            <button key={m.moment_id} className="chip" aria-pressed={picked?.moment_id === m.moment_id} onClick={() => setPicked(m)}>
              {m.minute} {m.kind.replace("_", " ")}
            </button>
          ))}
        </div>
        {picked ? (
          <div className="mt-3 rounded-lg bg-panel-2 p-3">
            <div className="text-sm text-muted">{picked.minute} · {picked.kind.replace("_", " ")} · importance {picked.importance}</div>
            <h3 className="display text-xl font-bold">{insights.get(picked.moment_id)?.headline ?? picked.summary}</h3>
            {insights.get(picked.moment_id) ? <p className="mt-1">{insights.get(picked.moment_id)?.why_it_matters}</p> : null}
            {insights.get(picked.moment_id)?.stats_cited.length ? (
              <ul className="mt-2 flex flex-wrap gap-2 text-sm">
                {insights.get(picked.moment_id)?.stats_cited.map((s, i) => (
                  <li key={i} className="rounded bg-panel px-2 py-1" title={s.source}>{s.label}: <b>{s.value}{s.unit ? ` ${s.unit}` : ""}</b></li>
                ))}
              </ul>
            ) : null}
            <h4 className="mt-3 text-xs uppercase tracking-wider text-muted">Evidence events</h4>
            <ul className="mt-1 space-y-1 font-mono text-xs">
              {evidence.map((e) => (
                <li key={e.event_id}>
                  #{e.seq} {e.type} {e.team_id} {e.player_id} {e.outcome ?? ""} {e.ball_speed_kmh ? `${e.ball_speed_kmh} km/h` : ""}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </main>
  );
}

export default function Page() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  );
}
