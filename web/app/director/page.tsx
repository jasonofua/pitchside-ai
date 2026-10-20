"use client";

// Director panel: start a scenario, set the speed, pull the chaos switch, inject a wrong
// number for the Fact Checker to catch, and watch the live agent trace.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import Scoreboard from "@/components/Scoreboard";
import { api, ApiError } from "@/lib/api";
import type { AgentTrace } from "@/lib/contracts";
import { DEFAULT_PROFILE } from "@/lib/profile";
import { useMatchStream } from "@/lib/stream";
import type { ScenarioInfo } from "@/lib/types";
import { useMatchId } from "@/lib/useMatchId";
import { useWorld } from "@/lib/world";

const AGENTS = ["moment_detector", "tactical_analyst", "narrator", "fan_lens", "localizer", "fact_checker", "producer"];
const STATUS_COLOR: Record<string, string> = {
  ok: "text-accent",
  regenerated: "text-accent",
  skipped: "text-muted",
  fallback: "text-amber-300",
  timeout: "text-amber-300",
  rejected: "text-danger",
  error: "text-danger",
  circuit_open: "text-danger",
  dropped: "text-muted",
};

function Director() {
  const id = useMatchId();
  const router = useRouter();
  const world = useWorld();
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [scenario, setScenario] = useState("comeback");
  const [speed, setSpeed] = useState(5);
  const [note, setNote] = useState<string | null>(null);
  const [killedUntil, setKilledUntil] = useState(0);
  const [, tick] = useState(0);
  const stream = useMatchStream(id, DEFAULT_PROFILE, { admin: true });
  const [history, setHistory] = useState<AgentTrace[]>([]);

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => undefined);
    const t = setInterval(() => tick((n) => n + 1), 500);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (id) api.trace(id).then(setHistory).catch(() => undefined);
  }, [id]);

  const traces = useMemo(() => {
    const seen = new Set<string>();
    return [...history, ...stream.traces]
      .filter((t) => {
        const k = `${t.trace_id}:${t.agent}:${t.profile_hash ?? ""}:${t.at}`;
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      })
      .slice(-150)
      .reverse();
  }, [history, stream.traces]);

  const stats = useMemo(() => {
    const by: Record<string, { n: number; ms: number; bad: number }> = {};
    for (const t of traces) {
      const s = (by[t.agent] ??= { n: 0, ms: 0, bad: 0 });
      s.n += 1;
      s.ms += t.latency_ms;
      if (["error", "timeout", "rejected", "circuit_open", "fallback"].includes(t.status)) s.bad += 1;
    }
    return by;
  }, [traces]);

  const start = async () => {
    try {
      const { match_id } = await api.start({ scenario, speed });
      router.push(`/director/?id=${match_id}`);
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "could not start");
    }
  };
  const kill = async () => {
    await api.chaos("narrator", 20);
    setKilledUntil(Date.now() + 20_000);
    setNote("Narrator killed for 20 s: watch the fallback cards.");
  };
  const wrong = async () => {
    await api.fault(1);
    setNote("The next card will carry a wrong number. The Fact Checker should reject it.");
  };
  const remaining = Math.max(0, Math.ceil((killedUntil - Date.now()) / 1000));

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <h1 className="display text-3xl font-bold">Director</h1>
      <div className="mt-4 grid gap-4 lg:grid-cols-[22rem_1fr]">
        <aside className="flex flex-col gap-4">
          <section className="glass rounded-xl p-4">
            <h2 className="font-semibold">New match</h2>
            <div className="mt-2 flex flex-wrap gap-2">
              {scenarios.map((s) => (
                <button key={s.name} className="chip" aria-pressed={scenario === s.name} onClick={() => setScenario(s.name)}>
                  {s.name.replace("_", " ")}
                </button>
              ))}
            </div>
            <div className="mt-2 flex gap-2">
              {[1, 5, 20].map((x) => (
                <button key={x} className="chip" aria-pressed={speed === x} onClick={() => setSpeed(x)}>
                  {x}×
                </button>
              ))}
            </div>
            <button className="btn btn-accent mt-3 w-full" onClick={start}>
              Start
            </button>
          </section>
          {id ? (
            <>
              <section className="glass rounded-xl p-4">
                <h2 className="font-semibold">Chaos switch</h2>
                <p className="mt-1 text-sm text-muted">Kill the Narrator for 20 s. Cards fall back to stats-only templates, then recover by themselves.</p>
                <button className="btn mt-3 w-full border-danger text-danger" onClick={kill} disabled={remaining > 0}>
                  {remaining > 0 ? `Narrator down · ${remaining}s` : "Kill the Narrator"}
                </button>
                <button className="btn mt-2 w-full" onClick={wrong}>
                  Inject a wrong number
                </button>
                {note ? <p className="mt-2 text-sm text-accent">{note}</p> : null}
              </section>
              <section className="glass rounded-xl p-4">
                <h2 className="font-semibold">Agents</h2>
                <table className="mt-2 w-full text-sm">
                  <tbody>
                    {AGENTS.map((a) => {
                      const s = stats[a];
                      return (
                        <tr key={a} className="border-t border-line">
                          <td className="py-1">{a.replace("_", " ")}</td>
                          <td className="tnum text-right text-muted">{s ? `${Math.round(s.ms / s.n)} ms` : "—"}</td>
                          <td className="tnum text-right">{s?.n ?? 0}</td>
                          <td className="tnum text-right text-danger">{s?.bad ? s.bad : ""}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div className="mt-2 flex gap-3 text-xs">
                  <Link className="text-accent" href={`/match/?id=${id}`}>Match</Link>
                  <Link className="text-accent" href={`/three/?id=${id}`}>Three Fans</Link>
                  <Link className="text-accent" href={`/analyst/?id=${id}`}>Analyst</Link>
                  <Link className="text-accent" href={`/recap/?id=${id}`}>Recap</Link>
                </div>
              </section>
            </>
          ) : null}
        </aside>
        <section className="flex flex-col gap-3">
          {id ? <Scoreboard match={stream.match} stats={stream.stats} world={world} lang="en" /> : null}
          <div className="glass rounded-xl p-3">
            <h2 className="mb-2 font-semibold">Live agent trace</h2>
            {!id ? <p className="text-muted">Start or pick a match to see the agents at work.</p> : null}
            <ol className="max-h-[70vh] space-y-1 overflow-y-auto font-mono text-xs">
              {traces.map((t, i) => (
                <li key={i} className="grid grid-cols-[4.5rem_8.5rem_6rem_4rem_1fr] gap-2 border-b border-line/60 py-1">
                  <span className="text-muted">{t.at.slice(11, 19)}</span>
                  <span>{t.agent}</span>
                  <span className={STATUS_COLOR[t.status] ?? ""}>{t.status}</span>
                  <span className="tnum text-right text-muted">{t.latency_ms}ms</span>
                  <span className="truncate" title={t.detail ?? ""}>
                    {t.tools?.length ? <span className="text-accent">[{t.tools.join(", ")}] </span> : null}
                    {t.detail}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </section>
      </div>
    </main>
  );
}

export default function Page() {
  return (
    <Suspense>
      <Director />
    </Suspense>
  );
}
