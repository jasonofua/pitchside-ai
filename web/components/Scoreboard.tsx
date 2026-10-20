"use client";

import { AnimatePresence, motion } from "framer-motion";
import { api } from "@/lib/api";
import type { Lang, MatchInfo, StatsSnapshot } from "@/lib/contracts";
import { tr } from "@/lib/i18n";
import type { WorldIndex } from "@/lib/world";

export function Crest({ teamId, size = 36 }: { teamId: string; size?: number }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={api.crestUrl(teamId)} alt="" width={size} height={size} className="shrink-0" />;
}

interface Props {
  match: MatchInfo | null;
  stats: StatsSnapshot | null;
  world: WorldIndex | null;
  lang: Lang;
  compact?: boolean;
}

export default function Scoreboard({ match, stats, world, lang, compact }: Props) {
  const home = match?.home ?? stats?.teams[0]?.team_id ?? null;
  const away = match?.away ?? stats?.teams[1]?.team_id ?? null;
  const hc = home ? world?.clubs.get(home) : undefined;
  const ac = away ? world?.clubs.get(away) : undefined;
  const hs = stats?.teams[0]?.goals ?? 0;
  const as = stats?.teams[1]?.goals ?? 0;
  const status = stats?.status ?? match?.status ?? "scheduled";
  const label =
    status === "half_time" ? tr("half_time", lang) : status === "full_time" ? tr("full_time", lang) : null;
  const size = compact ? 26 : 36;

  return (
    <div className={`glass flex items-stretch overflow-hidden rounded-xl ${compact ? "text-base" : "text-xl md:text-2xl"}`}>
      <Side name={hc?.short_name ?? home ?? "—"} color={hc?.colors.primary} teamId={home} size={size} />
      <div className="display tnum flex items-center gap-3 bg-panel-2 px-4 font-bold">
        <Digit value={hs} />
        <span className="text-muted">–</span>
        <Digit value={as} />
      </div>
      <Side name={ac?.short_name ?? away ?? "—"} color={ac?.colors.primary} teamId={away} size={size} reverse />
      <div className="flex min-w-[5.5rem] flex-col items-center justify-center border-l border-line px-3">
        <span className="display tnum text-lg font-semibold md:text-xl">{stats?.clock_display ?? "00:00"}</span>
        {label ? (
          <span className="text-[0.7rem] uppercase tracking-wider text-accent">{label}</span>
        ) : status === "live" ? (
          <span className="flex items-center gap-1 text-[0.7rem] uppercase tracking-wider text-muted">
            <span className="live-dot" /> {tr("live", lang)}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function Side({
  name,
  color,
  teamId,
  size,
  reverse,
}: {
  name: string;
  color?: string;
  teamId: string | null;
  size: number;
  reverse?: boolean;
}) {
  return (
    <div className={`flex items-center gap-2 px-3 py-2 ${reverse ? "flex-row-reverse" : ""}`}>
      <span className="h-8 w-1.5 rounded-full" style={{ background: color ?? "#888" }} aria-hidden />
      {teamId ? <Crest teamId={teamId} size={size} /> : null}
      <span className="display font-bold uppercase tracking-wide">{name}</span>
    </div>
  );
}

function Digit({ value }: { value: number }) {
  return (
    <span className="relative inline-flex w-[1ch] justify-center overflow-hidden">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={value}
          initial={{ y: "-100%", opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: "100%", opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 24 }}
        >
          {value}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
