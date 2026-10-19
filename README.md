# Pitchside AI

**Every fan saw the same goal. Pitchside AI tells each one a different story.**

Pitchside AI is a multi-agent system that watches a football match as it happens and turns
raw events into live, explained, personalized match intelligence. Specialist agents spot the
key moments, explain *why* they matter (grounded in deterministic stats and checked by a Fact
Checker), and reshape each insight for the viewer: analyst or casual fan, favourite club,
player cam, and language: English, Nigerian Pidgin, Yoruba, French or Spanish.

Everything runs on a synthetic match engine with invented clubs and players. No real league,
club or player data is used anywhere.

> Status: **Day 1 of 8.** The synthetic match engine, schemas and fictional world are done.
> Agents, the live UI and the Azure deployment follow. See [docs/PROGRESS.md](docs/PROGRESS.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (it fetches Python 3.12 if needed).

```bash
uv sync
uv run python -m sim teams                                       # the fictional clubs
uv run python -m sim run --seed 42 --speed 5 --format pretty     # watch a match at 5x
uv run python -m sim run --seed 42 --speed 0 --topics events     # raw JSON lines, unpaced
uv run pytest                                                    # tests
```

## Synthetic match engine

`services/sim` is a seeded, possession-based Markov model. At each touch the defending side
may press, tackle or foul; the carrier then shoots, carries, passes or crosses with
probabilities shaped by pitch zone, pressure, player ratings and fatigue. Pass targets come
from the same formation model that drives player movement, so the 5 Hz tracking stays
consistent with the events.

```
python -m sim run --scenario default --seed 42 --speed 5 --sink stdout|file [--format pretty]
                  [--home LAG --away HCF] [--topics events,tracking] [--match-id ID]
```

| Option | Meaning |
| --- | --- |
| `--speed` | match-clock multiplier: `1`, `5`, `20`; `0` streams as fast as possible |
| `--sink stdout` | JSON lines `{"topic": "events" \| "tracking", "data": {...}}`, or `--format pretty` |
| `--sink file` | writes `data/matches/<match_id>.events.jsonl`, `.tracking.jsonl.gz`, `.meta.json` |
| `--topics` | `events`, `tracking` (5 Hz positions), or both |

Over 50 seeded runs it averages about 1,000 passes (80% completion), 23 shots and 2.7 goals
per match. The test suite checks these totals, along with pitch bounds, monotonic `seq`,
schema validity and human-plausible player speeds.

## Data and contracts

| Path | What |
| --- | --- |
| [`schemas/`](schemas) | JSON Schemas: `event`, `tracking`, `overlay`, `world`. The source of truth. |
| `services/contracts/` | Pydantic models generated from the schemas (`./scripts/gen_models.sh`) |
| [`data/world.json`](data/world.json) | four invented clubs, 18-player squads, ratings; crests in `data/crests/` |
| [`data/matches/`](data/matches) | exported synthetic matches: an open dataset |

## Repository layout

```
schemas/        JSON Schemas (event, tracking, overlay, world)
services/
  contracts/    generated Pydantic models
  sim/          synthetic match engine, tracking, CLI
data/           world.json, crests, exported matches
scripts/        model and world generators
tests/          pytest suite
docs/           SPEC.md, DECISIONS.md, PROGRESS.md
```

Planned per the spec: `services/{ingestor,stats,mcp_stats,agents,gateway}`, `web/` (Next.js),
`infra/` (Bicep, `azd up`), and `evals/`.

## Microsoft technology

Planned: Microsoft Foundry (models), Microsoft Agent Framework (agents and workflows), MCP,
Azure Container Apps, Event Hubs, Cosmos DB, Web PubSub, Static Web Apps, Application
Insights, Key Vault; built with GitHub Actions and GitHub Copilot / Claude Code.

## Licence

[MIT](LICENSE). All clubs, players and crests are fictional.
