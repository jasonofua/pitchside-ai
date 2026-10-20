"use client";

// 2D pitch animated from 5 Hz tracking frames. Positions are interpolated between the last
// two frames on every animation frame, so movement looks smooth at 60 fps. Coordinates are
// absolute (home attacks towards x=105). Player tags (overlay slot "player_tag") pop next
// to their player.
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import type { Club } from "@/lib/contracts";
import type { FrameBuffer, LiveOverlay } from "@/lib/stream";
import type { WorldIndex } from "@/lib/world";

const L = 105;
const W = 68;

interface Props {
  frames: React.MutableRefObject<FrameBuffer>;
  world: WorldIndex | null;
  home: string | null;
  away: string | null;
  tags?: LiveOverlay[];
  focusPlayer?: string | null;
  className?: string;
}

interface TagPos {
  id: string;
  x: number;
  y: number;
  card: LiveOverlay;
}

function contrast(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#0b0f14" : "#ffffff";
}

function drawPitch(ctx: CanvasRenderingContext2D, s: number) {
  const stripes = 12;
  for (let i = 0; i < stripes; i++) {
    ctx.fillStyle = i % 2 ? "#124530" : "#0f3b26";
    ctx.fillRect((i * L * s) / stripes, 0, (L * s) / stripes + 1, W * s);
  }
  ctx.strokeStyle = "rgba(255,255,255,0.55)";
  ctx.lineWidth = Math.max(1, s * 0.12);
  ctx.strokeRect(0.5, 0.5, L * s - 1, W * s - 1);
  ctx.beginPath();
  ctx.moveTo((L / 2) * s, 0);
  ctx.lineTo((L / 2) * s, W * s);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc((L / 2) * s, (W / 2) * s, 9.15 * s, 0, Math.PI * 2);
  ctx.stroke();
  for (const left of [true, false]) {
    const x0 = left ? 0 : L;
    const dir = left ? 1 : -1;
    ctx.strokeRect(Math.min(x0, x0 + dir * 16.5) * s, 13.84 * s, 16.5 * s, 40.32 * s);
    ctx.strokeRect(Math.min(x0, x0 + dir * 5.5) * s, 24.84 * s, 5.5 * s, 18.32 * s);
    ctx.beginPath();
    ctx.arc((x0 + dir * 11) * s, (W / 2) * s, 9.15 * s, left ? -0.93 : Math.PI - 0.93, left ? 0.93 : Math.PI + 0.93);
    ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,0.8)";
    ctx.fillRect((left ? -0.6 : L) * s, (W / 2 - 3.66) * s, 0.6 * s, 7.32 * s);
  }
}

export default function Pitch({ frames, world, home, away, tags = [], focusPlayer, className }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [tagPos, setTagPos] = useState<TagPos[]>([]);
  const tagsRef = useRef(tags);
  tagsRef.current = tags;

  useEffect(() => {
    let raf = 0;
    let lastTagUpdate = 0;
    const clubs = new Map<string, Club>();
    if (world && home) {
      const h = world.clubs.get(home);
      if (h) clubs.set(home, h);
    }
    if (world && away) {
      const a = world.clubs.get(away);
      if (a) clubs.set(away, a);
    }
    const draw = (now: number) => {
      const c = canvas.current;
      const box = wrap.current;
      if (!c || !box) {
        raf = requestAnimationFrame(draw);
        return;
      }
      const dpr = window.devicePixelRatio || 1;
      const cssW = box.clientWidth;
      const cssH = (cssW * W) / L;
      if (c.width !== Math.round(cssW * dpr)) {
        c.width = Math.round(cssW * dpr);
        c.height = Math.round(cssH * dpr);
        c.style.height = `${cssH}px`;
      }
      const ctx = c.getContext("2d");
      if (!ctx) return;
      const s = (cssW / L) * dpr;
      drawPitch(ctx, s);

      const { prev, curr, receivedAt, intervalMs } = frames.current;
      if (curr) {
        const t = prev && prev.period === curr.period ? Math.min(1, (now - receivedAt) / intervalMs) : 1;
        const before = new Map((prev?.players ?? []).map((p) => [p.player_id, p]));
        const positions: { id: string; x: number; y: number }[] = [];
        for (const p of curr.players) {
          const q = before.get(p.player_id);
          const x = q ? q.x + (p.x - q.x) * t : p.x;
          const y = q ? q.y + (p.y - q.y) * t : p.y;
          positions.push({ id: p.player_id, x, y });
          const player = world?.players.get(p.player_id);
          const club = player ? clubs.get(player.team_id) : undefined;
          const fill = club?.colors.primary ?? "#cccccc";
          const r = 1.25 * s;
          ctx.beginPath();
          ctx.arc(x * s, y * s, r, 0, Math.PI * 2);
          ctx.fillStyle = fill;
          ctx.fill();
          ctx.lineWidth = Math.max(1, 0.25 * s);
          ctx.strokeStyle = club?.colors.secondary ?? "#000";
          ctx.stroke();
          if (focusPlayer === p.player_id) {
            ctx.beginPath();
            ctx.arc(x * s, y * s, r + 0.9 * s, 0, Math.PI * 2);
            ctx.strokeStyle = "#d4ff3a";
            ctx.lineWidth = Math.max(1.5, 0.35 * s);
            ctx.stroke();
          }
          if (player && s > 4) {
            ctx.fillStyle = contrast(fill);
            ctx.font = `700 ${Math.round(1.25 * s)}px Inter, system-ui, sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(String(player.shirt_number), x * s, y * s + 0.05 * s);
          }
        }
        const pb = prev?.ball;
        const bx = pb && t < 1 ? pb.x + (curr.ball.x - pb.x) * t : curr.ball.x;
        const by = pb && t < 1 ? pb.y + (curr.ball.y - pb.y) * t : curr.ball.y;
        ctx.beginPath();
        ctx.arc(bx * s, by * s, 0.7 * s, 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        ctx.shadowColor = "rgba(0,0,0,0.6)";
        ctx.shadowBlur = 0.6 * s;
        ctx.fill();
        ctx.shadowBlur = 0;

        if (now - lastTagUpdate > 120 && tagsRef.current.length) {
          lastTagUpdate = now;
          const byId = new Map(positions.map((p) => [p.id, p]));
          const next: TagPos[] = [];
          for (const card of tagsRef.current) {
            const target = card.player_id ? byId.get(card.player_id) : undefined;
            if (target) next.push({ id: card.overlay_id, x: target.x, y: target.y, card });
          }
          setTagPos(next);
        } else if (!tagsRef.current.length && lastTagUpdate !== -1) {
          lastTagUpdate = -1;
          setTagPos([]);
        }
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [frames, world, home, away, focusPlayer]);

  return (
    <div ref={wrap} className={`relative w-full overflow-hidden rounded-xl ${className ?? ""}`}>
      <canvas ref={canvas} className="block w-full" />
      <AnimatePresence>
        {tagPos.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, scale: 0.6, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className={`pointer-events-none absolute z-10 whitespace-nowrap rounded-md bg-accent px-2 py-1 text-xs font-bold text-accent-ink shadow-lg md:text-sm ${
              t.x > L * 0.75 ? "-translate-x-full" : t.x < L * 0.25 ? "" : "-translate-x-1/2"
            } ${t.y < W * 0.15 ? "translate-y-[40%]" : "-translate-y-[120%]"}`}
            style={{ left: `${(t.x / L) * 100}%`, top: `${(t.y / W) * 100}%` }}
          >
            {t.card.title}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
