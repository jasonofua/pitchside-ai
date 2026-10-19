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
