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

122 tests, all passing (<1s).

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
| `adapter/constraint_generator.py` | Cross-anchor bridge (ISO4D → VoidLine constraints) |
| `examples/help_defender_replay.py` | PNR counterfactual replay script |
| `examples/transition_replay.py` | Transition counterfactual replay script |
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
python -m pytest tests/ -v           # 122 tests
python demo_runner.py                # PNR scenario demo
python visualize_hero.py             # regenerate figures
```

## v0.3.1 — Scheme-Driven Integration (2026-04-03)

**Extracted offensive motion plus scheme-driven defense produces stable, scheme-differentiated constraint behavior with meaningful timing sensitivity.**

### What was added

- **Scheme Engine** (`adapter/scheme.py`): generates defender entities from offensive state + scheme rules. Three schemes: drop, ice, help_heavy. Three archetypes: on-ball defender, help defender, rim protector. Ball-relative positioning with per-scheme reaction delay.
- **VoidLine integration** (`integration_iso3.py`): loads ISO4D extraction, transforms coordinates (ui_halfcourt_normalized -> ISO4D feet), injects scheme defenders, evaluates per-frame constraint fields, compares normal vs +300ms delayed reads across schemes.

### What was proven

| Scheme | Peak pressure | Max delay delta | Active defenders |
|---|---|---|---|
| drop | 28.5% | +23.5% | D1_onball only (help stays at 18ft) |
| ice | 30.0% | +26.4% | D1_onball + tighter deny-middle positioning |
| help_heavy | 36.1% | +32.6% | D1_onball + D2_help (gap help at 8.5ft) |

1. **Scheme differentiates behavior.** drop < ice < help_heavy in both peak pressure and delay sensitivity.
2. **Help defender activates only when scheme demands it.** D2_help enters the 15ft constraint radius only in help_heavy — drop and ice keep help at 18-20ft.
3. **Rim protector contributes to corridor denial, not field pressure.** D3 at 33ft from a wing ball handler is correct basketball — its impact belongs in corridor viability analysis, not direct pressure.
4. **Static entities stay quiet.** Offensive SF contributes 0.6% volume, never dominates.
5. **Delay sensitivity scales with scheme aggressiveness.** More active constraints = stale reads compound more.

### Architecture

```
ISO4D          ->  state (positions, velocities from video)
Scheme Engine  ->  defense (generated from offensive state + scheme rules)
VoidLine       ->  pressure field (constraint removal, corridor viability)
```

The Scheme Engine is a distinct layer — it consumes offensive state and produces defensive entities, which VoidLine then evaluates as constraints. Offense from extraction. Defense from scheme logic.

### Cross-anchor integration (completed)

Decision Window integration validated in the DecisionWindow repo (`integration_voidline.py`). Pass viability evaluated under all three schemes with delay sweep. Key result: ice kills the pass spatially, drop allows it up to 200ms delay, help_heavy allows it up to 100ms. See DecisionWindow checkpoint v0.2.1.

## Next Steps (When Resuming)

1. Portfolio packaging: one diagram, one comparison table, one sentence across all repos
2. README updates across repos to reflect full pipeline
3. TickEngine integration with scheme defenders (corridor viability under scheme pressure)
4. Optionally: agent archetypes (first consumer of the possibility field)
