"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import MatchScreen from "@/components/MatchScreen";
import Onboarding from "@/components/Onboarding";
import { DEFAULT_PROFILE, LANGUAGES, MODES, useProfile } from "@/lib/profile";
import { useMatchId } from "@/lib/useMatchId";
import { useMatchStream } from "@/lib/stream";
import { useWorld } from "@/lib/world";

function MatchPage() {
  const id = useMatchId();
  const world = useWorld();
  const [profile, saveProfile, loaded] = useProfile();
  const [editing, setEditing] = useState(false);
  // A light connection just to learn which clubs are playing, for the onboarding sheet.
  const probe = useMatchStream(id, profile ? null : DEFAULT_PROFILE);
  const clubs = [probe.match?.home, probe.match?.away].filter((c): c is string => !!c);
  const fallbackClubs = clubs.length ? clubs : (world?.world.clubs.map((c) => c.team_id) ?? []);

  if (!id) {
    return (
      <main className="p-8 text-muted">
        No match selected. <Link className="text-accent" href="/">Start one</Link>.
      </main>
    );
  }
  if (!loaded) return null;
  const mode = profile ? MODES.find((m) => m.id === profile.mode)?.title : null;
  const lang = profile ? LANGUAGES.find((l) => l.id === profile.language)?.name : null;

  return (
    <main className="px-3 py-4 md:px-6">
      {profile ? (
        <>
          <div className="mx-auto mb-3 flex max-w-6xl items-center gap-3 text-sm text-muted">
            <span>
              Watching as <b className="text-text">{mode}</b> in <b className="text-text">{lang}</b>
              {profile.favorite_club ? (
                <>
                  {" "}
                  · <b className="text-text">{world?.clubs.get(profile.favorite_club)?.short_name}</b> fan
                </>
              ) : null}
            </span>
            <button className="chip" onClick={() => setEditing(true)}>
              Change
            </button>
            <Link className="ml-auto hover:text-text" href={`/three/?id=${id}`}>
              Three Fans view →
            </Link>
          </div>
          <MatchScreen matchId={id} profile={profile} world={world} />
        </>
      ) : null}
      <Onboarding
        open={!profile || editing}
        initial={profile ?? DEFAULT_PROFILE}
        world={world}
        clubs={fallbackClubs}
        onSave={(p) => {
          saveProfile(p);
          setEditing(false);
        }}
        onClose={profile ? () => setEditing(false) : undefined}
      />
    </main>
  );
}

export default function Page() {
  return (
    <Suspense>
      <MatchPage />
    </Suspense>
  );
}
