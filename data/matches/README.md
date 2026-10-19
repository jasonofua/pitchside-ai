# Pitchside synthetic matches

Fully synthetic football matches produced by the Pitchside AI match engine
(`services/sim`). Every club, player and match is invented; no real-world data is used.
MIT licensed.

## Files

For each match `<match_id>` (e.g. `lag-hcf-default-s42` = home LAG, away HCF, scenario
`default`, seed 42):

| File | Contents |
| --- | --- |
| `<match_id>.events.jsonl` | one event per line, valid against [`schemas/event.schema.json`](../../schemas/event.schema.json) |
| `<match_id>.meta.json` | seed, scenario, teams, final score, counts |
| `<match_id>.tracking.jsonl.gz` | 5 Hz positions ([`schemas/tracking.schema.json`](../../schemas/tracking.schema.json)); not committed, regenerate below |

Clubs, squads and player ratings are in [`data/world.json`](../world.json).

## Conventions

- Pitch is 105 x 68 m. Event coordinates are in the acting team's frame, attacking towards
  x=105, with y=0 on that team's left touchline. Tracking coordinates are absolute, with the
  home team attacking towards x=105 all match.
- `clock_ms` is the displayed match clock; the second half starts at 2,700,000 (45:00). Order
  events by `seq`.
- A goal is a `shot` with `outcome: "complete"` followed by a `goal` event.

See [`docs/DECISIONS.md`](../../docs/DECISIONS.md) for the reasoning behind each convention.

## Regenerate

Output is deterministic for a given home, away and seed:

```bash
uv run python -m sim run --home LAG --away HCF --seed 42 --speed 0 --sink file \
  --topics events,tracking
```
