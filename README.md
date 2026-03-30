# VoidLine

**Possibility Field Engine**

A constraint-driven negative-space engine that models how live pressure removes available possibility from a continuous spatial field, evolves that pressure over time, and supports counterfactual replay to prove what would have changed if a single constraint were different.

---

## Core Thesis

The product is **surviving possibility**, not chosen action.

Most simulation systems model what agents *do*. VoidLine models what agents *could still do* — and what removed the rest. The action is only the visible consequence. The real object is the shape of remaining possibility and the constraints that carved it.

**Three layers:**

1. **Raw court space** — continuous spatial field in ISO4D-aligned coordinates (feet from basket center)
2. **Negative-space transform** — six constraint categories carve away possibility
3. **Action selection over survivors** — scoring happens only over what survived

---

## What It Computes

At any moment, VoidLine answers:

- How much usable possibility remains?
- Where is it located?
- What removed the rest, and why?
- How does that change when a constraint expires or appears?
- What would have been different if one constraint had not changed?

---

## Constraint Categories

Every constraint is a function that removes a region of possibility from the action space:

| Category | What it removes | Example |
|---|---|---|
| **Spatial** | Physical court regions | Defender denial area, blocked lane |
| **Temporal** | Time windows | Shot clock pressure, help defender arriving |
| **Kinematic** | Movement corridors | Overcommitted momentum, fatigue |
| **Role** | Actions invalid for current role | Not the ball handler, screener must hold |
| **Perceptual** | Actions requiring unseen information | Target behind vision cone |
| **Risk** | Actions exceeding risk thresholds | Contested shot above turnover limit |

The possibility field is what survives their union.

---

## Example: Pick-and-Roll at the Screen Point

Seven constraints active at t=0.0 — on-ball defender shading left, help defender in paint, shot clock at 14s, rightward momentum commitment, screen not yet set, weak-side blind spot, contested pull-up above risk threshold.

**Result:** 90% of action space removed. 10% surviving possibility.

At t=1.2s, three constraints expire simultaneously (help defender rotates out, screen arrives, momentum decays):

**Result:** Pressure drops from 90% to 45%. The drive corridor recovers from 86% viability to 97%.

The system names the constraint that blocked each corridor segment and attributes exactly how much space reopened when it expired.

```
t=0.0s
  drive_left       viability=86%   blocked by: help_defender_paint
  pullup_right     viability=100%
  reset_left       viability=100%
  kick_corner      viability=100%
  pocket_pass      viability=100%

t=1.2s
  drive_left       viability=97%   (help defender expired)
  pullup_right     viability=100%
  reset_left       viability=100%
  kick_corner      viability=100%
  pocket_pass      viability=100%
```

### Counterfactual: What If the Help Defender Had Not Rotated?

Fork the baseline at t=0. Replace `help_defender_paint` (expires t=1.2) with a sustained version that never expires. Rerun the engine over the same timestamps.

- **Baseline:** help expires at t=1.2, pressure drops, `drive_left` reopens to 97% viability
- **Replay:** help persists, pressure stays higher, `drive_left` remains degraded
- **First divergence:** occurs at the baseline expiration point (~t=1.2)
- **Summary:** `drive_left` is the most affected corridor; field pressure stays 20+ percentage points higher in the replay

The replay system compares aligned timelines at four levels: field volume, space pressure, corridor viability, and event stream. It identifies the first tick where the two timelines diverge and attributes the divergence to specific constraint changes.

---

## Architecture

```
Core (the product):
    field/          spatial primitives, continuous court model
    constraints/    six carving categories with temporal dynamics
    envelope/       possibility field computation, removal attribution, diff

Consumer (downstream of core):
    rail/           authored topology, corridor viability projection
    engine/         tick loop — time-evolving constraint fields, event detection
    replay/         single-fork counterfactual with aligned divergence analysis
    agents/         archetypes score over surviving space (planned)
    memory/         envelope-keyed tabular memory (planned)
```

---

## Milestones

| Tag | What it contains |
|---|---|
| **v0.1.0-foundation** | Field, constraints, envelope, rail viability, PNR scenario |
| **v0.2.0-temporal-replay** | Tick engine, event detection, replay, aligned divergence analysis |

---

## Implemented

- `Point`, `Circle`, `Cone`, `Corridor`, `TimeWindow` — spatial primitives (ISO4D-aligned)
- Six constraint types with temporal dynamics (static, sustained, transient, decaying)
- `PossibilityField` — surviving volume, space pressure, collapse detection, removal attribution by source
- `FieldDiff` — counterfactual comparison via removed/reopened space
- `RailGraph` — JSON-schema-validated topology loader with node types and role filtering
- `CorridorViability` — sampling-based projection of negative space onto corridor geometry with per-constraint blocker attribution
- `TickEngine` — advances time in discrete steps, recomputes field and viabilities each tick, emits events when constraints expire/activate or corridors open/collapse
- `replay_from_tick()` — forks a baseline timeline at one tick, applies constraint changes with deterministic precedence, reruns at exact baseline timestamps, compares aligned timelines at field/corridor/event level
- `ConstraintChanges` — remove/add/replace with explicit precedence rules and collision detection
- `ReplayResult` — per-tick divergence records, first divergence index and timestamp, aggregate summary with max corridor deltas
- PNR scenario (`scenarios/pnr_basic.json`) — 7 nodes, 7 edges, 5 reads off the screen point
- 72 tests passing

## Not Yet Implemented

- Agent archetypes responding differently to the same surviving space
- Envelope-signature-keyed memory (compact fingerprint of possibility geometry)

These are designed but intentionally deferred until the engine is proven.

---

## Running

```bash
python -m venv .venv
source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest -v
```

Requires Python 3.11+.

---

## Coordinate System

Matches [ISO4D](https://github.com/jmxisnext) convention:

| Property | Value |
|---|---|
| Origin | Center of attacking hoop (basket) |
| Units | Feet |
| +X | Toward baseline (behind hoop) |
| -X | Toward mid-court |
| +Y | Right wing |
| -Y | Left wing |

---

## Design Principles

- **Negative space is the product.** Rails give structure. Constraints carve space. Decisions are evidence.
- **Constraints compose via union.** Adding constraints reduces possibility — it doesn't increase computational complexity.
- **Attribution over aggregation.** Every removal is named, sourced, and measured.
- **Deterministic and inspectable.** Same inputs, same field. Every corridor viability can be traced to specific constraint boundaries.
- **Replay proves causation.** Aligned divergence analysis shows exactly where and why two timelines split.
