# Portfolio Positioning — VoidLine

## Anchor Alignment

This project is the core deliverable of **Anchor 2 (Voidline — Feasibility)** in a portfolio of gameplay AI simulation systems.

| Anchor | Focus | Status |
|---|---|---|
| 1 — ISO4D | Extraction: raw input to structured spatial state | In progress |
| **2 — Voidline** | **Feasibility: what is allowed under constraints** | **v0.3 complete** |
| 3 — Decision Window | Timing: is the action still viable at execution? | v0.1 complete |

The three anchors form a decision pipeline: ISO4D provides state, Voidline defines the feasibility space, Decision Window evaluates whether a specific action survives through execution.

## Target Problem

Sports game AI systems decide what an agent should do — but they rarely model *why other options were removed*. When a help defender rotates into the paint, the driving lane doesn't just become "worse" — the space is removed. The constraint is the product, not the decision.

VoidLine makes this removal explicit: each constraint is named, sourced, measured, and attributed. When the constraint changes (defender rotates out, momentum decays, screen arrives), the reopened space is tracked and the causal chain is preserved through counterfactual replay.

## Resume Bullets

- Built a constraint-driven possibility field engine that models how defensive pressure, kinematic limits, and perceptual constraints remove actions from an agent's space — with per-constraint removal attribution
- Demonstrated that one help defender's rotation changes space pressure by 20 percentage points and opens a primary driving lane, proven through deterministic counterfactual replay with aligned timeline divergence analysis
- Validated across two play topologies (pick-and-roll star, transition cascade) with different temporal profiles (monotonic vs non-monotonic pressure), proving the engine generalizes beyond a single scenario

## Project Summary (Short)

> Constraint-driven possibility field engine for sports gameplay AI. Models how defensive pressure, kinematic commitment, and perceptual limits remove available actions from an agent's space. Supports counterfactual replay — proving that one help defender's rotation creates a 20% pressure swing and opens a driving lane. Validated across two play topologies with 122 tests.

## Why This Matters to Sports Gameplay AI

### The problem is fundamental
Every play in basketball involves constraints removing options: the on-ball defender removes one side, help defense removes driving lanes, momentum removes change-of-direction, the shot clock removes waiting. Current systems evaluate these implicitly. VoidLine makes them explicit, measurable, and attributable.

### The solution enables better decisions
If the AI knows *what removed each option*, it can reason about what happens when those constraints change. When the help defender rotates out, the system doesn't just re-evaluate — it knows exactly which space reopened and why. This is the difference between reactive and causal decision-making.

### It demonstrates the right skills
- **Constraint-based reasoning** — six categories of removal, each with temporal dynamics
- **Spatial modeling** — continuous court field projected onto discrete topology via corridor viability
- **Counterfactual analysis** — fork-and-compare with aligned divergence detection
- **Systems architecture** — clean separation between field (core), topology (rail), time (engine), and analysis (replay)
- **Generalization** — two topologies, two temporal profiles, same engine

### Connection to Decision Window Engine
VoidLine answers "what is feasible?" Decision Window answers "will it still be feasible when executed?" Together they form the feasibility-through-time layer that sits between state extraction (ISO4D) and action selection. A pass that VoidLine marks as feasible can still be killed by animation delay — Decision Window catches that. A pass that VoidLine marks as infeasible never reaches Decision Window at all.
