"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import type { Club, Player, World } from "./contracts";

let cache: Promise<World> | null = null;

export function loadWorld(): Promise<World> {
  if (!cache) {
    cache = api.world().catch((e: unknown) => {
      cache = null;
      throw e;
    });
  }
  return cache;
}

export interface WorldIndex {
  world: World;
  clubs: Map<string, Club>;
  players: Map<string, Player & { team_id: string }>;
}

export function indexWorld(world: World): WorldIndex {
  const clubs = new Map<string, Club>();
  const players = new Map<string, Player & { team_id: string }>();
  for (const club of world.clubs) {
    clubs.set(club.team_id, club);
    for (const p of club.players) players.set(p.player_id, { ...p, team_id: club.team_id });
  }
  return { world, clubs, players };
}

export function useWorld(): WorldIndex | null {
  const [index, setIndex] = useState<WorldIndex | null>(null);
  useEffect(() => {
    let alive = true;
    loadWorld()
      .then((w) => alive && setIndex(indexWorld(w)))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return index;
}
