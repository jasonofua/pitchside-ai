// UI chrome in the five supported languages. Card text comes from the agents already
// localised; this covers labels around it. Pidgin and Yoruba await native review.
import type { Lang } from "./contracts";

type Key =
  | "live"
  | "half_time"
  | "full_time"
  | "possession"
  | "shots"
  | "xg"
  | "top_speed"
  | "shot_speed"
  | "distance"
  | "pass_accuracy"
  | "momentum"
  | "control"
  | "chaos"
  | "waiting";

const T: Record<Key, Record<Lang, string>> = {
  live: { en: "LIVE", pcm: "LIVE", yo: "Ní TÀÁRÀ", fr: "DIRECT", es: "EN VIVO" },
  half_time: { en: "Half time", pcm: "Half time", yo: "Ìdajì àkókò", fr: "Mi-temps", es: "Descanso" },
  full_time: { en: "Full time", pcm: "Full time", yo: "Òpin ìdíje", fr: "Fin du match", es: "Final" },
  possession: { en: "Possession", pcm: "Ball possession", yo: "Ìní bọ́ọ̀lù", fr: "Possession", es: "Posesión" },
  shots: { en: "Shots", pcm: "Shots", yo: "Ìgbá", fr: "Tirs", es: "Tiros" },
  xg: { en: "xG", pcm: "xG", yo: "xG", fr: "xG", es: "xG" },
  top_speed: { en: "Top speed", pcm: "Top speed", yo: "Ìyára gíga jùlọ", fr: "Vitesse max", es: "Velocidad máx." },
  shot_speed: { en: "Shot speed", pcm: "Shot speed", yo: "Ìyára ìgbá", fr: "Vitesse de frappe", es: "Velocidad del disparo" },
  distance: { en: "Distance", pcm: "Distance", yo: "Ìjìnnà", fr: "Distance", es: "Distancia" },
  pass_accuracy: { en: "Pass accuracy", pcm: "Pass wey land", yo: "Ìpéye ìfiránṣẹ́", fr: "Passes réussies", es: "Precisión de pase" },
  momentum: { en: "Control vs Chaos", pcm: "Control vs Chaos", yo: "Control vs Chaos", fr: "Control vs Chaos", es: "Control vs Chaos" },
  control: { en: "Control", pcm: "Control", yo: "Àkóso", fr: "Contrôle", es: "Control" },
  chaos: { en: "Chaos", pcm: "Wahala", yo: "Rúdurùdu", fr: "Chaos", es: "Caos" },
  waiting: { en: "Waiting for kickoff", pcm: "We dey wait for kickoff", yo: "A ń dúró de ìbẹ̀rẹ̀", fr: "En attente du coup d'envoi", es: "Esperando el saque inicial" },
};

export function tr(key: Key, lang: Lang): string {
  return T[key][lang] ?? T[key].en;
}
