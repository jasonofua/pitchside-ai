# Submission: Pitchside AI

Copy for the hackathon site. Category: **Best Multi-Agent System** (secondary fit: Azure
Cloud Native). Replace the demo and video links before submitting.

- **Repo:** https://github.com/jasonofua/pitchside-ai (public, MIT)
- **Live demo (no login):** <GATEWAY_URL from `azd up`>
- **Video (1:55):** <YouTube link>

## Elevator pitch (one line)

Every fan saw the same goal; Pitchside AI tells each one a different story: seven agents on
Microsoft Foundry and Agent Framework turn a live match into explained, fact-checked,
personalised overlays in English, Pidgin, Yorùbá, French and Spanish.

## Description

Live sport speaks to millions of people with one voice. Pitchside AI gives every viewer
their own: the analyst gets xG and pressing data, the casual fan a punchy line in their own
language, the Player Cam viewer everything their favourite player did, all within seconds
of the action and all checked against the numbers.

**How it works.** A synthetic match engine (our own: seeded, scriptable, fictional clubs)
streams events and 5 Hz player tracking through Azure Event Hubs. A deterministic Stats
Engine computes possession, pass difficulty, xG, PPDA, speeds, distance and a Control vs
Chaos momentum index, and raises triggers for the moments that matter. Every number lives
behind one **Model Context Protocol** server with six tools.

Seven agents built with **Microsoft Agent Framework** run as one workflow on **Microsoft
Foundry** models, reading numbers only through MCP:

1. **Moment Detector** (small model) decides what is worth explaining.
2. **Tactical Analyst** (large) explains why it matters, citing its numbers.
3. **Narrator** (large) writes the commentary, the half-time story and the recap.
4. **Fan Lens** (small) rewrites the moment for every viewer: analyst, casual, Player Cam,
   kids; favourite club and player.
5. **Localizer** (small) delivers it in English, Nigerian Pidgin, Yorùbá, French or Spanish.
6. **Fact Checker** (small model + code) blocks any card whose figures do not match match
   state; a rejected card is rewritten once, then replaced by a stats-only card.
7. **Producer** (large model + code) schedules timed overlay cards: slot, priority, time on
   screen, de-duplication, stale-card dropping.

**Built to fail gracefully.** A viewer sees a stats-only card within a second of every key
event; the explained card replaces it in place a few seconds later. Every model call has a
budget, every agent a circuit breaker, and the Director panel has a chaos switch that kills
the Narrator for 20 seconds while the screen keeps working. Every step is traced live in the
Director panel and to Application Insights through OpenTelemetry.

**What judges can try.** Open the demo URL, press *Start demo match* and pick how you watch.
Open *Three Fans* to see one match as an analyst (English), a casual Lagos Lions fan
(Pidgin) and Player Cam on the Lions' number 9 (Yorùbá) side by side. In *Director*, pull
the chaos switch or inject a wrong number and watch the Fact Checker catch it. At full time,
*Recap* has the story, five key moments, player of the match and a JSON export for
broadcast tooling.

**Engineering.** Python 3.12 (uv, ruff, mypy strict, pytest: 320+ tests), Next.js with
TypeScript strict; one set of JSON Schemas generates both the Python models and the
TypeScript types. Agent evals score every agent over 30 seeded moments (number accuracy,
mode rules, language, Fact Checker recall). Local mode runs with `docker compose up` and no
Azure account (an offline mock model drives the same Agent Framework tool-calling loop);
Azure mode deploys with `azd up` and uses managed identity everywhere.

**Synthetic data only.** Clubs, players, crests and matches are invented; the match dataset
is published in the repo.

## Microsoft technology used

Microsoft Foundry (two model deployments) · Microsoft Agent Framework (agents, workflow,
MCP tools, OpenTelemetry) · Model Context Protocol · Azure Container Apps · Azure Event Hubs
· Azure Cosmos DB · Azure Web PubSub · Azure Static Web Apps · Application Insights · Azure
Key Vault · managed identity · Azure Developer CLI · GitHub Actions · GitHub Copilot /
Claude Code.

## Testing notes for judges

- No login is needed. The demo starts matches at 5× (a match takes about 19 minutes); the
  *comeback* story has goals at about 17', 53', 71' and 88'. 20× is available for a quick
  look (about 5 minutes).
- One match can be started every 20 seconds and three can run at once, to protect the demo's
  budget; join a running match from the home page if *Start* is refused.
- Running locally: `docker compose up --build`, then http://localhost:8000. Without model
  settings the agents use the offline mock model; see the README for Foundry or any
  OpenAI-compatible endpoint.
