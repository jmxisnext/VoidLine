# VoidLine — Claude Code Project Instructions

## Role

Anchor 2: Constraint-driven feasibility modeling engine.

Models what actions are impossible under defensive pressure, kinematic commitment, perceptual limits, and rules. The product is the shape of surviving possibility after constraints carve away the rest. Does NOT perform state extraction or execution timing — those belong to ISO4D and Decision Window.

## Current Milestone

v0.3.1 complete. Core engine, 2 validated scenarios, scheme-driven defense integration, 122 tests. See `docs/checkpoints/CHECKPOINT_v0_3_voidline.md`.

## Session Start

1. Read this file
2. Read `docs/checkpoints/CHECKPOINT_v0_3_voidline.md`
3. Run `git status` and `git log --oneline -3`
4. Summarize: current milestone, dirty state, next 3 actions

## Session Close

1. Update checkpoint if milestone state changed
2. Summarize what changed
3. List next actions
4. Confirm `git status`

## Run / Test

```bash
python -m pytest tests/ -v             # 122 tests, <1s
python demo_runner.py                  # PNR scenario terminal demo
python visualize_hero.py               # regenerate hero figures
```

## Directory Map

| Path | Purpose |
|---|---|
| `src/field/` | Spatial primitives, court model |
| `src/constraints/` | 6 constraint categories |
| `src/envelope/` | Possibility field computation |
| `src/engine/` | Tick loop, event detection |
| `src/rail/` | Topology loader, corridor viability |
| `src/replay/` | Counterfactual fork, compare, report |
| `adapter/` | Cross-anchor bridge: constraint generator + scheme engine |
| `adapter/scheme.py` | Defensive scheme engine (drop, ice, help_heavy) |
| `scenarios/` | JSON scenario definitions |
| `schemas/` | JSON schema validation |
| `tests/` | Test suite |
| `docs/checkpoints/` | Milestone checkpoints |
| `integration_iso3.py` | End-to-end integration demo (ISO4D -> scheme defense -> VoidLine) |

## Anchor Boundary

This module is responsible ONLY for feasibility modeling. Do not add:
- State extraction (ISO4D)
- Timing evaluation (Decision Window)
- Validation / ground-truth comparison (RenderTrace)

## What Not to Touch

- Locked assumptions in the checkpoint (volume summation, sampling spacing, tick resolution)
- Deferred items listed in the checkpoint — do not start without explicit instruction
- `adapter/` interface contract — stack_integration depends on this
