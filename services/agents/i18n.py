"""Fixed phrases in the five supported languages, used by template cards.

en = English, pcm = Nigerian Pidgin, yo = Yoruba, fr = French, es = Spanish. Pidgin and
Yoruba lines are first drafts awaiting the native-speaker review listed in the build plan
(docs/PROGRESS.md); edit them here and the evals in evals/language pick them up.
"""

from __future__ import annotations

from typing import Literal

Lang = Literal["en", "pcm", "yo", "fr", "es"]
LANGS: tuple[Lang, ...] = ("en", "pcm", "yo", "fr", "es")

PHRASES: dict[str, dict[Lang, str]] = {
    # ---------------------------------------------------------------- titles
    "goal": {
        "en": "GOAL! {team}",
        "pcm": "GOAL! {team} don score!",
        "yo": "GÓÒLÙ! {team}",
        "fr": "BUT ! {team}",
        "es": "¡GOL! {team}",
    },
    "goal_body": {
        "en": "{player} scores in the {minute}. {home} {score} {away}",
        "pcm": "{player} put am for net for {minute}. {home} {score} {away}",
        "yo": "{player} gbá a wọlé ní ìṣẹ́jú {minute}. {home} {score} {away}",
        "fr": "{player} marque à la {minute}. {home} {score} {away}",
        "es": "{player} marca en el {minute}. {home} {score} {away}",
    },
    "yellow": {
        "en": "Yellow card: {player}",
        "pcm": "Yellow card for {player}",
        "yo": "Káàdì ofeefee fún {player}",
        "fr": "Carton jaune : {player}",
        "es": "Tarjeta amarilla: {player}",
    },
    "second_yellow": {
        "en": "Second yellow: {player} is off",
        "pcm": "Second yellow! {player} don comot",
        "yo": "Káàdì ofeefee kejì: {player} ti jáde",
        "fr": "Deuxième jaune : {player} expulsé",
        "es": "Segunda amarilla: {player}, expulsado",
    },
    "red": {
        "en": "Red card: {player} is off",
        "pcm": "Red card! {player} don comot for field",
        "yo": "Káàdì pupa: {player} ti jáde",
        "fr": "Carton rouge : {player} expulsé",
        "es": "Tarjeta roja: {player}, expulsado",
    },
    "card_body": {
        "en": "{team}, {minute}",
        "pcm": "{team}, {minute}",
        "yo": "{team}, ìṣẹ́jú {minute}",
        "fr": "{team}, {minute}",
        "es": "{team}, {minute}",
    },
    "speed": {
        "en": "{player} hits {value} km/h",
        "pcm": "{player} dey fly: {value} km/h",
        "yo": "{player} ń sáré: {value} km/h",
        "fr": "{player} flashé à {value} km/h",
        "es": "{player} vuela: {value} km/h",
    },
    "speed_body": {
        "en": "Sprinting above 32 km/h",
        "pcm": "E pass 32 km/h for this run",
        "yo": "Ó sáré ju 32 km/h lọ",
        "fr": "Sprint au-delà de 32 km/h",
        "es": "Sprint por encima de 32 km/h",
    },
    "xg": {
        "en": "Big chance: {value} xG",
        "pcm": "Big chance: {value} xG",
        "yo": "Àǹfààní ńlá: {value} xG",
        "fr": "Grosse occasion : {value} xG",
        "es": "Ocasión clara: {value} xG",
    },
    "xg_body": {
        "en": "{player} ({team}), {outcome}",
        "pcm": "{player} ({team}), {outcome}",
        "yo": "{player} ({team}), {outcome}",
        "fr": "{player} ({team}), {outcome}",
        "es": "{player} ({team}), {outcome}",
    },
    "pass_difficulty": {
        "en": "Pass difficulty {value}/100",
        "pcm": "Correct pass! Difficulty {value}/100",
        "yo": "Ìfiránṣẹ́ tó le: {value}/100",
        "fr": "Passe de difficulté {value}/100",
        "es": "Pase de dificultad {value}/100",
    },
    "pass_difficulty_body": {
        "en": "{player} finds a team-mate through traffic",
        "pcm": "{player} find im paddy for inside crowd",
        "yo": "{player} rí ẹlẹgbẹ́ rẹ̀ láàrin àwọn alátakò",
        "fr": "{player} trouve un partenaire dans la densité",
        "es": "{player} encuentra a un compañero entre líneas",
    },
    "momentum": {
        "en": "Momentum swing: {value} pts",
        "pcm": "Game don turn: {value} pts",
        "yo": "Ìyípadà nínú eré: {value} pts",
        "fr": "Bascule du match : {value} pts",
        "es": "Cambio de inercia: {value} pts",
    },
    "momentum_body_control": {
        "en": "The match is settling: Control vs Chaos at {index}",
        "pcm": "Game don calm small: Control vs Chaos na {index}",
        "yo": "Eré ti ń rọlẹ̀: Control vs Chaos jẹ́ {index}",
        "fr": "Le match se pose : Control vs Chaos à {index}",
        "es": "El partido se calma: Control vs Chaos en {index}",
    },
    "momentum_body_chaos": {
        "en": "The match is opening up: Control vs Chaos at {index}",
        "pcm": "Wahala don start for field: Control vs Chaos na {index}",
        "yo": "Eré ti ń gbóná: Control vs Chaos jẹ́ {index}",
        "fr": "Le match s'emballe : Control vs Chaos à {index}",
        "es": "El partido se rompe: Control vs Chaos en {index}",
    },
    "half_time": {
        "en": "Half time: {home} {score} {away}",
        "pcm": "Half time: {home} {score} {away}",
        "yo": "Ìdajì àkókò: {home} {score} {away}",
        "fr": "Mi-temps : {home} {score} {away}",
        "es": "Descanso: {home} {score} {away}",
    },
    "full_time": {
        "en": "Full time: {home} {score} {away}",
        "pcm": "Full time: {home} {score} {away}",
        "yo": "Òpin ìdíje: {home} {score} {away}",
        "fr": "Fin du match : {home} {score} {away}",
        "es": "Final: {home} {score} {away}",
    },
    "period_body": {
        "en": "Possession {home_poss}% to {away_poss}%, shots {home_shots} to {away_shots}",
        "pcm": "Ball possession {home_poss}% to {away_poss}%, shots {home_shots} to {away_shots}",
        "yo": "Ìní bọ́ọ̀lù {home_poss}% sí {away_poss}%, ìgbá {home_shots} sí {away_shots}",
        "fr": "Possession {home_poss} % à {away_poss} %, tirs {home_shots} à {away_shots}",
        "es": "Posesión {home_poss}% a {away_poss}%, tiros {home_shots} a {away_shots}",
    },
    "spell": {
        "en": "{team} on top",
        "pcm": "{team} dey press dem",
        "yo": "{team} ló ń darí eré",
        "fr": "{team} prend le dessus",
        "es": "{team} domina",
    },
    "spell_body": {
        "en": "{poss}% of the ball in the last 5 minutes",
        "pcm": "Dem get {poss}% of the ball for last 5 minutes",
        "yo": "Wọ́n ní {poss}% bọ́ọ̀lù ní ìṣẹ́jú márùn-ún tó kọjá",
        "fr": "{poss} % de possession sur les 5 dernières minutes",
        "es": "{poss}% de posesión en los últimos 5 minutos",
    },
    # -------------------------------------------------------------- outcomes
    "outcome_complete": {
        "en": "scored",
        "pcm": "e enter",
        "yo": "ó wọlé",
        "fr": "but",
        "es": "gol",
    },
    "outcome_saved": {
        "en": "saved",
        "pcm": "keeper hold am",
        "yo": "olùṣọ́ góòlù gbà á",
        "fr": "arrêté",
        "es": "parada",
    },
    "outcome_blocked": {
        "en": "blocked",
        "pcm": "dem block am",
        "yo": "wọ́n dí i",
        "fr": "contré",
        "es": "bloqueado",
    },
    "outcome_off_target": {
        "en": "off target",
        "pcm": "e no enter",
        "yo": "kò wọlé",
        "fr": "non cadré",
        "es": "desviado",
    },
    # ---------------------------------------------------------------- labels
    "label_possession": {
        "en": "Possession",
        "pcm": "Ball possession",
        "yo": "Ìní bọ́ọ̀lù",
        "fr": "Possession",
        "es": "Posesión",
    },
    "label_shots": {"en": "Shots", "pcm": "Shots", "yo": "Ìgbá", "fr": "Tirs", "es": "Tiros"},
    "label_xg": {"en": "xG", "pcm": "xG", "yo": "xG", "fr": "xG", "es": "xG"},
    "label_pass_accuracy": {
        "en": "Pass accuracy",
        "pcm": "Pass wey land",
        "yo": "Ìpéye ìfiránṣẹ́",
        "fr": "Passes réussies",
        "es": "Precisión de pase",
    },
    "label_distance": {
        "en": "Distance",
        "pcm": "Distance wey e run",
        "yo": "Ìjìnnà",
        "fr": "Distance",
        "es": "Distancia",
    },
    "label_top_speed": {
        "en": "Top speed",
        "pcm": "Top speed",
        "yo": "Ìyára gíga jùlọ",
        "fr": "Vitesse max",
        "es": "Velocidad máx.",
    },
    "label_shot_speed": {
        "en": "Shot speed",
        "pcm": "Shot speed",
        "yo": "Ìyára ìgbá",
        "fr": "Vitesse de frappe",
        "es": "Velocidad del disparo",
    },
    "label_touches": {
        "en": "Touches",
        "pcm": "Touches",
        "yo": "Ìgbà tó kan bọ́ọ̀lù",
        "fr": "Ballons touchés",
        "es": "Toques",
    },
    "label_difficulty": {
        "en": "Difficulty",
        "pcm": "Difficulty",
        "yo": "Ìṣòro",
        "fr": "Difficulté",
        "es": "Dificultad",
    },
    "label_momentum": {
        "en": "Control vs Chaos",
        "pcm": "Control vs Chaos",
        "yo": "Control vs Chaos",
        "fr": "Control vs Chaos",
        "es": "Control vs Chaos",
    },
    "label_ppda": {"en": "PPDA", "pcm": "PPDA", "yo": "PPDA", "fr": "PPDA", "es": "PPDA"},
    "label_score": {
        "en": "Score",
        "pcm": "Score",
        "yo": "Àmì ayò",
        "fr": "Score",
        "es": "Marcador",
    },
}


def t(key: str, lang: Lang, **values: object) -> str:
    """Phrase `key` in `lang` with values filled in; falls back to English."""
    table = PHRASES[key]
    return (table.get(lang) or table["en"]).format(**values)
