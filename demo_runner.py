#!/usr/bin/env python3
"""
VoidLine Demo Runner

Runs the PNR pick-and-roll scenario and prints:
  1. Constraint timeline — what's active, what expires, what it removes
  2. Corridor viability at key moments
  3. Counterfactual comparison — help defender rotates vs stays

Usage:
    python demo_runner.py
"""

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.constraints.types import (
    ConstraintDynamics, ConstraintSource, Stability,
    SpatialConstraint,
)
from src.engine.tick import TickEngine
from src.rail.graph import load_railgraph
from src.replay import ConstraintChanges, replay_from_tick
from examples.help_defender_replay import pnr_constraints


SCENARIOS_DIR = Path(__file__).parent / "scenarios"
AGENT_ID = "PG_01"


def fmt_pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def print_section(title: str):
    print()
    print(f"  {title}")
    print(f"  {'-' * len(title)}")


def main():
    graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
    constraints = pnr_constraints()

    engine = TickEngine(
        graph, constraints, AGENT_ID, "screen_point", role="ball_handler",
    )
    timeline = engine.run(duration=2.0, dt=0.1)

    # ── Header ──
    print()
    print("=" * 70)
    print("  VoidLine v0.3 — PNR Scenario Demo")
    print("=" * 70)

    # ── 1. Constraint overview ──
    print_section("Active Constraints at t=0.0")
    t0 = timeline[0]
    for c in t0.field.active_constraints:
        print(f"    {c.name:<32} source={c.source.value:<10} vol={fmt_pct(c.volume):>4}"
              f"  [{c.dynamics.stability.value}]")
    print(f"\n    Space pressure: {fmt_pct(t0.field.space_pressure)}")
    print(f"    Surviving volume: {fmt_pct(t0.field.surviving_volume)}")

    # ── 2. Timeline events ──
    print_section("Key Events")
    for snap in timeline:
        for ev in snap.events:
            print(f"    t={snap.timestamp:.1f}s  {ev.kind.value:<24} {ev.name}")

    # ── 3. Corridor viability at key moments ──
    moments = [
        ("t=0.0 (initial)", 0),
        ("t=0.8 (screen set)", 8),
        ("t=1.2 (help rotates)", 12),
        ("t=2.0 (late)", 20),
    ]
    print_section("Corridor Viability Over Time")
    # Header
    corridor_ids = [v.edge_id for v in timeline[0].viabilities]
    header = f"    {'Moment':<24}" + "".join(f"{cid:>14}" for cid in corridor_ids)
    print(header)
    print(f"    {'-' * (len(header) - 4)}")
    for label, idx in moments:
        snap = timeline[idx]
        viab_map = {v.edge_id: v.viability for v in snap.viabilities}
        row = f"    {label:<24}" + "".join(
            f"{fmt_pct(viab_map.get(cid, 0)):>14}" for cid in corridor_ids
        )
        print(row)

    # ── 4. The counterfactual ──
    print_section("Counterfactual: What If Help Defender Stays?")

    help_original = next(c for c in constraints if c.name == "help_defender_paint")
    help_persistent = SpatialConstraint(
        name="help_defender_paint",
        source=help_original.source,
        dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
        boundary=help_original.boundary,
        volume=help_original.volume,
        agent_id=help_original.agent_id,
    )
    changes = ConstraintChanges(replace={"help_defender_paint": help_persistent})

    result = replay_from_tick(
        timeline, graph, constraints,
        fork_tick=0, changes=changes,
        node_id="screen_point", role="ball_handler",
    )

    # Show pressure comparison at divergence
    print(f"    First divergence: t={result.summary.first_divergence_timestamp:.1f}s")
    print()
    print(f"    {'Time':<10} {'Baseline':>12} {'Help Stays':>12} {'Delta':>10}")
    print(f"    {'-' * 44}")

    for i, (b, r) in enumerate(zip(result.baseline_segment, result.replay_segment)):
        if b.timestamp < 1.0:
            continue
        bp = b.field.space_pressure
        rp = r.field.space_pressure
        delta = rp - bp
        marker = " <-- diverges" if abs(delta) > 0.001 and b.timestamp <= 1.3 else ""
        print(f"    t={b.timestamp:<5.1f} {fmt_pct(bp):>12} {fmt_pct(rp):>12} {'+' if delta >= 0 else ''}{fmt_pct(delta):>9}{marker}")

    # Drive left comparison
    print()
    drive_baseline_late = None
    drive_replay_late = None
    for snap in result.baseline_segment:
        if snap.timestamp >= 1.5:
            for v in snap.viabilities:
                if v.edge_id == "drive_left":
                    drive_baseline_late = v.viability
            break
    for snap in result.replay_segment:
        if snap.timestamp >= 1.5:
            for v in snap.viabilities:
                if v.edge_id == "drive_left":
                    drive_replay_late = v.viability
            break

    if drive_baseline_late is not None and drive_replay_late is not None:
        print(f"    drive_left at t=1.5s:")
        print(f"      Baseline (help rotates): {fmt_pct(drive_baseline_late)}")
        print(f"      Replay (help stays):     {fmt_pct(drive_replay_late)}")

    # ── Summary ──
    print()
    print("=" * 70)
    print("  Key result: When help defender rotates out at t=1.2s, pressure")
    print(f"  drops from {fmt_pct(timeline[11].field.space_pressure)} to"
          f" {fmt_pct(timeline[12].field.space_pressure)} and drive_left opens.")
    print("  If help stays, that driving lane never opens.")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
