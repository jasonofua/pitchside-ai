"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Crest } from "@/components/Scoreboard";
import { api, ApiError } from "@/lib/api";
import type { MatchInfo } from "@/lib/contracts";
import type { ScenarioInfo } from "@/lib/types";
import { useWorld } from "@/lib/world";

const SPEEDS = [1, 5, 20];

export default function Home() {
  const router = useRouter();
  const world = useWorld();
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [scenario, setScenario] = useState("comeback");
  const [speed, setSpeed] = useState(5);
  const [matches, setMatches] = useState<MatchInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => setError("The match server is not reachable."));
    const load = () => api.matches().then(setMatches).catch(() => undefined);
    void load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const start = async (view: "match" | "three") => {
    setBusy(true);
    setError(null);
    try {
      const { match_id } = await api.start({ scenario, speed });
      router.push(`/${view}/?id=${encodeURIComponent(match_id)}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start a match.");
      setBusy(false);
    }
  };

  const chosen = scenarios.find((s) => s.name === scenario);
  const live = matches.filter((m) => m.status === "live" || m.status === "half_time");
  const done = matches.filter((m) => m.status === "full_time").slice(0, 6);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 md:py-14">
      <section className="grid items-center gap-10 md:grid-cols-[1.2fr_1fr]">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-accent">Live match intelligence</p>
          <h1 className="display mt-3 text-5xl font-extrabold leading-[0.95] md:text-7xl">
            Every fan saw the same goal.
            <br />
            <span className="text-accent">Each one gets their own story.</span>
          </h1>
          <p className="mt-5 max-w-xl text-lg text-muted">
            Seven AI agents watch a synthetic match as it happens, explain why each moment matters, check
            every number against one source of truth and rewrite the story for each viewer: analyst or casual
            fan, any club, in English, Pidgin, Yorùbá, French or Spanish.
          </p>
        </div>

        <div className="glass rounded-2xl p-5">
          <h2 className="display text-2xl font-bold">Start a demo match</h2>
          <label className="mt-4 block text-xs uppercase tracking-wider text-muted">Story</label>
          <div className="mt-2 flex flex-wrap gap-2">
            {scenarios.map((s) => (
              <button key={s.name} className="chip" aria-pressed={scenario === s.name} onClick={() => setScenario(s.name)}>
                {s.name.replace("_", " ")}
              </button>
            ))}
          </div>
          {chosen ? (
            <div className="mt-3 flex items-center gap-3 rounded-lg bg-panel-2 p-3 text-sm">
              <Crest teamId={chosen.home} size={28} />
              <span className="font-semibold">{world?.clubs.get(chosen.home)?.short_name}</span>
              <span className="text-muted">v</span>
              <span className="font-semibold">{world?.clubs.get(chosen.away)?.short_name}</span>
              <Crest teamId={chosen.away} size={28} />
            </div>
          ) : null}
          {chosen ? <p className="mt-2 text-sm text-muted">{chosen.description}</p> : null}
          <label className="mt-4 block text-xs uppercase tracking-wider text-muted">Speed</label>
          <div className="mt-2 flex gap-2">
            {SPEEDS.map((x) => (
              <button key={x} className="chip tnum" aria-pressed={speed === x} onClick={() => setSpeed(x)}>
                {x}×
              </button>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <button className="btn btn-accent" disabled={busy} onClick={() => start("match")}>
              {busy ? "Starting…" : "Start demo match"}
            </button>
            <button className="btn" disabled={busy} onClick={() => start("three")}>
              Start in Three Fans view
            </button>
          </div>
          {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
          <p className="mt-3 text-xs text-muted">No login. A {speed}× match lasts about {Math.round(95 / speed)} minutes.</p>
        </div>
      </section>

      <section className="mt-12">
        <h2 className="display text-2xl font-bold">Live now</h2>
        {live.length === 0 ? <p className="mt-2 text-muted">No live matches. Start one above.</p> : null}
        <MatchList matches={live} />
        {done.length ? (
          <>
            <h2 className="display mt-8 text-2xl font-bold">Recent</h2>
            <MatchList matches={done} finished />
          </>
        ) : null}
      </section>
    </main>
  );
}

function MatchList({ matches, finished }: { matches: MatchInfo[]; finished?: boolean }) {
  const world = useWorld();
  return (
    <ul className="mt-3 grid gap-3 md:grid-cols-2">
      {matches.map((m) => (
        <li key={m.match_id} className="glass flex flex-wrap items-center gap-3 rounded-xl p-3">
          <Crest teamId={m.home} size={28} />
          <span className="font-semibold">{world?.clubs.get(m.home)?.short_name ?? m.home}</span>
          <span className="text-muted">v</span>
          <span className="font-semibold">{world?.clubs.get(m.away)?.short_name ?? m.away}</span>
          <Crest teamId={m.away} size={28} />
          <span className="text-xs text-muted">
            {m.scenario} · {m.speed}× · {m.status.replace("_", " ")}
          </span>
          <span className="ml-auto flex gap-2 text-sm">
            {finished ? (
              <>
                <Link className="text-accent hover:underline" href={`/recap/?id=${m.match_id}`}>
                  Recap
                </Link>
                <Link className="hover:underline" href={`/analyst/?id=${m.match_id}`}>
                  Analyst
                </Link>
              </>
            ) : (
              <>
                <Link className="text-accent hover:underline" href={`/match/?id=${m.match_id}`}>
                  Watch
                </Link>
                <Link className="hover:underline" href={`/three/?id=${m.match_id}`}>
                  Three Fans
                </Link>
                <Link className="hover:underline" href={`/director/?id=${m.match_id}`}>
                  Director
                </Link>
              </>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}
