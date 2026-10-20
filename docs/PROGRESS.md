# Progress

## Day 1 — foundations (worked Oct 19, a day ahead of plan)

**Done**
- Repo scaffold: uv project (Python 3.12), ruff, mypy (strict), pytest, MIT licence,
  README, CLAUDE.md, `.env.example`, GitHub Actions CI (lint, format, types, schema drift,
  tests).
- Schemas for `event`, `tracking`, `overlay` (+ `world`) in `/schemas`; Pydantic models
  generated into `services/contracts` by `scripts/gen_models.sh`.
- Fictional world: 4 clubs (Lagos Lions, Harbour City FC, Northbank Rovers, Kestrel Vale
  Athletic), 18-player squads with hand-written invented names, seeded ratings, generated SVG
  crests.
- Simulator v1 (`services/sim`): possession-based Markov engine; 5 Hz tracking; seed; speed
  (1x/5x/20x, or 0 = unpaced); stdout (JSON lines or `--format pretty`) and file sinks;
  deterministic ULID event ids.
- Acceptance checks pass. Mean over 50 seeded runs across all 12 pairings: about 1,000
  passes, 23 shots, 2.7 goals. No events or frames out of bounds, `seq` monotonic, every
  event valid against the JSON Schema. Tracking: top speeds 32–33 km/h for the quickest
  players, median outfield distance about 11.6 km.
- Dataset: 6 seeded matches (events + meta) in `data/matches/`.

**Broken / not done**
- Public GitHub repo not created: no `gh` CLI or credentials here. The repo is committed
  locally on `main`.
- Foundry project and the two model deployments are not provisioned: needs the Azure account.
- Hello-world Container App (the spec's Day 1 risk check) not deployed, for the same reason.
- Tracking is pure Python: about 10 s CPU per full match on a loaded dev machine. That is
  far faster than any live speed needs; vectorize later only if exports get slow.

**Actions for the owner**
1. Create the public repo and push: `gh repo create pitchside-ai --public --source . --push`.
2. In Azure AI Foundry, create a project with one large and one small chat deployment. Put
   the endpoint and deployment names in `.env` (see `.env.example`) and confirm quota.
3. Optional but recommended by the spec: deploy a hello-world Container App to surface
   subscription, region and quota problems early.

**Next (Day 2)**: stats engine with unit tests for every metric (incl. pass difficulty, xG,
PPDA), Control vs Chaos index and threshold triggers, Match Stats MCP server (six tools),
in-process bus + Ingestor with SQLite in local mode, and the `comeback` and `late_winner`
scenario scripts (the engine's `TeamModifiers` are the hook for them).

## Day 2 — numbers (worked Oct 19-20)

**Done**
- Stats Engine (`services/stats`): possession, pass accuracy, distance, speed and difficulty,
  shot speed, xG, PPDA, turnovers, distance covered, sprints, top speed, key passes, heat
  maps, shot map, pass network, difficulty histogram; windows for the match, each half and
  the last 5/10/15 minutes. Unit tests for every metric.
- Control vs Chaos index every 30 s over a 5-minute window, calibrated on simulated matches
  (`scripts/calibrate_stats.py`), with speed, pass-difficulty, xG, goal, card, period,
  momentum-swing and tick triggers. Per match: about 11 sprint triggers, 3 hard passes,
  2 big chances, 6 momentum swings.
- Match Stats MCP server (`services/mcp_stats`) with the six tools, tested through a real
  MCP client over Streamable HTTP.
- Local bus, SQLite event log, Ingestor (JSON Schema validation, de-duplication) and stats
  service; a full match flows sim → bus → Ingestor → Stats Engine in tests.
- Scenario scripts: comeback, late_winner, red_card and pressing_collapse, each tested over
  10 seeds. `python -m sim run --scenario comeback` uses the scenario's clubs.
- 199 tests pass; ruff, format and mypy (strict) are clean.

**Broken / not done**
- Still no public GitHub repo or Azure resources (see Day 1 owner actions).
- The dev machine's network is slow (PyPI downloads at ~30 KB/s), so dependency installs
  take 15+ minutes; nothing to fix in the repo.

**Next (Day 3)**: Agent Framework workflow with typed messages and trace ids; Moment
Detector, Tactical Analyst and Narrator reading through the MCP server; gateway WebSocket
pushing overlay JSON; one match explained end to end in a terminal.

## Day 3 — first agents, first slice (worked Oct 20)

**Done**
- Agent Framework workflow (`services/agents/workflow.py`): Moment Detector → Tactical
  Analyst → Narrator → Fan Lens → Localizer → Fact Checker → Producer, typed messages
  with trace and moment ids, one workflow per trigger.
- All seven agents (Day 4's four included), with versioned prompts in
  `services/agents/prompts`, reading stats only through the Match Stats MCP server.
- Failure handling (also Day 4): instant stats-only cards, 4 s soft / 20 s hard budgets
  with upgrade in place, circuit breakers, chaos switch, wrong-number fault injection,
  one regeneration then fallback, stale-card dropping.
- Gateway: REST, WebSocket fan-out filtered per profile, Director API, ingest socket,
  Web PubSub path for Azure; `python -m runtime.main` runs everything locally.
- Milestone: `uv run python scripts/explain_match.py --scenario comeback` explains a whole
  match in the terminal; a live match also streams to a WebSocket client with agent cards
  in English, Pidgin and Yoruba.
- Azure adapters written (Event Hubs bus, Cosmos DB store); untested until there is a
  subscription.

**Broken / not done**
- No real model has been called yet: no Foundry or other endpoint is configured here. The
  offline mock covers local mode and tests; the first run against Foundry needs the owner's
  deployments (the prompts are written for them).

**Next (Day 4)**: evals for every agent (30 seeded moments, number accuracy and language
quality), then the native-speaker review list for Pidgin and Yoruba.

## Day 4 — the rest of the crew (worked Oct 20)

**Done**
- Fan Lens, Localizer, Fact Checker and Producer, and the failure handling, were built
  on Day 3; today added the evals that hold them to account.
- `uv run python -m evals.run` replays 30 seeded moments through the crew for five viewers
  and scores every agent. With the offline models all seven pass (results in
  `evals/results/mock.md`); the run caught and fixed xG jargon in casual and kids cards and
  Pidgin lines that read as English.
- `evals/results/language_samples.md`: 20 Pidgin and 20 Yoruba cards ready for review.

**Broken / not done**
- The evals have only run against the offline models. With Foundry deployments in place,
  run `FOUNDRY_ENDPOINT=... MODEL_LARGE=... MODEL_SMALL=... uv run python -m evals.run`.
- Native-speaker review of the Pidgin and Yoruba samples (owner action).

**Next (Day 5)**: the match screen in the browser (pitch, scoreboard, overlay rail, stat
bug, momentum ribbon, player tags), the onboarding sheet, and the live match with agent
cards in sync.

## Days 5-6 — the screen, personalisation and recap (worked Oct 20)

**Done**
- Next.js static site (`web/`): the broadcast match screen (2D pitch interpolated to 60 fps
  from 5 Hz tracking, scoreboard and clock, lower third over the pitch, full card, ticker,
  corner stat bug for the viewer's focus metric, momentum ribbon, player tags), the
  20-second onboarding sheet, Three Fans, Player Cam (focus ring, player panel, cards about
  the chosen player), the analyst dashboard (pass networks, shot map, difficulty histogram,
  clickable momentum timeline with the agent's explanation and evidence events), the
  full-time recap (five languages, player of the match, copy as JSON) and the Director
  panel (start, chaos switch, wrong-number injection, live agent trace and per-agent
  latency).
- Milestone: a live match in the browser with agent cards in sync. Checked with
  screenshots in headless Chrome and a Playwright smoke test (2 tests) against the running
  stack.
- Fixes found by running it: card lifetimes scale with playback speed (D28), SQLite fsync
  stalls (D29), viewers' cards share one stats snapshot, the recap page's polling loop,
  and the histogram rendering.

## Day 7 — Azure and hardening (worked Oct 20)

**Done**
- `Dockerfile` (one image: Python services plus the built site), `docker-compose.yml` for
  local mode, `azure.yaml` and `infra/` (Bicep: Foundry with two model deployments,
  Container Apps, Event Hubs, Cosmos DB, Web PubSub, Static Web Apps, App Insights, Key
  Vault, managed identity with least-privilege roles, an optional budget alert). The Bicep
  compiles and lints clean with Bicep 0.48.
- Event Hubs bus and Cosmos DB store adapters; Web PubSub delivery; App Insights
  exporter with managed identity plus Agent Framework instrumentation.
- CI: lint, types, schema drift (Python and TypeScript), 319 tests, evals, web build,
  Playwright against a live gateway, Docker build and smoke check, Bicep build and lint. A
  manual deploy workflow uses azd with GitHub OIDC.
- Hardening: three full 20× matches with three viewers ran clean (zero agent errors, zero
  false rejections, recap written); tracking to browsers is thinned at fast replays; the
  stats registry evicts old finished matches; real-world names are blocked by a hashed
  deny-list scanned over every tracked file.

**Broken / not done**
- Not deployed: no Azure subscription or `az`/`azd` here, so the Bicep has never run
  against Azure. Expect a round of fixes on the first `azd up` (for example model version
  or region availability, and whether `FoundryChatClient` needs a different endpoint form
  for your project).
- The Docker image was not built on this machine (the disk is 99% full); CI builds it and
  checks that local mode answers.
- With the dev machine heavily loaded by other work, one run froze for several minutes
  (swap and a load average near 40); nothing in the code was implicated, and runs at normal
  load keep their speed.

## Day 8 — ship: what is left for the owner

1. **GitHub:** create the public repo and push (`gh repo create pitchside-ai --public
   --source . --push`); CI runs on push.
2. **Azure:** `azd auth login`, then `azd env set PITCHSIDE_BUDGET_EMAIL <you>` and `azd up`.
   If the default models are not available in your region, set `MODEL_LARGE`,
   `MODEL_SMALL` (and the versions in `infra/main.bicep`) or `PITCHSIDE_FOUNDRY_LOCATION`.
   Then run three matches at 5× from the demo URL and check App Insights for traces
   (screenshot for the README).
3. **Evals on real models:** `FOUNDRY_ENDPOINT=... MODEL_LARGE=... MODEL_SMALL=... uv run
   python -m evals.run`, and have a native speaker review
   `evals/results/language_samples.md` (corrections go into
   `services/agents/prompts/localizer.v2.md` as few-shot examples and into
   `services/agents/i18n.py`).
4. **Video:** record with `docs/VIDEO.md` (QuickTime or OBS on this Mac), upload to
   YouTube, add the link to the README and the submission.
5. **Submit:** paste `docs/SUBMISSION.md` into the hackathon site, choose Best
   Multi-Agent System, and open the repo and demo URL in a private window before 8 pm Lagos
   on Oct 27.
