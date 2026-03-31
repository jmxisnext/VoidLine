# Checkpoint: VoidLine v0.3.0

**Date:** 2026-03-31
**Anchor:** 2 — Voidline (Feasibility)
**Status:** Core engine complete. Presentation layer added. Portfolio-ready.

## What Was Built

A constraint-driven possibility field engine that models how defensive pressure, kinematic commitment, perceptual limits, and rules remove available actions from an agent's space — and supports counterfactual replay to prove what would have changed.

### Core capabilities

- 6 constraint categories (spatial, temporal, kinematic, role, perceptual, risk)
- 4 temporal dynamics (static, sustained, transient, decaying)
- Possibility field computation with per-constraint removal attribution
- Tick engine with event detection (constraint expired/activated, corridor opened/collapsed)
- Rail topology with JSON-schema-validated scenario loading
- Corridor viability projection (continuous field onto discrete topology)
- Single-fork counterfactual replay with aligned divergence analysis
- Structured text reports with natural-language conclusions

### Validated scenarios

- PNR (pick-and-roll): star topology, monotonic pressure decrease, expiry-driven
- Transition (3-on-2): cascading topology, non-monotonic pressure, activation-driven

### Test coverage

105 tests, all passing (<1s).

## What Was Proven

1. **Constraints compose predictably** — 7 constraints at t=0 produce 90% pressure, expiry of 3 reduces to 45%.
2. **Corridor viability tracks constraints spatially** — drive_left goes from 86% to 97% when help defender's circle no longer overlaps the corridor.
3. **Counterfactual replay isolates causation** — replacing one transient constraint with a sustained version produces a 20% pressure divergence at exactly the expected timestamp.
4. **Engine generalizes across topology and temporal profile** — PNR (monotonic, star) and transition (non-monotonic, cascading) both work with the same engine.
5. **Non-monotonic pressure is captured** — transition scenario shows pressure dropping then rising when a recovering defender activates mid-play.

## Hero Result

Help defender counterfactual in PNR:

| Scenario | Pressure | drive_left | Status |
|---|---|---|---|
| Help rotates out | 45% | 97% viable | SPACE OPEN |
| Help stays | 65% | 86% viable | UNDER PRESSURE |

Same play, one variable changed. 20% pressure swing, driving lane opens or stays degraded.

## Artifact Index

| File | Purpose |
|---|---|
| `src/field/space_model.py` | Spatial primitives, court model |
| `src/constraints/types.py` | 6 constraint categories |
| `src/envelope/field.py` | Possibility field computation |
| `src/engine/tick.py` | Tick loop, event detection |
| `src/rail/graph.py` | Topology loader, corridor viability |
| `src/replay/` | Fork, compare, models, report |
| `scenarios/pnr_basic.json` | PNR scenario definition |
| `scenarios/transition_3on2.json` | Transition scenario definition |
| `demo_runner.py` | Terminal demo output |
| `visualize_hero.py` | Hero figures (court + pressure timeline) |
| `help_defender_flip.png` | Two-panel court comparison |
| `pressure_timeline.png` | Pressure over time chart |
| `README.md` | Portfolio-focused documentation |

## Locked Assumptions (Do Not Change Without Reason)

- Volume summation (not geometric union) — acknowledged, shape is reliable
- Sampling-based corridor viability (spacing = 0.5 ft)
- Single-agent per scenario
- Static constraint geometry (activate/expire, not translate)
- dt = 0.1s tick resolution

## Deferred Items (Do Not Start Yet)

- Agent archetypes scoring over surviving field
- Envelope-keyed tabular memory
- Geometric union of overlapping constraint boundaries
- Continuously moving constraint boundaries
- Multi-agent field interaction
- Additional play-type scenarios

## Resume Commands

```bash
cd J:/projects/VoidLine
python -m pytest tests/ -v           # 105 tests
python demo_runner.py                # PNR scenario demo
python visualize_hero.py             # regenerate figures
```

## Next Steps (When Resuming)

1. Cross-anchor portfolio alignment (link VoidLine + Decision Window)
2. Optionally: agent archetypes (first consumer of the possibility field)
3. Optionally: moving constraint boundaries
