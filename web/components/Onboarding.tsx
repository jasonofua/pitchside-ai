"use client";

// The 20-second onboarding sheet: how you watch, your language, your club, your player and
// the one stat you always want on screen. Stored in the browser only.
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import type { Profile } from "@/lib/contracts";
import { FOCUS_METRICS, LANGUAGES, MODES } from "@/lib/profile";
import type { WorldIndex } from "@/lib/world";
import { Crest } from "./Scoreboard";

interface Props {
  open: boolean;
  initial: Profile;
  world: WorldIndex | null;
  clubs: string[]; // the two clubs in this match
  onSave: (p: Profile) => void;
  onClose?: () => void;
}

export default function Onboarding({ open, initial, world, clubs, onSave, onClose }: Props) {
  const [p, setP] = useState<Profile>(initial);
  const set = (patch: Partial<Profile>) => setP((cur) => ({ ...cur, ...patch }));
  const club = p.favorite_club ? world?.clubs.get(p.favorite_club) : undefined;
  const players = club ? [...club.players].sort((a, b) => a.shirt_number - b.shirt_number) : [];

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 md:items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-t-2xl border border-line bg-panel p-5 md:rounded-2xl"
            initial={{ y: 60 }}
            animate={{ y: 0 }}
            exit={{ y: 60 }}
            role="dialog"
            aria-label="Personalize your match"
          >
            <h2 className="display text-3xl font-bold">How do you watch?</h2>
            <p className="mt-1 text-muted">Twenty seconds, and every card is written for you.</p>

            <Section title="Mode">
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => set({ mode: m.id })}
                    aria-pressed={p.mode === m.id}
                    className={`rounded-xl border p-3 text-left transition ${
                      p.mode === m.id ? "border-accent bg-accent/10" : "border-line hover:border-muted"
                    }`}
                  >
                    <div className="font-semibold">{m.title}</div>
                    <div className="text-xs text-muted">{m.blurb}</div>
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Language">
              <div className="flex flex-wrap gap-2">
                {LANGUAGES.map((l) => (
                  <button key={l.id} className="chip" aria-pressed={p.language === l.id} onClick={() => set({ language: l.id })}>
                    {l.name}
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Your club">
              <div className="flex flex-wrap gap-2">
                {clubs.map((id) => (
                  <button
                    key={id}
                    className="chip flex items-center gap-2"
                    aria-pressed={p.favorite_club === id}
                    onClick={() => set({ favorite_club: id, favorite_player: undefined })}
                  >
                    <Crest teamId={id} size={22} /> {world?.clubs.get(id)?.name ?? id}
                  </button>
                ))}
                <button className="chip" aria-pressed={!p.favorite_club} onClick={() => set({ favorite_club: undefined, favorite_player: undefined })}>
                  Neutral
                </button>
              </div>
            </Section>

            {club ? (
              <Section title={p.mode === "player_cam" ? "Your player (Player Cam follows them)" : "Favourite player"}>
                <select
                  className="w-full rounded-lg border border-line bg-panel-2 p-2"
                  value={p.favorite_player ?? ""}
                  onChange={(e) => set({ favorite_player: e.target.value || undefined })}
                >
                  <option value="">None</option>
                  {players.map((pl) => (
                    <option key={pl.player_id} value={pl.player_id}>
                      #{pl.shirt_number} {pl.name} ({pl.position})
                    </option>
                  ))}
                </select>
              </Section>
            ) : null}

            <Section title="Always show me">
              <div className="flex flex-wrap gap-2">
                {FOCUS_METRICS.map((f) => (
                  <button key={f.id} className="chip" aria-pressed={p.focus_metric === f.id} onClick={() => set({ focus_metric: f.id })}>
                    {f.name}
                  </button>
                ))}
              </div>
            </Section>

            <div className="mt-6 flex justify-end gap-2">
              {onClose ? (
                <button className="btn" onClick={onClose}>
                  Cancel
                </button>
              ) : null}
              <button
                className="btn btn-accent"
                disabled={p.mode === "player_cam" && !p.favorite_player}
                onClick={() => onSave(p)}
              >
                Watch
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">{title}</h3>
      {children}
    </section>
  );
}
