"use client";

// Control vs Chaos across the bottom of the screen: the index every 30 s of match time
// (above the line = control, below = chaos), tinted by whichever team had the ball.
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Lang, MomentumPoint, StatsSnapshot } from "@/lib/contracts";
import { tr } from "@/lib/i18n";
import type { WorldIndex } from "@/lib/world";

interface Props {
  matchId: string | null;
  stats: StatsSnapshot | null;
  world: WorldIndex | null;
  lang: Lang;
  onPick?: (p: MomentumPoint) => void;
  height?: number;
}

export default function MomentumRibbon({ matchId, stats, world, lang, onPick, height = 64 }: Props) {
  const [points, setPoints] = useState<MomentumPoint[]>([]);
  const minuteKey = stats ? `${stats.period}:${Math.floor(stats.clock_ms / 30_000)}` : "";

  useEffect(() => {
    if (!matchId) return;
    let alive = true;
    api
      .momentum(matchId, "match")
      .then((m) => alive && setPoints(m.points))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [matchId, minuteKey]);

  const home = stats?.teams[0]?.team_id;
  const away = stats?.teams[1]?.team_id;
  const hc = home ? world?.clubs.get(home)?.colors.primary : undefined;
  const ac = away ? world?.clubs.get(away)?.colors.primary : undefined;
  const n = Math.max(points.length, 190);
  const w = 1000;
  const mid = height / 2;
  const scale = (height / 2 - 4) / 100;

  return (
    <div className="glass rounded-xl px-3 py-2">
      <div className="mb-1 flex items-center justify-between text-[0.7rem] uppercase tracking-wider text-muted">
        <span>
          {tr("momentum", lang)} · <span className="text-accent">{tr("control", lang)}</span> ↑{" "}
          <span className="text-danger">{tr("chaos", lang)}</span> ↓
        </span>
        <span className="tnum text-text">
          {stats ? `${stats.momentum.index > 0 ? "+" : ""}${stats.momentum.index}` : "—"}
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="block w-full" style={{ height }}>
        <line x1={0} x2={w} y1={mid} y2={mid} stroke="var(--color-line)" />
        {points.map((p, i) => {
          const x = (i / n) * w;
          const bw = w / n + 0.5;
          const v = p.index * scale;
          const color = p.home_share > 0.55 ? hc : p.home_share < 0.45 ? ac : "#8b98a9";
          return (
            <rect
              key={i}
              x={x}
              width={bw}
              y={v >= 0 ? mid - v : mid}
              height={Math.max(1, Math.abs(v))}
              fill={color ?? "#8b98a9"}
              opacity={0.85}
              onClick={() => onPick?.(p)}
              style={{ cursor: onPick ? "pointer" : undefined }}
            >
              <title>{`${p.minute} index ${p.index}`}</title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}
