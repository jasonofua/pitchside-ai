# CLAUDE.md

Pitchside AI is our entry to the Microsoft "Inside the Game" hackathon. The full spec is
`docs/SPEC.md`; read it before writing code. Sessions follow the build plan one day at a
time ("Continue with Day N of docs/SPEC.md").

## Standing rules

1. Follow docs/SPEC.md. If you need to deviate, explain why and record it in docs/DECISIONS.md.
2. Numbers come only from deterministic code (services/stats). Agents never compute or invent
   statistics; they read them through the Match Stats MCP server.
3. Fictional data only: no real clubs, leagues, players, crests, or broadcaster marks anywhere
   in code, data, UI, or docs.
4. Python 3.12 with uv, ruff, mypy, pytest. TypeScript strict with pnpm. Pydantic models
   generated from the JSON Schemas in /schemas.
5. Every metric has a unit test. Every agent has a prompt file in services/agents/prompts and
   an eval in /evals.
6. Local mode must run with `docker compose up` and no Azure account; Azure mode deploys with
   `azd up`. Never commit secrets; use managed identity in Azure and .env.example locally.
7. Use Microsoft Agent Framework (Python) for agents and workflows, and Microsoft Foundry model
   deployments via env vars FOUNDRY_ENDPOINT, MODEL_LARGE, MODEL_SMALL. If you are unsure of a
   current SDK API, check the official docs or package source before writing code — do not guess.
8. Work in small commits with conventional messages. At the end of each session, update the
   checklist in docs/SPEC.md and write a short docs/PROGRESS.md entry: done, broken, next.

## Commands

```bash
uv sync                                   # install (Python 3.12, dev tools included)
uv run pytest                             # all tests, incl. the 50-run totals check
uv run pytest -m "not slow"               # skip the 50-run check while iterating
uv run ruff check . && uv run ruff format --check . && uv run mypy
./scripts/gen_models.sh                   # regenerate services/contracts from /schemas
uv run python scripts/gen_world.py        # regenerate data/world.json and crests
uv run python -m sim run --seed 42 --speed 5 --format pretty   # watch a match
```

## Conventions that are easy to get wrong

- `services/contracts/*.py` is generated. Edit the schema in `/schemas`, then run
  `./scripts/gen_models.sh`; CI fails if the two drift.
- Event coordinates are in the **acting team's frame** (attacking towards x=105); tracking
  frames are **absolute** (home attacks towards x=105 all match). Flip with
  `sim.formation.flip`. Details in docs/DECISIONS.md.
- `clock_ms` is the displayed match clock: period 2 restarts at 2,700,000 (45:00), so
  first-half stoppage overlaps it. Order by `seq`, or by `(period, clock_ms)`.
- The simulator is deterministic for a given (teams, seed). Live runs must pass a fresh
  `--match-id` so event ids don't collide with earlier runs in the event log.
- Each Python service is a top-level package under `services/` (`sim`, `contracts`, ...),
  all built from the root `pyproject.toml`.
