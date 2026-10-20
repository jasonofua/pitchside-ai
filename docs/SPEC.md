# Pitchside AI — Build Spec for Claude

Oct 19, 2026 · @Neuro6

## Overview

Pitchside AI is a multi-agent system that watches a synthetic football match as it happens and turns raw events into live, explained, personalized match intelligence. It must be submitted by **Oct 27, 11:59 pm PT (Oct 28, 7:59 am Lagos)**; aim to submit on Oct 27 evening Lagos time.

**What it does, end to end:**

1. **Ingest** — our own synthetic match engine streams fictional match events (passes, shots, tackles, pressure, possession changes) in real time.
2. **Interpret** — a deterministic stats engine turns events into stats: possession, pass accuracy and difficulty, shot speed, distance covered, xG, and a Control vs Chaos momentum index.
3. **Explain** — specialist AI agents detect key moments and explain *why* they matter, grounded in the stats.
4. **Render** — a Producer agent emits timed, machine-readable overlay cards that sit on a live 2D match view.
5. **Personalize** — a Fan Lens agent reshapes the same insight for each viewer: Analyst, Casual Fan, Player Cam, favorite club, and language (English, Pidgin, Yoruba, French, Spanish).

**The demo moment:** one goal, shown three ways side by side — the analyst's tactical breakdown, a casual fan's line in English, and the scorer's Player Cam card.

**Prize targets:** Grand Prize, plus Best Multi-Agent System as the primary category (Azure Cloud Native as a secondary fit). Each judging criterion is 20%, so the build must be balanced: real agents, real Azure deployment, polished UI, and a tight 2-minute video.

**Hard rules the build must respect:**

- All code written after Sep 29, 2026, in a **public** GitHub repo.
- Synthetic data only. Fictional clubs, players, and crests; no real league marks, club names, player names, or copyrighted music anywhere (code, UI, video).
- A working, free-to-access demo URL for judges until Nov 10.
- English for all submission materials.

## Architecture

Events flow left to right through deterministic services into one source of truth, the Match Stats MCP server; seven agents read from it, and only Fact-Checked cards reach viewers.

&#91;embedded content: Pitchside AI architecture · data tier, agent workflow, delivery\]

Every service runs as its own Azure Container App, scaled by Event Hubs load and to zero when idle. If an agent fails or runs slow, Producer releases a fallback card so the screen never goes blank; all agent calls are traced into App Insights.

## Synthetic match engine

We build our own simulator so the demo is reproducible and can be steered into dramatic moments on cue. It is a seeded, possession-based Markov model in Python that emits events on a match clock at 1x, 5x, or 20x speed.

**Fictional world (`data/world.json`):** two to four invented clubs (e.g. Lagos Lions, Harbour City FC, Northbank Rovers), 18-player squads with invented names, positions, shirt numbers, and attribute ratings (pace, passing, finishing, pressing, stamina). Crests are simple generated SVG shapes.

**Event schema (`schemas/event.schema.json`, JSON Schema + Pydantic model):**

| Field | Type | Notes |
| --- | --- | --- |
| event\_id | string (ULID) | sortable, unique |
| match\_id | string |  |
| seq | int | strictly increasing per match |
| clock\_ms | int | match clock; period resets not needed |
| period | int | 1 or 2 |
| type | enum | pass, carry, shot, tackle, interception, pressure, foul, card, substitution, goal, possession\_change, out\_of\_play, kickoff, period\_end |
| team\_id, player\_id | string |  |
| x, y / end\_x, end\_y | float, metres | pitch 105 x 68, attacking left to right |
| outcome | enum | complete, incomplete, saved, blocked, off\_target, won, lost |
| under\_pressure | bool |  |
| ball\_speed\_kmh | float | passes and shots |
| recipient\_id, body\_part, card\_color | optional |  |

**Tracking frames (`tracking` topic, 5 Hz):** `{match_id, clock_ms, players:[{player_id, x, y}], ball:{x, y}}`. Used for player speed, distance covered, and the 2D pitch animation. Generate with simple steering toward role-based target positions plus noise.

**Scenario scripts (`sim/scenarios/*.yaml`):** inject story beats at set minutes so every demo run has a narrative arc:

- `comeback` — underdog trails 0–2 at 60', scores at 71' and 88'
- `red_card` — straight red at 34', momentum collapse then recovery
- `pressing_collapse` — a high-press team tires after 65', turnovers spike
- `late_winner` — tight match, winner at 90+2'

**Interface:** `python -m sim run --scenario comeback --seed 42 --speed 5 --sink eventhubs|ws|stdout|file`. Also export full matches to `data/matches/*.jsonl` so they double as a published synthetic dataset (counts toward the "data innovation" criterion).

**Acceptance checks:** realistic totals per match (about 800–1,100 passes, 20–30 shots, 2–4 goals on average over 50 seeded runs), no events out of pitch bounds, monotonic `seq`, and schema validation in CI.

## Agents

Numbers come from deterministic code; language comes from agents. Every agent reads stats through one MCP server and never invents a figure — a Fact Checker blocks any output whose numbers don't match match state. Build agents with **Microsoft Agent Framework (Python)**, models deployed in a **Microsoft Foundry** project (one capable chat model for analysis and narration, one small fast model for moment triage and rewrites), and orchestrate them as an Agent Framework workflow.

**Non-agent services (deterministic, unit-tested):**

- **Ingestor** — consumes Event Hubs, validates schema, de-duplicates by `event_id`, appends to the event log.
- **Stats Engine** — rolling aggregates per team and player: possession %, pass accuracy, pass distance, pass difficulty (0–100 from distance, pressure, line-breaking, receiver tightness), ball and shot speed, distance covered, sprint count, simple xG (distance + angle logistic model), PPDA, and the **Control vs Chaos index** (blend of possession stability, turnover rate, pressure events, and tempo over a 5-minute window, scaled −100 to +100). Emits threshold triggers (speed > 32 km/h, pass difficulty > 80, xG > 0.3).
- **Match Stats MCP server** — exposes tools: `get_match_state`, `get_team_stats(window)`, `get_player_stats(player_id, window)`, `get_events(since, types)`, `get_momentum(window)`, `compare_periods`. All agents use this; it is the shared state.

**Agents:**

| Agent | Model | Trigger | Output |
| --- | --- | --- | --- |
| Moment Detector | small | each trigger or every 30 s of match time | `Moment{id, clock, type, importance 0–1, evidence_event_ids}` |
| Tactical Analyst | large | Moment importance ≥ 0.5, momentum swing ≥ 30 | `Insight{headline, why_it_matters, stats_cited[]}` |
| Narrator | large | Insight, goal, card, half-time, full-time | commentary line, half-time story, full-time recap |
| Fan Lens | small | each Insight × each active profile | profile-specific rewrite: depth, tone, club bias, player focus |
| Localizer | small | each Fan Lens output | same card in the profile's language (en, pcm, yo, fr, es) |
| Fact Checker | small + code | every card before release | pass, or reject with the mismatched figure |
| Producer | large (planning) + code (timing) | all approved cards | overlay timeline: priority, slot, ttl, de-duplication |

**Orchestration flow:** Moment Detector → Tactical Analyst → Narrator → Fan Lens (fan-out per profile) → Localizer → Fact Checker → Producer → WebSocket. Agents hand off typed Pydantic messages; every handoff carries `trace_id` and `moment_id`.

**Failure handling (judges score this for the multi-agent prize):**

- Fact Checker rejects → one regeneration with the correction in context → else fall back to a stats-only template card.
- Any model call over 4 s → template card now, upgraded card replaces it if it lands within ttl.
- Foundry errors or rate limits → circuit breaker per agent; Producer keeps rendering stats-only cards so the screen never goes blank.
- Stale insight (match clock moved past ttl) → dropped by Producer, logged.
- Show this live in the demo: a "chaos switch" in the admin panel that kills the Narrator for 20 s and shows graceful fallback.

**Latency budget:** event → stat overlay under 1 s; event → explained insight under 6 s at 1x speed.

**Optional, if time allows:** expose Fan Lens over **A2A** so another app (e.g. a chat bot) can ask "explain the last 10 minutes for a casual fan in Pidgin"; add a 1-minute audio recap with Azure AI Speech where a voice exists for the chosen language.

## Frontend

One Next.js app with a broadcast-style match screen as the hero, plus a split-screen "three fans" view built purely for the demo video.

**Views:**

- **Match screen** — 2D pitch animated from tracking frames, scoreboard and clock, a lower-third overlay rail, a corner stat bug, a momentum ribbon (Control vs Chaos) across the bottom, and player name tags that pop with speed and distance when thresholds trigger.
- **Three Fans view** — the same match running in three panes: Analyst (English), Casual Fan (Pidgin), Player Cam (Yoruba or French). This is the money shot for the video.
- **Analyst dashboard** — pass network, shot map with xG, pass difficulty histogram, momentum timeline with clickable moments that show the agent's explanation and the evidence events.
- **Recap page** — auto-generated full-time recap: headline, 5 key moments, player of the match, stat cards, language switch, and a "copy as JSON" button for broadcast tooling.
- **Admin / Director panel** — start a scenario, set speed, toggle the chaos switch, watch the live agent trace (which agent ran, latency, fact-check verdicts).

**Personalization profile:** `{mode: analyst|casual|player_cam|kids, language, favorite_club, favorite_player, focus_metric}`. Set through a 20-second onboarding sheet; stored in local state, sent with the WebSocket subscription.

| Mode | What changes |
| --- | --- |
| Analyst | dense cards, xG and PPDA, tactical language, more cards per minute |
| Casual | short punchy lines, no jargon, emotional framing, fewer cards |
| Player Cam | every card filtered to one player: touches, distance, heat map, milestone pings |
| Favorite club | tone leans to your club; rival goals framed honestly but briefly |
| Focus metric | one persistent bug for the metric the viewer chose (e.g. shot speed) |

**Overlay contract (`schemas/overlay.schema.json`)** — what the Producer emits and what any broadcast renderer could consume:

`{overlay_id, match_id, clock_ms, slot: lower_third|corner_bug|player_tag|full_card|ticker, priority 1–5, ttl_ms, audience_profile_hash, lang, title, body, stats:[{label, value, unit}], evidence_event_ids[], trace_id}`

**Look:** dark broadcast theme, one accent colour, large type readable on a phone-recorded demo, motion via Framer Motion. No real league styling.

## Repo layout and stack

One public monorepo, deployable with a single `azd up`, runnable locally with `docker compose up` and no Azure account (local mode swaps Event Hubs for an in-process queue and Foundry for a mock or any OpenAI-compatible endpoint).

```
pitchside-ai/
├─ README.md              # pitch, architecture image, quick start, demo link
├─ CLAUDE.md              # rules for Claude Code (see kickoff prompt)
├─ azure.yaml             # azd project
├─ infra/                 # Bicep: Container Apps env, Event Hubs, Cosmos DB,
│                         # Web PubSub, App Insights, Key Vault, Foundry refs
├─ schemas/               # event, tracking, overlay JSON Schemas
├─ data/                  # world.json, exported synthetic matches
├─ services/
│  ├─ sim/                # synthetic match engine (Python)
│  ├─ ingestor/           # Event Hubs consumer → event log
│  ├─ stats/              # stats engine + Control vs Chaos index
│  ├─ mcp_stats/          # Match Stats MCP server
│  ├─ agents/             # Agent Framework agents + workflow
│  │  ├─ moment_detector.py
│  │  ├─ tactical_analyst.py
│  │  ├─ narrator.py
│  │  ├─ fan_lens.py
│  │  ├─ localizer.py
│  │  ├─ fact_checker.py
│  │  ├─ producer.py
│  │  ├─ prompts/
│  │  └─ workflow.py
│  └─ gateway/            # FastAPI: REST + WebSocket fan-out, admin API
├─ web/                   # Next.js frontend
├─ evals/                 # agent eval sets: fact accuracy, tone, language
├─ tests/                 # pytest + Playwright smoke test
└─ .github/workflows/     # CI: lint, test, schema check, deploy
```

| Layer | Choice |
| --- | --- |
| Language | Python 3.12 (uv, ruff, mypy, pytest); TypeScript strict (pnpm) |
| Agents | Microsoft Agent Framework (Python), workflows for orchestration |
| Models | Microsoft Foundry project: one large and one small chat deployment |
| Tools / shared state | MCP server over the stats engine; Cosmos DB for event log, match state, moments |
| Streaming | Azure Event Hubs (events, tracking); Azure Web PubSub to browsers |
| Compute | Azure Container Apps, one app per service, KEDA scaling on Event Hubs |
| Frontend | Next.js + Tailwind + Framer Motion, hosted on Azure Static Web Apps |
| Ops | Application Insights with OpenTelemetry traces across agents; Key Vault; managed identity |
| Dev tooling | GitHub Copilot / Claude Code, GitHub Actions, azd |

**Conventions:** every agent prompt lives in `prompts/` as a versioned file; every agent has an eval in `evals/`; no secrets in the repo (managed identity in Azure, `.env.example` locally); MIT licence; conventional commits.

## 8-day build plan

The rule: a working end-to-end slice by Day 3, then widen. Day 8 is for the video and submission only, with a hard stop at 8 pm Lagos on Oct 27.

### Day 1 — Tue Oct 20: foundations

- [ ] Create public repo, licence, README skeleton, `CLAUDE.md`, CI (ruff, mypy, pytest) — all done locally; public GitHub repo still to create
- [x] Write `event`, `tracking`, `overlay` schemas + Pydantic models
- [x] Build `world.json` with fictional clubs and squads
- [x] Simulator v1: possession Markov model, events + 5 Hz tracking, seed, speed, stdout/file sink
- [ ] Provision Foundry project and two model deployments; confirm keys and quotas work — needs the Azure account owner

### Day 2 — Wed Oct 21: numbers

- [x] Stats engine with unit tests for every metric, including pass difficulty and xG
- [x] Control vs Chaos index over a 5-minute window, with threshold triggers
- [x] Match Stats MCP server exposing the six tools
- [x] Local bus (in-process) + Ingestor; Cosmos DB emulator or SQLite in local mode
- [x] Scenario scripts: comeback and late winner (plus red_card and pressing_collapse)

### Day 3 — Thu Oct 22: first agents, first slice

- [x] Agent Framework workflow skeleton with typed messages and trace ids
- [x] Moment Detector, Tactical Analyst, Narrator working through the MCP server
- [x] Gateway WebSocket pushing raw overlay JSON
- [x] **Milestone:** one simulated match produces explained moments end to end in a terminal (`scripts/explain_match.py`)

### Day 4 — Fri Oct 23: the rest of the crew

- [x] Fan Lens (4 modes), Localizer (en, pcm, yo, fr, es), Fact Checker, Producer
- [x] Failure handling: timeouts, template fallback, circuit breaker, chaos switch
- [x] Evals: 30 seeded moments checked for number accuracy and language quality — native-speaker review of `evals/results/language_samples.md` still needed (owner)

### Day 5 — Sat Oct 24: the screen

- [ ] Next.js match screen: 2D pitch from tracking, scoreboard, overlay rail, stat bug, momentum ribbon, player tags
- [ ] Onboarding sheet for the personalization profile
- [ ] **Milestone:** live match in the browser with agent cards appearing in sync

### Day 6 — Sun Oct 25: personalization and recap

- [ ] Three Fans split view
- [ ] Player Cam mode and focus-metric bug
- [ ] Analyst dashboard and full-time Recap page with JSON export
- [ ] Director panel with live agent trace

### Day 7 — Mon Oct 26: Azure and hardening

- [ ] Bicep + `azd up`: Container Apps, Event Hubs, Cosmos DB, Web PubSub, Static Web Apps, App Insights, Key Vault, managed identity
- [ ] Deploy, run three full matches at 5x, fix what breaks
- [ ] OpenTelemetry traces visible in App Insights (screenshot for README)
- [ ] Public demo URL with a "Start demo match" button that needs no login

### Day 8 — Tue Oct 27: ship

- [ ] Record and edit the 2-minute video; upload to YouTube (public or unlisted-but-accessible)
- [ ] Final README: pitch, architecture image, Microsoft tech list, how to run, how to test, video link
- [ ] Write the project description on the hackathon site and submit by 8 pm Lagos
- [ ] Open the repo and demo URL in a private browser window to confirm judges can reach both

**If you fall behind, cut in this order:** audio recap → A2A → Analyst dashboard → Kids mode → one language. Never cut the Three Fans view, the Fact Checker, or the Azure deployment.

## Demo video, submission and risks

Judges may stop at 2:00, so the strongest moment comes before 1:00.

**Video script (1:55 total):**

| Time | Shot | Voice-over point |
| --- | --- | --- |
| 0:00–0:10 | Match screen, a goal lands | "Every fan saw the same goal. Pitchside AI tells each one a different story." |
| 0:10–0:40 | Three Fans split view on that goal | Analyst breakdown, Pidgin casual line, Player Cam card, all live |
| 0:40–1:05 | Agent trace in the Director panel | Seven agents, MCP shared state, Fact Checker rejecting a wrong number |
| 1:05–1:20 | Chaos switch: Narrator killed | Screen keeps working on fallback cards, recovers on its own |
| 1:20–1:40 | Architecture diagram + Azure portal / App Insights trace | Foundry, Agent Framework, Container Apps, Event Hubs |
| 1:40–1:55 | Recap page, language switch, JSON export | "Ready for studio, broadcast and streaming, in any language." |

Use royalty-free music or none. Record at 1080p, large browser zoom.

**Submission checklist:**

- [ ] Public GitHub repo URL, MIT licence, clean README
- [ ] Demo video under 2:00, public link
- [ ] Live demo URL, no login (or credentials in testing notes), up until Nov 10
- [ ] Elevator pitch naming Microsoft tech: Foundry, Agent Framework, MCP, Container Apps, Event Hubs, Cosmos DB, Web PubSub, App Insights, GitHub Copilot/Actions
- [ ] Category selected: Best Multi-Agent System
- [ ] No real club, league, or player names anywhere
- [ ] Azure budget alert set so the demo isn't shut off by a billing surprise

**Risks and fallbacks:**

- **Model quota or latency spikes** — keep the small model for fan-out agents; cache rewrites per profile; template fallback keeps the screen alive.
- **Azure deploy eats Day 7** — deploy a hello-world Container App on Day 1 to shake out subscription, region, and quota issues early.
- **Pidgin/Yoruba quality** — get a native speaker to review 20 samples on Day 4; tune the Localizer prompt with their corrections as few-shot examples.
- **Demo URL costs while judging** — scale-to-zero on Container Apps; matches run only when a visitor presses Start.
- **Scope creep** — follow the cut order in the build plan.

## Kickoff prompt for Claude Code

Export this doc as Markdown, save it in the repo as `docs/SPEC.md`, then start Claude Code in the repo with the prompt below. Run one day's checklist per session and start each new session with "Continue with Day N of docs/SPEC.md."

```markdown
You are the lead engineer on Pitchside AI, our entry to the Microsoft "Inside the Game" hackathon. The full spec is in docs/SPEC.md — read it completely before writing code.

First, create CLAUDE.md with these standing rules, then follow them in every session:
1. Follow docs/SPEC.md. If you need to deviate, explain why and record it in docs/DECISIONS.md.
2. Numbers come only from deterministic code (services/stats). Agents never compute or invent statistics; they read them through the Match Stats MCP server.
3. Fictional data only: no real clubs, leagues, players, crests, or broadcaster marks anywhere in code, data, UI, or docs.
4. Python 3.12 with uv, ruff, mypy, pytest. TypeScript strict with pnpm. Pydantic models generated from the JSON Schemas in /schemas.
5. Every metric has a unit test. Every agent has a prompt file in services/agents/prompts and an eval in /evals.
6. Local mode must run with `docker compose up` and no Azure account; Azure mode deploys with `azd up`. Never commit secrets; use managed identity in Azure and .env.example locally.
7. Use Microsoft Agent Framework (Python) for agents and workflows, and Microsoft Foundry model deployments via env vars FOUNDRY_ENDPOINT, MODEL_LARGE, MODEL_SMALL. If you are unsure of a current SDK API, check the official docs or package source before writing code — do not guess.
8. Work in small commits with conventional messages. At the end of each session, update the checklist in docs/SPEC.md and write a short docs/PROGRESS.md entry: done, broken, next.

Now do Day 1 of the build plan. Start by proposing the exact file tree you will create, then build it. Finish with the simulator streaming a seeded match to stdout and all tests passing.
```

**Tips for running it:** keep sessions to one day's scope; ask Claude to run the simulator and tests itself before saying a task is done; review the agent prompts by hand, since tone in Pidgin and Yoruba is where human judgment matters most.
