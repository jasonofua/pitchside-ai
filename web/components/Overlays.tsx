"use client";

// The overlay slots: lower-third rail, full centre card, ticker and the corner bug's
// cards. Each slot shows the highest-priority live card, newest first on ties; an
// upgraded agent card replaces its template card in place (same overlay_id).
import { AnimatePresence, motion } from "framer-motion";
import type { StatItem } from "@/lib/contracts";
import type { LiveOverlay } from "@/lib/stream";
import type { WorldIndex } from "@/lib/world";

export function pick(cards: LiveOverlay[], slot: LiveOverlay["slot"]): LiveOverlay | null {
  const inSlot = cards.filter((c) => c.slot === slot);
  if (!inSlot.length) return null;
  return inSlot.reduce((best, c) =>
    c.priority > best.priority || (c.priority === best.priority && c.receivedAt > best.receivedAt) ? c : best,
  );
}

function Stats({ stats, large }: { stats: StatItem[]; large?: boolean }) {
  if (!stats.length) return null;
  return (
    <div className={`mt-2 flex flex-wrap gap-2 ${large ? "justify-center" : ""}`}>
      {stats.map((s, i) => (
        <span key={i} className="rounded-md bg-panel-2 px-2 py-1 text-sm">
          <span className="text-muted">{s.label} </span>
          <span className="tnum font-semibold">
            {s.value}
            {s.unit && s.unit !== "%" ? ` ${s.unit}` : s.unit}
          </span>
        </span>
      ))}
    </div>
  );
}

function SourceBadge({ card }: { card: LiveOverlay }) {
  const agent = card.source !== "template";
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[0.65rem] font-bold uppercase tracking-wider ${
        agent ? "bg-accent text-accent-ink" : "bg-panel-2 text-muted"
      }`}
      title={agent ? "Written by the agent crew, fact-checked" : "Stats-only card"}
    >
      {agent ? "AI" : "Stats"}
    </span>
  );
}

export function LowerThird({
  cards,
  world,
  floating,
}: {
  cards: LiveOverlay[];
  world: WorldIndex | null;
  floating?: boolean; // laid over the pitch, broadcast style
}) {
  const card = pick(cards, "lower_third");
  const color = card?.team_id ? world?.clubs.get(card.team_id)?.colors.primary : undefined;
  return (
    <div className={`pointer-events-none ${floating ? "" : "min-h-[5.5rem]"}`}>
      <AnimatePresence mode="wait">
        {card ? (
          <motion.div
            key={card.overlay_id + card.title}
            initial={{ x: -40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 26 }}
            className={`glass flex overflow-hidden rounded-xl ${floating ? "max-w-3xl shadow-2xl" : ""}`}
          >
            <span className="w-2 shrink-0" style={{ background: color ?? "var(--color-accent)" }} />
            <div className="px-4 py-3">
              <div className="flex items-center gap-2">
                <SourceBadge card={card} />
                <h3 className="display text-xl font-bold leading-tight md:text-2xl">{card.title}</h3>
              </div>
              {card.body ? <p className="mt-1 text-base leading-snug text-text/90 md:text-lg">{card.body}</p> : null}
              <Stats stats={card.stats} />
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

export function FullCard({ cards, world }: { cards: LiveOverlay[]; world: WorldIndex | null }) {
  const card = pick(cards, "full_card");
  const color = card?.team_id ? world?.clubs.get(card.team_id)?.colors.primary : undefined;
  return (
    <AnimatePresence>
      {card ? (
        <motion.div
          key={card.overlay_id}
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 1.05 }}
          transition={{ type: "spring", stiffness: 220, damping: 22 }}
          className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center p-4"
        >
          <div
            className="glass max-w-xl rounded-2xl px-6 py-5 text-center shadow-2xl"
            style={{ borderColor: color ?? "var(--color-accent)", borderWidth: 2 }}
          >
            <div className="mb-1 flex justify-center">
              <SourceBadge card={card} />
            </div>
            <h2 className="display text-3xl font-extrabold uppercase md:text-5xl">{card.title}</h2>
            {card.body ? <p className="mt-2 text-lg md:text-xl">{card.body}</p> : null}
            <Stats stats={card.stats} large />
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

export function Ticker({ cards }: { cards: LiveOverlay[] }) {
  const items = cards.filter((c) => c.slot === "ticker").sort((a, b) => b.receivedAt - a.receivedAt).slice(0, 3);
  return (
    <div className="flex min-h-9 items-center gap-3 overflow-hidden rounded-lg bg-panel px-3 text-sm">
      <span className="display shrink-0 font-bold uppercase tracking-wider text-accent">Ticker</span>
      <AnimatePresence initial={false}>
        {items.map((c) => (
          <motion.span
            key={c.overlay_id}
            layout
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="truncate whitespace-nowrap"
          >
            <b>{c.title}</b>
            {c.body ? <span className="text-muted"> · {c.body}</span> : null}
          </motion.span>
        ))}
      </AnimatePresence>
    </div>
  );
}
