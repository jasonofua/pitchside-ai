"""Phrase bank for the offline mock model (local mode without any LLM).

The mock Fan Lens writes cards from these phrases and records what it rendered, so the
mock Localizer can re-render the same phrases in the viewer's language. Real models
replace all of this in Azure mode. Pidgin and Yoruba await native-speaker review.
"""

from __future__ import annotations

from agents.i18n import Lang

# Kinds grouped for body text.
GROUP = {
    "goal": "goal",
    "big_chance": "chance",
    "card": "card",
    "speed_burst": "physical",
    "hard_pass": "physical",
    "momentum_swing": "flow",
    "spell": "flow",
    "half_time": "period",
    "full_time": "period",
}

BODIES: dict[str, dict[Lang, str]] = {
    # analyst
    "analyst_goal": {
        "en": "{team} now have {shots} shots and {xg} xG. {player} finishes a move worth {shot_xg} xG.",
        "pcm": "{team} don shoot {shots} times, {xg} xG. {player} finish the move wey get {shot_xg} xG.",
        "yo": "{team} ti gbá ìgbá {shots}, {xg} xG. {player} parí ìkọlù tó ní {shot_xg} xG.",
        "fr": "{team} compte {shots} tirs pour {xg} xG. {player} conclut une action à {shot_xg} xG.",
        "es": "{team} suma {shots} tiros y {xg} xG. {player} culmina una jugada de {shot_xg} xG.",
    },
    "analyst_chance": {
        "en": "A {shot_xg} xG chance for {team}, who have {xg} xG from {shots} shots.",
        "pcm": "Chance of {shot_xg} xG for {team}; dem get {xg} xG from {shots} shots.",
        "yo": "Àǹfààní {shot_xg} xG fún {team}; wọ́n ní {xg} xG láti inú ìgbá {shots}.",
        "fr": "Occasion à {shot_xg} xG pour {team}, qui totalise {xg} xG sur {shots} tirs.",
        "es": "Ocasión de {shot_xg} xG para {team}, que suma {xg} xG en {shots} tiros.",
    },
    "analyst_card": {
        "en": "{team} have committed {fouls} fouls; their PPDA is {ppda}.",
        "pcm": "{team} don foul {fouls} times; their PPDA na {ppda}.",
        "yo": "{team} ti ṣe àṣìṣe {fouls}; PPDA wọn jẹ́ {ppda}.",
        "fr": "{team} en est à {fouls} fautes ; PPDA de {ppda}.",
        "es": "{team} acumula {fouls} faltas; su PPDA es {ppda}.",
    },
    "analyst_physical": {
        "en": "{player}: {touches} touches, {distance} km covered, top speed {top_speed} km/h.",
        "pcm": "{player}: {touches} touches, e don run {distance} km, top speed {top_speed} km/h.",
        "yo": "{player}: ìgbà {touches} tó kan bọ́ọ̀lù, {distance} km, ìyára gíga jùlọ {top_speed} km/h.",
        "fr": "{player} : {touches} ballons, {distance} km parcourus, pointe à {top_speed} km/h.",
        "es": "{player}: {touches} toques, {distance} km recorridos, punta de {top_speed} km/h.",
    },
    "analyst_flow": {
        "en": "Control vs Chaos is at {index}; {team} hold {poss}% of the ball over the last 5 minutes.",
        "pcm": "Control vs Chaos na {index}; {team} get {poss}% of the ball for last 5 minutes.",
        "yo": "Control vs Chaos jẹ́ {index}; {team} ní {poss}% bọ́ọ̀lù ní ìṣẹ́jú márùn-ún tó kọjá.",
        "fr": "Control vs Chaos à {index} ; {team} a {poss} % du ballon sur les 5 dernières minutes.",
        "es": "Control vs Chaos en {index}; {team} tiene el {poss}% del balón en los últimos 5 minutos.",
    },
    "analyst_period": {
        "en": "xG {home_xg} to {away_xg}; pass accuracy {home_acc}% to {away_acc}%.",
        "pcm": "xG {home_xg} to {away_xg}; pass wey land {home_acc}% to {away_acc}%.",
        "yo": "xG {home_xg} sí {away_xg}; ìpéye ìfiránṣẹ́ {home_acc}% sí {away_acc}%.",
        "fr": "xG {home_xg} à {away_xg} ; passes réussies {home_acc} % à {away_acc} %.",
        "es": "xG {home_xg} a {away_xg}; precisión de pase {home_acc}% a {away_acc}%.",
    },
    # casual
    "casual_goal": {
        "en": "What a moment for {team}!",
        "pcm": "Na so! {team} don do am!",
        "yo": "Ìdùnnú ńlá fún {team}!",
        "fr": "Quel moment pour {team} !",
        "es": "¡Qué momento para {team}!",
    },
    "casual_goal_rival": {
        "en": "{team} strike. Time to answer back.",
        "pcm": "{team} don score o. Make we answer dem.",
        "yo": "{team} ti gbá wọlé. Àkókò láti fèsì.",
        "fr": "{team} frappe. À nous de répondre.",
        "es": "Golpea {team}. Toca responder.",
    },
    "casual_chance": {
        "en": "So close for {team}!",
        "pcm": "E remain small! {team} nearly score!",
        "yo": "Ó kù díẹ̀ fún {team}!",
        "fr": "Si près pour {team} !",
        "es": "¡Qué cerca {team}!",
    },
    "casual_card": {
        "en": "The referee has seen enough.",
        "pcm": "Referee don vex.",
        "yo": "Adájọ́ ti rí i.",
        "fr": "L'arbitre sévit.",
        "es": "El árbitro dice basta.",
    },
    "casual_physical": {
        "en": "{player} is flying today!",
        "pcm": "{player} dey fly today!",
        "yo": "{player} ń fò lónìí!",
        "fr": "{player} est intenable aujourd'hui !",
        "es": "¡{player} va volando hoy!",
    },
    "casual_flow": {
        "en": "{team} are taking over.",
        "pcm": "{team} don take over the game.",
        "yo": "{team} ti gba àkóso eré.",
        "fr": "{team} prend les commandes.",
        "es": "{team} se adueña del partido.",
    },
    "casual_period": {
        "en": "{home} {score} {away}. What a game so far.",
        "pcm": "{home} {score} {away}. This game sweet well well.",
        "yo": "{home} {score} {away}. Eré yìí dùn gan-an.",
        "fr": "{home} {score} {away}. Quel match !",
        "es": "{home} {score} {away}. ¡Vaya partido!",
    },
    # kids
    "kids_goal": {
        "en": "Goal! {team} score and the fans cheer!",
        "pcm": "Goal! {team} score and everybody dey happy!",
        "yo": "Góòlù! {team} gbá wọlé, inú àwọn olólùfẹ́ dùn!",
        "fr": "But ! {team} marque et les fans applaudissent !",
        "es": "¡Gol! ¡{team} marca y la afición aplaude!",
    },
    "kids_chance": {
        "en": "Wow, nearly a goal!",
        "pcm": "Wow, e nearly enter!",
        "yo": "Háà, ó fẹ́rẹ̀ẹ́ wọlé!",
        "fr": "Ouah, presque un but !",
        "es": "¡Uy, casi gol!",
    },
    "kids_card": {
        "en": "The referee shows a card. Play fair!",
        "pcm": "Referee show card. Make una play fair!",
        "yo": "Adájọ́ fi káàdì hàn. Ẹ ṣeré dáadáa!",
        "fr": "L'arbitre sort un carton. Fair-play !",
        "es": "El árbitro saca tarjeta. ¡Juego limpio!",
    },
    "kids_physical": {
        "en": "{player} runs super fast!",
        "pcm": "{player} dey run well well!",
        "yo": "{player} ń sáré gan-an!",
        "fr": "{player} court super vite !",
        "es": "¡{player} corre súper rápido!",
    },
    "kids_flow": {
        "en": "{team} have the ball a lot right now.",
        "pcm": "{team} dey hold ball well well now.",
        "yo": "{team} ní bọ́ọ̀lù púpọ̀ báyìí.",
        "fr": "{team} a souvent le ballon en ce moment.",
        "es": "{team} tiene mucho el balón ahora.",
    },
    "kids_period": {
        "en": "Time for a break! {home} {score} {away}.",
        "pcm": "Time for small rest! {home} {score} {away}.",
        "yo": "Àkókò ìsinmi! {home} {score} {away}.",
        "fr": "C'est la pause ! {home} {score} {away}.",
        "es": "¡Hora de descansar! {home} {score} {away}.",
    },
    # player cam
    "cam_involved": {
        "en": "{player} in the thick of it: {touches} touches, {distance} km so far.",
        "pcm": "{player} dey everywhere: {touches} touches, {distance} km so far.",
        "yo": "{player} wà níbẹ̀: ìgbà {touches} tó kan bọ́ọ̀lù, {distance} km títí di báyìí.",
        "fr": "{player} au cœur de l'action : {touches} ballons, {distance} km.",
        "es": "{player} en plena acción: {touches} toques, {distance} km.",
    },
    "cam_watching": {
        "en": "{player} keeps working: {distance} km covered, top speed {top_speed} km/h.",
        "pcm": "{player} still dey work: {distance} km, top speed {top_speed} km/h.",
        "yo": "{player} ń ṣiṣẹ́ lọ: {distance} km, ìyára gíga jùlọ {top_speed} km/h.",
        "fr": "{player} ne lâche rien : {distance} km, pointe à {top_speed} km/h.",
        "es": "{player} no para: {distance} km, punta de {top_speed} km/h.",
    },
}

# English-only lines for the mock Tactical Analyst and Narrator (their output feeds the Fan
# Lens and the recap, which are localised separately).
HEADLINES = {
    "goal": "{team} make their pressure count",
    "big_chance": "{team} carve out a clear chance",
    "card": "Discipline costs {team}",
    "speed_burst": "{player} stretches the play",
    "hard_pass": "{player} breaks the lines",
    "momentum_swing": "The match tilts towards {team}",
    "spell": "{team} take control of the ball",
    "half_time": "Half time: {home} {score} {away}",
    "full_time": "Full time: {home} {score} {away}",
}
WHY = {
    "goal": (
        "{team} have {shots} shots and {xg} xG in the match, and {recent_poss}% of the ball "
        "in the last 10 minutes. Watch whether {opp} change shape to chase it."
    ),
    "big_chance": (
        "{team} have produced {xg} xG from {shots} shots. Chances like this decide tight "
        "games; {opp} need to protect the box better."
    ),
    "card": (
        "{team} have committed {fouls} fouls. With a PPDA of {ppda}, their pressing has to "
        "stay aggressive without another booking."
    ),
    "speed_burst": (
        "{player} has covered {distance} km with {sprints} sprints. That pace is how {team} "
        "turn defence into attack."
    ),
    "hard_pass": (
        "{player} completes {accuracy}% of passes. Line-breaking balls like this one open "
        "space between {opp}'s lines."
    ),
    "momentum_swing": (
        "The Control vs Chaos index is {index}, a swing of {swing} points in 5 minutes. "
        "{team} have {recent_poss}% of the ball in the last 10 minutes."
    ),
    "spell": (
        "{team} have {recent_poss}% of the ball in the last 10 minutes and a pass accuracy of "
        "{accuracy}%. {opp} are being pinned back."
    ),
    "half_time": (
        "At the break xG is {home_xg} to {away_xg} and possession {home_poss}% to {away_poss}%."
    ),
    "full_time": (
        "Over the match xG finished {home_xg} to {away_xg} and possession {home_poss}% to "
        "{away_poss}%."
    ),
}
LINES = {
    "goal": "{player} scores for {team}! {home} {score} {away}.",
    "big_chance": "Huge chance for {team}! {player} so nearly made it count.",
    "card": "{player} goes into the book for {team}.",
    "speed_burst": "{player} tears down the pitch at {top_speed} km/h!",
    "hard_pass": "Wonderful pass from {player}, threaded through the lines.",
    "momentum_swing": "The tide is turning: {team} are on top now.",
    "spell": "{team} keep the ball and keep asking questions.",
    "half_time": "That's half time: {home} {score} {away}.",
    "full_time": "Full time! {home} {score} {away}.",
}
