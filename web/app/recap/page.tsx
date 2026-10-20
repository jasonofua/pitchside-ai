"use client";

// Full-time recap: headline, five key moments, player of the match, stat cards, a
// language switch and "copy as JSON" for broadcast tooling.
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { Crest } from "@/components/Scoreboard";
import { api, ApiError } from "@/lib/api";
import { LANGUAGES } from "@/lib/profile";
import type { Recap } from "@/lib/types";
import { useMatchId } from "@/lib/useMatchId";
import { useWorld } from "@/lib/world";

function fmt(label: string, v: number | string | null): string {
  if (v === null) return "—";
  if (typeof v === "number" && label === "xG") return v.toFixed(2);
  return String(v);
}

function RecapPage() {
  const id = useMatchId();
  const world = useWorld();
  const [recap, setRecap] = useState<Recap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState("en");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    // The recap is written at full time: poll until it exists, then stop.
    const load = () =>
      api
        .recap(id)
        .then((r) => {
          if (!alive) return;
          setRecap(r);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!alive) return;
          setError(e instanceof ApiError ? e.message : "Recap unavailable");
          timer = setTimeout(load, 8000);
        });
    void load();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [id]);

  if (!id) return <main className="p-8 text-muted">No match selected. <Link className="text-accent" href="/">Start one</Link>.</main>;
  if (!recap) return <main className="p-8 text-muted">{error ?? "Loading…"}</main>;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(recap, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex flex-wrap items-center gap-2">
        {LANGUAGES.filter((l) => recap.languages.includes(l.id)).map((l) => (
          <button key={l.id} className="chip" aria-pressed={lang === l.id} onClick={() => setLang(l.id)}>
            {l.name}
          </button>
        ))}
        <button className="btn ml-auto" onClick={copy}>
          {copied ? "Copied" : "Copy as JSON"}
        </button>
      </div>
      <p className="mt-6 text-sm uppercase tracking-[0.2em] text-accent">Full time · {recap.final_score}</p>
      <h1 className="display mt-2 text-4xl font-extrabold md:text-6xl">{recap.headline[lang] ?? recap.headline.en}</h1>
      <p className="mt-4 max-w-3xl text-lg leading-relaxed">{recap.story[lang] ?? recap.story.en}</p>

      <section className="mt-8 grid gap-3 md:grid-cols-3">
        {recap.stat_cards.map((c) => (
          <div key={c.label} className="glass rounded-xl p-4">
            <div className="text-xs uppercase tracking-wider text-muted">{c.label}</div>
            <div className="display tnum mt-1 text-3xl font-bold">
              {fmt(c.label, c.home)}
              {c.unit ?? ""} <span className="text-lg text-muted">–</span> {fmt(c.label, c.away)}
              {c.unit ?? ""}
            </div>
          </div>
        ))}
      </section>

      {recap.player_of_the_match ? (
        <section className="glass mt-8 flex flex-wrap items-center gap-4 rounded-xl p-5">
          <Crest teamId={recap.player_of_the_match.team_id} size={48} />
          <div>
            <div className="text-xs uppercase tracking-wider text-accent">Player of the match</div>
            <div className="display text-3xl font-bold">{recap.player_of_the_match.name}</div>
            <div className="text-sm text-muted">{world?.clubs.get(recap.player_of_the_match.team_id)?.name}</div>
          </div>
          <div className="ml-auto flex flex-wrap gap-2">
            {recap.player_of_the_match.stats.map((s) => (
              <span key={s.label} className="rounded-md bg-panel-2 px-3 py-2 text-sm">
                <span className="text-muted">{s.label} </span>
                <b className="tnum">
                  {s.value}
                  {s.unit ? ` ${s.unit}` : ""}
                </b>
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <section className="mt-8">
        <h2 className="display text-2xl font-bold">Five key moments</h2>
        <ol className="mt-3 space-y-3">
          {recap.key_moments.map((m) => (
            <li key={m.moment_id} className="glass rounded-xl p-4">
              <div className="text-sm text-muted">
                {m.minute} · {m.kind.replace("_", " ")}
              </div>
              <div className="display text-xl font-bold">{m.headline}</div>
              <p className="mt-1 text-text/90">{m.why_it_matters}</p>
            </li>
          ))}
        </ol>
      </section>
      <p className="mt-8 text-xs text-muted">Written by {recap.generated_by}. Every number checked against the Stats Engine.</p>
    </main>
  );
}

export default function Page() {
  return (
    <Suspense>
      <RecapPage />
    </Suspense>
  );
}
