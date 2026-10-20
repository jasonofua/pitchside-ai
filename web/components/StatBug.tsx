"use client";

// The corner stat bug: one persistent metric (the viewer's focus metric), plus any
// corner_bug card (e.g. a momentum swing) flashing underneath it.
import { AnimatePresence, motion } from "framer-motion";
import type { Lang, Profile, StatsSnapshot } from "@/lib/contracts";
import { tr } from "@/lib/i18n";
import type { LiveOverlay } from "@/lib/stream";
import type { WorldIndex } from "@/lib/world";
import { pick } from "./Overlays";

type Metric = NonNullable<Profile["focus_metric"]>;

function values(stats: StatsSnapshot, metric: Metric, profile: Profile): [string, string] | string {
  const [h, a] = stats.teams;
  if (!h || !a) return "—";
  switch (metric) {
    case "possession": {
      const hp = Math.round(h.possession_pct);
      return [`${hp}%`, `${100 - hp}%`];
    }
    case "xg":
      return [h.xg.toFixed(2), a.xg.toFixed(2)];
    case "shot_speed":
      return [h.max_shot_speed_kmh ? `${h.max_shot_speed_kmh}` : "—", a.max_shot_speed_kmh ? `${a.max_shot_speed_kmh}` : "—"];
    case "top_speed": {
      if (profile.favorite_player) {
        const p = stats.players.find((x) => x.player_id === profile.favorite_player);
        return p?.top_speed_kmh ? `${p.top_speed_kmh} km/h` : "—";
      }
      return [h.top_speed_kmh ? `${h.top_speed_kmh}` : "—", a.top_speed_kmh ? `${a.top_speed_kmh}` : "—"];
    }
    case "distance": {
      if (profile.favorite_player) {
        const p = stats.players.find((x) => x.player_id === profile.favorite_player);
        return p ? `${p.distance_km.toFixed(2)} km` : "—";
      }
      return [`${h.distance_km.toFixed(1)}`, `${a.distance_km.toFixed(1)}`];
    }
    case "pass_accuracy":
      return [`${h.pass_accuracy_pct ?? "—"}%`, `${a.pass_accuracy_pct ?? "—"}%`];
    case "momentum":
      return `${stats.momentum.index > 0 ? "+" : ""}${stats.momentum.index}`;
  }
}

export default function StatBug({
  stats,
  profile,
  cards,
  world,
}: {
  stats: StatsSnapshot | null;
  profile: Profile;
  cards: LiveOverlay[];
  world: WorldIndex | null;
}) {
  const metric: Metric = profile.focus_metric ?? "possession";
  const lang: Lang = profile.language;
  const v = stats ? values(stats, metric, profile) : "—";
  const label = tr(metric === "momentum" ? "momentum" : metric, lang);
  const card = pick(cards, "corner_bug");
  const [h, a] = stats?.teams ?? [];
  return (
    <div className="glass w-56 rounded-xl p-3">
      <div className="text-[0.7rem] uppercase tracking-wider text-muted">{label}</div>
      {Array.isArray(v) ? (
        <div className="display tnum mt-1 flex items-baseline justify-between text-2xl font-bold">
          <span style={{ color: h ? world?.clubs.get(h.team_id)?.colors.primary : undefined }}>{v[0]}</span>
          <span className="text-sm text-muted">vs</span>
          <span style={{ color: a ? world?.clubs.get(a.team_id)?.colors.primary : undefined }}>{v[1]}</span>
        </div>
      ) : (
        <div className="display tnum mt-1 text-3xl font-bold">{v}</div>
      )}
      <AnimatePresence>
        {card ? (
          <motion.div
            key={card.overlay_id}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="mt-2 overflow-hidden border-t border-line pt-2 text-sm"
          >
            <b className="text-accent">{card.title}</b>
            {card.body ? <p className="text-muted">{card.body}</p> : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
