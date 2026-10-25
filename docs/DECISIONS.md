# Decisions

Deviations from, and interpretations of, `docs/SPEC.md`. Newest last.

## Day 1 (Oct 19, 2026)

### D1. One uv project for all Python services
The spec lists services as folders under `services/`. They are top-level packages (`sim`,
`contracts`, later `stats`, `agents`, ...) built from one root `pyproject.toml` rather than
one project per service. **Why:** one lockfile, one CI job and shared contracts with no
publishing step, which matters on an 8-day clock. Each Container App image can still install
the same project and run its own module.

### D2. Event coordinates are team-relative; tracking is absolute
The spec says "pitch 105 x 68, attacking left to right". For **events**, coordinates are in
the acting team's frame: x=0 is its own goal line, x=105 the opponent's, y=0 the touchline on
its left. Converting between frames is a 180° rotation: `(105 - x, 68 - y)`. **Tracking
frames** use one absolute frame in which the home team attacks towards x=105 for the whole
match (no switch at half-time). Events without a team (`period_end`) use the home frame.
**Why:** team-relative events make xG, pass difficulty and line-breaking simple (the goal is
always at x=105); one fixed frame keeps the 2D pitch view stable.

### D3. Tracking frames carry `period`
Added `period` to the tracking frame. **Why:** `clock_ms` is the displayed clock, so the
second half restarts at 45:00 and first-half stoppage time (e.g. 45:00–47:30) overlaps it.
Without `period`, those frames would be ambiguous.

### D4. How a goal is encoded
A scoring shot is a `shot` event with `outcome: "complete"`, immediately followed by a `goal`
event by the same player (`x, y` = where it was struck from, `end_x, end_y` = the net). Shot
outcomes are restricted to `complete | saved | blocked | off_target` by the JSON Schema.

### D5. Small extensions to the event schema
- `card_color` allows `second_yellow` as well as `yellow` and `red`, so a dismissal for two
  bookings is distinguishable from a straight red.
- `substitution`: `player_id` is the player leaving, `recipient_id` the player coming on.
- `team_id` and `player_id` are required for every type except `period_end`.
- Conditional rules (e.g. a pass needs `end_x/end_y`, `ball_speed_kmh`, `recipient_id`) live
  in the JSON Schema `allOf`. The generated Pydantic models enforce types, bounds and
  required fields, but not these conditionals, so tests validate against the JSON Schema too.
- Possession: `possession_change` is emitted whenever the ball passes to the other team in
  play or at a restart; a `kickoff` also establishes possession on its own.

### D6. Deterministic event ids
`event_id` is a ULID whose timestamp is a fixed synthetic kickoff instant (2026-10-27 18:00
UTC) plus elapsed match time, including a 15-minute half-time, and whose random bits come from
an RNG seeded by `match_id`. The same match therefore always has the same ids, and ids sort
in emission order. **Consequence:** a live replay of the same seed must pass a fresh
`--match-id`, or the Ingestor's de-duplication would drop it. The gateway will do this.

### D7. Simulator CLI details
- `--speed 0` means unpaced (used for exports and tests). Half-time is a short wall-clock
  pause (`--halftime-s`, default 10 s).
- stdout output is JSON lines with an envelope: `{"topic": "events" | "tracking", "data": ...}`.
  `--format pretty` prints a readable log instead (events only).
- `--sink ws` and `--sink eventhubs` exist in the CLI but exit with a clear error until the
  gateway (Day 3) and the Azure deployment (Day 7) add them.
- `--scenario` only accepts `default` until the scenario scripts land on Day 2.

### D8. Published dataset excludes tracking by default
`data/matches/` holds events and metadata for seeded matches (≈0.5 MB each). Tracking files
(≈4 MB gzipped per match) are git-ignored and can be regenerated deterministically with
`--sink file --topics events,tracking`.

### D9. A world schema
Added `schemas/world.schema.json` (with a generated model) so the published world file is
validated like the other contracts. It also fixes the player id format to `<TEAM>-<shirt>`,
e.g. `LAG-09`.

### D10. Day 1 items that need the account owner
Creating the **public GitHub repo** and provisioning the **Foundry project and model
deployments** need credentials this environment doesn't have (no `gh`, `az` or `azd` CLI).
Everything else in Day 1 is done; these two are listed in PROGRESS.md as actions for the owner.

## Day 2 (worked Oct 19-20, 2026)

### D11. How the Stats Engine defines its numbers
- **Possession** is the share of ball-in-play time, credited between consecutive events to
  the team in possession (gaps capped at 8 s); play stops at out-of-play, fouls, goals and
  period ends. **Turnovers** are possession changes, except those after the losing team's
  own shot.
- **Pass difficulty** (0-100): distance (30 pts, linear to 40 m), passer under pressure
  (20), opponents bypassed (25, full at 5+) and space at the target (25, full at 1.5 m or
  less, none at 9 m+), using the latest tracking frame. Without tracking, line-breaking
  falls back to 20 m+ forward and tightness scores a neutral 12.5.
- **xG** is the distance + angle logistic model with the engine's coefficients for an
  average finisher, discounted for headers, pressure and direct free kicks; penalties 0.76.
- **PPDA**: opponent passes in their first 60% of the pitch per tackle, interception or
  foul in that zone.
- **Control vs Chaos** blends possession stability (passes per possession, 35%), turnover
  rate (30%), pressure rate (20%) and forward tempo (15%) over the last 5 minutes, every
  30 s of match time. Baselines are the medians from `scripts/calibrate_stats.py` and the
  scales about five standard deviations, so a typical window sits near 0 and a swing of 30+
  in 5 minutes happens about 6 times a match. The dominant team is the one with more than
  55% of the ball in the window.
- **Speed** is smoothed over three 5 Hz samples (0.6 s). The >32 km/h trigger fires once
  per sprint and at most once per player per 5 minutes; a sprint is 25.2 km/h for 1 s+.
- **Triggers** also fire on goals, cards, half time, full time, an xG above 0.3, a
  completed pass above 80 difficulty, a momentum swing of 30+ (3-minute cooldown) and every
  30 s of match time (the Moment Detector's heartbeat).

### D12. MCP tool signatures
Every tool takes `match_id` first, because one server serves every live match. Windows
are `match | first_half | second_half | last_5 | last_10 | last_15`. `get_events(since)`
uses event `seq` (the clock is ambiguous across halves). `get_player_stats` leaves out the
96-cell heat map unless `include_heatmap` is set, to keep agent context small. The server
is stateless Streamable HTTP with JSON responses.

### D13. Dependency pins
- `mcp` stays on 1.x (1.30): Agent Framework 1.22's MCP tools import 1.x modules and the
  framework's extras pin `mcp<2`.
- `cryptography<49`: 49+ ships no Intel macOS wheel, so uv compiled it from Rust source on
  the dev machine. 48.0.1 has universal2 wheels; revisit when the Intel Macs go.

### D14. The Stats Engine and the MCP server share a process
The MCP server answers from in-memory StatsEngines, so in Azure the stats service and the
MCP server run in the same Container App. The event log is in Cosmos DB, so a restarted or
new replica rebuilds any match on demand (tracking-derived numbers restart from zero).

### D15. Scenario scripts
Scenarios are YAML validated by `schemas/scenario.schema.json`. Beats can set team
modifiers, schedule a goal or force a straight red. With `scoring: scripted` only goal
beats score, and an otherwise-scoring shot becomes a save, so every seed tells the same
story (the comeback is always 0-2 at the hour, then 2-2). All four scenarios from the spec
are done, not just the two Day 2 asked for. Scripted goals land within about two minutes
of their minute.

### D16. Bus messages
Messages are JSON dicts in both modes. Models are dumped with `exclude_unset`, so
optional fields the JSON Schemas forbid as null are left out, while nullable stats (e.g.
PPDA before any defensive action) stay as null. In local mode every subscriber gets every
message on its topic; Event Hubs consumer groups give the same fan-out in Azure.

### D17. Overlay contract extensions
`OverlayCard` gains optional `kind`, `source` (agent or template), `player_id` (where a
player tag goes) and `team_id` (club colours). Renderers that ignore them still work.

## Day 3 (worked Oct 20, 2026)

### D18. Model clients
Agents use Agent Framework's `FoundryChatClient` against the Foundry project
(`FOUNDRY_ENDPOINT`, deployments `MODEL_LARGE` / `MODEL_SMALL`, managed identity).
Locally, `OPENAI_COMPAT_BASE_URL` switches to `OpenAIChatCompletionClient` for any
OpenAI-compatible server; with neither set, an offline mock chat client is used. The mock
is a real Agent Framework client (function-invocation, middleware and telemetry layers)
that asks for MCP tools through the same function-calling loop and writes from a phrase
bank, so local mode and CI exercise the whole pipeline without a model. Model output uses
strict JSON-schema response formats, which is why the output schemas carry no length or
range keywords (code clamps instead).

### D19. When the models are not called
- Goals and period ends are moments by rule; the Moment Detector model is skipped.
- Ticks in the first 5 minutes of a half are skipped (the 5-minute window is not full),
  and at most one "spell" moment is explained per 5 minutes of match time.
- With nobody watching a match, ticks, sprints and hard passes are skipped; goals, cards,
  big chances, momentum swings and period ends still run (they feed the dashboard and the
  recap).
- The Analyst runs for importance 0.5+ or a momentum swing of 30+; the Narrator for
  insights, goals, cards and period ends; the Producer's model only for agent cards of
  importance 0.8+ (house rules plan the rest).

### D20. Template first, upgrade in place
Goals, cards, big chances, sprints, hard passes, momentum swings and period ends publish
a stats-only card for every viewer as soon as the trigger arrives (well under 1 s). The
agents' card for the same moment and viewer reuses its overlay id, so it replaces the
template on screen. Each model call has a 4 s soft budget (after which the template goes
out if it has not already) and a 20 s hard budget; three failures in 60 s open an agent's
circuit breaker for 30 s. The Producer drops a card once the match clock has passed its
moment by more than its ttl. The chaos switch makes an agent unavailable for N seconds.

### D21. What the Fact Checker checks against
Code extracts every figure (percentages, km/h, km, m, xG, difficulty, index points,
minutes, scorelines, plain counts) and requires a match of the same kind within the
precision the card used. The reference set is fresh MCP reads plus every MCP result the
writers received in this run (recorded by a function middleware), so a card is not
rejected just because the match moved on while it was being written. Derived numbers
(sums, differences) are rejected. The small model then checks the words around the
numbers. One regeneration with the correction in context, then the stats-only card.

### D22. Workflow shape and latency
The chain is linear as in the spec, one workflow instance per trigger (Agent Framework
forbids concurrent runs of one instance), at most four in flight per match. The Fan Lens
writes each viewer's card concurrently and the Localizer, Fact Checker and Producer then
handle each card independently. Explained cards arrive about 4-8 s after the event with
cloud models; the instant stats-only card covers the gap.

### D23. Gateway topology
Local mode: one process runs the simulator service, Ingestor, Stats Engine + MCP server,
agents and gateway (`python -m runtime.main --role all`). Azure: one Container App per
role on Event Hubs and Cosmos DB; the gateway reads stats from the stats app over HTTP
and delivers through Web PubSub groups per match, per profile and for admins. The
simulator CLI's `--sink ws` posts to `/ws/ingest`, which is open in local mode and needs
`PITCHSIDE_INGEST_TOKEN` in Azure.

## Day 4 (worked Oct 20, 2026)

### D24. How the agents are evaluated
`evals/` holds one eval module per agent over 30 seeded moments (`evals/data/moments.jsonl`,
regenerated by `python -m evals.dataset`): a fixed mix of goals, cards, big chances,
momentum swings, hard passes, sprints, half times, full times and ticks across all five
scenarios. Each moment is replayed through the real crew and MCP server for five viewers
covering all four modes and five languages. Thresholds: moment kind accuracy 0.9,
insight and commentary number accuracy 0.9 and full coverage, mode rules 0.95, every
published card in its viewer's language and with every figure backed, Fact Checker recall
1.0 on injected errors with no false positives, a valid overlay contract and stat
overlays under 1 s. Language quality is only checked loosely by machine (tone marks,
Pidgin markers, function words); the native-speaker review of
`evals/results/language_samples.md` is the real check.

### D25. Plain language for casual and kids viewers
Casual and kids cards never lead with xG or other analyst terms: big chances use a plain
"Big chance for <club>!" title and drop the xG stat; analysts keep the numbers.

## Days 5-7 (worked Oct 20, 2026)

### D26. The web app
A Next.js static export (no server rendering), so it can sit on Static Web Apps or be
served by the gateway; pages take the match from `?id=` instead of dynamic routes. In local
mode and in the single-container image the gateway serves `web/out`, so the whole demo is
one origin. Tracking frames go into a ref and the pitch interpolates between the last two
on every animation frame (smooth at 60 fps from 5 Hz data); everything else is React state.
The browser asks `/api/negotiate` where to connect: the gateway's own socket locally, Azure
Web PubSub in Azure.

### D27. Azure topology and scaling
One image, five Container Apps (gateway, stats with the MCP server, agents, ingestor, sim),
selected by `PITCHSIDE_ROLE`. **Deviation:** the spec mentions KEDA scaling on Event Hubs and
scale to zero. Each worker keeps per-match state in memory (the Stats Engine, the agents'
spell memory) and the gateway forwards every message to Web PubSub, so a second replica
would split or duplicate work. Every app therefore runs exactly one replica. Scaling out
would mean partitioned consumers with a checkpoint store and an external state store;
that is not needed for a demo. Foundry (an AIServices account, a project and the two model
deployments) is provisioned by the same Bicep. Model names and versions are parameters
(default `gpt-4.1` and `gpt-4.1-mini`) because availability varies by region and over time.
Static Web Apps hosts the site as the spec asks; the gateway also serves it, which gives a
same-origin fallback URL.

### D28. A card's ttl is reading time, stored in match time
The overlay contract defines `ttl_ms` as how long a card stays valid after `clock_ms` in
match time. A card meant to be read for 15 s at 5× is valid for 75 s of match clock, so
`ttl_ms` = reading seconds × playback speed. The Producer's staleness check and the
browser's display time both follow from that. Without this, at demo speeds the Producer
dropped most explained cards as stale before they arrived.

### D29. SQLite durability in local mode
SQLite runs WAL with `synchronous=NORMAL`. Writes happen on the event loop, and a durable
fsync per insert stalled live matches when the agents wrote bursts of trace documents.
NORMAL never corrupts the database; a power cut can lose the last few writes, which local
mode can afford.

### D30. Optional features cut
Per the spec's cut order, the audio recap (Azure AI Speech) and the A2A endpoint for the
Fan Lens were not built. Everything the spec says never to cut (Three Fans, Fact Checker,
Azure deployment templates) is in.

### D31. Web PubSub viewers register by heartbeat
The agents write cards only for profiles that are watching. Locally the gateway sees
every viewer's WebSocket; in Azure mode browsers connect straight to Web PubSub, so the
gateway would never learn of them and no cards would be written. A viewer is therefore
registered when it negotiates, and the browser sends `POST /api/matches/{id}/viewers` every
30 s while connected; a viewer silent for 90 s is dropped. The gateway re-announces the
viewer list every 30 s, so a restarted agents service learns it again. Web PubSub's
connect and disconnect event handlers would be exact, but they need a public webhook
endpoint with validation; the heartbeat needs nothing extra and the gateway runs one
replica (D27).
