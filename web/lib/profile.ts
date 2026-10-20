"use client";

import { useCallback, useEffect, useState } from "react";
import type { Profile } from "./contracts";

const KEY = "pitchside.profile.v1";

export const DEFAULT_PROFILE: Profile = { mode: "casual", language: "en", favorite_club: "LAG" };

// The Three Fans view: one goal, three stories.
export const DEMO_PROFILES: Profile[] = [
  { mode: "analyst", language: "en", focus_metric: "xg" },
  { mode: "casual", language: "pcm", favorite_club: "LAG", focus_metric: "possession" },
  { mode: "player_cam", language: "yo", favorite_club: "LAG", favorite_player: "LAG-09", focus_metric: "top_speed" },
];

export const MODES: { id: Profile["mode"]; title: string; blurb: string }[] = [
  { id: "analyst", title: "Analyst", blurb: "xG, PPDA, pass difficulty. Dense and tactical." },
  { id: "casual", title: "Casual fan", blurb: "Short, punchy, no jargon." },
  { id: "player_cam", title: "Player Cam", blurb: "Everything through one player." },
  { id: "kids", title: "Kids", blurb: "Simple and upbeat." },
];

export const LANGUAGES: { id: Profile["language"]; name: string }[] = [
  { id: "en", name: "English" },
  { id: "pcm", name: "Pidgin" },
  { id: "yo", name: "Yorùbá" },
  { id: "fr", name: "Français" },
  { id: "es", name: "Español" },
];

export const FOCUS_METRICS: { id: NonNullable<Profile["focus_metric"]>; name: string }[] = [
  { id: "possession", name: "Possession" },
  { id: "xg", name: "xG" },
  { id: "shot_speed", name: "Shot speed" },
  { id: "top_speed", name: "Top speed" },
  { id: "distance", name: "Distance" },
  { id: "pass_accuracy", name: "Pass accuracy" },
  { id: "momentum", name: "Control vs Chaos" },
];

function read(): Profile | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Profile) : null;
  } catch {
    return null;
  }
}

export function useProfile(): [Profile | null, (p: Profile) => void, boolean] {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    setProfile(read());
    setLoaded(true);
  }, []);
  const save = useCallback((p: Profile) => {
    setProfile(p);
    try {
      window.localStorage.setItem(KEY, JSON.stringify(p));
    } catch {
      /* private mode: keep it in memory */
    }
  }, []);
  return [profile, save, loaded];
}
