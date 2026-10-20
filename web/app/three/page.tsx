"use client";

// Three Fans: the same match in three panes, one per profile. The demo's money shot.
import Link from "next/link";
import { Suspense } from "react";
import MatchScreen from "@/components/MatchScreen";
import { DEMO_PROFILES } from "@/lib/profile";
import { useMatchId } from "@/lib/useMatchId";
import { useWorld } from "@/lib/world";

const LABELS = ["Analyst · English", "Casual fan · Pidgin", "Player Cam · Yorùbá"];

function ThreeFans() {
  const id = useMatchId();
  const world = useWorld();
  if (!id) {
    return (
      <main className="p-8 text-muted">
        No match selected. <Link className="text-accent" href="/">Start one</Link>.
      </main>
    );
  }
  return (
    <main className="px-3 py-4">
      <h1 className="display mb-3 text-center text-2xl font-bold md:text-3xl">
        One match. <span className="text-accent">Three fans.</span> Three stories.
      </h1>
      <div className="grid gap-4 xl:grid-cols-3">
        {DEMO_PROFILES.map((p, i) => (
          <section key={i} className="rounded-2xl border border-line p-2">
            <MatchScreen matchId={id} profile={p} world={world} compact label={LABELS[i]} />
          </section>
        ))}
      </div>
    </main>
  );
}

export default function Page() {
  return (
    <Suspense>
      <ThreeFans />
    </Suspense>
  );
}
