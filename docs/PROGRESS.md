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
