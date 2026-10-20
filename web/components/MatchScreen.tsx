"use client";

// The broadcast match screen for one viewer profile: scoreboard and clock, the 2D pitch
// with player tags, the full centre card, the lower-third rail, the corner stat bug, the
// ticker and the momentum ribbon. The Three Fans view renders three of these.
import type { Profile } from "@/lib/contracts";
import { tr } from "@/lib/i18n";
import { useMatchStream } from "@/lib/stream";
import type { WorldIndex } from "@/lib/world";
import MomentumRibbon from "./MomentumRibbon";
import { FullCard, LowerThird, Ticker } from "./Overlays";
import Pitch from "./Pitch";
import Scoreboard from "./Scoreboard";
import StatBug from "./StatBug";

interface Props {
  matchId: string;
  profile: Profile;
  world: WorldIndex | null;
  compact?: boolean;
  label?: string;
}

export default function MatchScreen({ matchId, profile, world, compact, label }: Props) {
  const s = useMatchStream(matchId, profile);
  const home = s.match?.home ?? s.stats?.teams[0]?.team_id ?? null;
  const away = s.match?.away ?? s.stats?.teams[1]?.team_id ?? null;
  const tags = s.overlays.filter((o) => o.slot === "player_tag");
  const focus = profile.mode === "player_cam" ? profile.favorite_player ?? null : profile.favorite_player ?? null;
  const waiting = !s.stats && s.status !== "error";

  return (
    <div className={`flex flex-col gap-3 ${compact ? "" : "mx-auto max-w-6xl"}`}>
      <div className="flex flex-wrap items-center gap-3">
        <Scoreboard match={s.match} stats={s.stats} world={world} lang={profile.language} compact={compact} />
        {label ? <span className="rounded-md bg-accent px-2 py-1 text-xs font-bold text-accent-ink">{label}</span> : null}
        {s.status !== "live" ? (
          <span className="text-xs text-muted">{s.status === "connecting" ? "connecting…" : s.status}</span>
        ) : null}
      </div>
      <div className={`grid gap-3 ${compact ? "" : "md:grid-cols-[1fr_15rem]"}`}>
        <div
          className="relative mx-auto w-full"
          // Keep the whole broadcast screen on one display: the pitch shrinks with the height.
          style={compact ? undefined : { maxWidth: "max(22rem, calc((100vh - 19rem) * 1.544))" }}
        >
          <Pitch frames={s.frames} world={world} home={home} away={away} tags={tags} focusPlayer={focus} />
          <FullCard cards={s.overlays} world={world} />
          {compact ? null : (
            <div className="absolute inset-x-3 bottom-3 z-10">
              <LowerThird cards={s.overlays} world={world} floating />
            </div>
          )}
          {waiting ? (
            <div className="absolute inset-0 flex items-center justify-center text-muted">{tr("waiting", profile.language)}</div>
          ) : null}
        </div>
        {compact ? null : (
          <div className="flex flex-col gap-3">
            <StatBug stats={s.stats} profile={profile} cards={s.overlays} world={world} />
            <PlayerPanel profile={profile} world={world} stats={s.stats} />
          </div>
        )}
      </div>
      {compact ? <LowerThird cards={s.overlays} world={world} /> : null}
      {compact ? <StatBug stats={s.stats} profile={profile} cards={s.overlays} world={world} /> : null}
      <Ticker cards={s.overlays} />
      <MomentumRibbon matchId={matchId} stats={s.stats} world={world} lang={profile.language} height={compact ? 40 : 64} />
    </div>
  );
}

function PlayerPanel({
  profile,
  world,
  stats,
}: {
  profile: Profile;
  world: WorldIndex | null;
  stats: ReturnType<typeof useMatchStream>["stats"];
}) {
  const pid = profile.favorite_player;
  if (!pid || !stats) return null;
  const line = stats.players.find((p) => p.player_id === pid);
  const player = world?.players.get(pid);
  if (!line || !player) return null;
  const rows: [string, string][] = [
    ["Touches", String(line.touches)],
    ["Passes", `${line.passes_completed}/${line.passes}`],
    ["Shots", String(line.shots)],
    ["Distance", `${line.distance_km.toFixed(2)} km`],
    ["Top speed", line.top_speed_kmh ? `${line.top_speed_kmh} km/h` : "—"],
  ];
  return (
    <div className="glass rounded-xl p-3">
      <div className="text-[0.7rem] uppercase tracking-wider text-muted">Player Cam</div>
      <div className="display text-xl font-bold">
        #{player.shirt_number} {player.short_name}
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="tnum text-right font-semibold">{v}</dd>
          </div>
        ))}
      </dl>
      {!line.on_pitch ? <div className="mt-2 text-xs text-muted">Not on the pitch</div> : null}
    </div>
  );
}
