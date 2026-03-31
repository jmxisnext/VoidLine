#!/usr/bin/env python3
"""
VoidLine Hero Visualization — Help Defender Counterfactual

Two-panel figure:
  Left:  Help defender rotates out at t=1.2s -> pressure drops, drive opens
  Right: Help defender stays -> pressure holds, drive stays degraded

Plus a pressure-over-time comparison chart.

Saved to help_defender_flip.png
"""

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

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


def run_scenarios():
    graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
    constraints = pnr_constraints()

    engine = TickEngine(
        graph, constraints, AGENT_ID, "screen_point", role="ball_handler",
    )
    baseline = engine.run(duration=2.0, dt=0.1)

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
        baseline, graph, constraints,
        fork_tick=0, changes=changes,
        node_id="screen_point", role="ball_handler",
    )

    return graph, baseline, result


def draw_court_scenario(ax, title, snap, graph, show_help=True, highlight_drive=True):
    """Draw a simplified court view with nodes, corridors, and constraint zones."""
    ax.set_xlim(-25, 5)
    ax.set_ylim(-15, 25)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel("x (ft from hoop)")
    ax.set_ylabel("y (ft from hoop)")

    # Court outline (simplified half court)
    court = plt.Rectangle((-47, -25), 47, 50, fill=False, edgecolor="#ccc",
                          linewidth=1, linestyle="--")
    ax.add_patch(court)

    # Paint
    paint = plt.Rectangle((-19, -8), 19, 16, fill=True, facecolor="#FFF3E0",
                          edgecolor="#FFB74D", linewidth=1, alpha=0.4)
    ax.add_patch(paint)

    # 3pt arc (partial)
    arc = mpatches.Arc((0, 0), 47.5, 47.5, angle=0, theta1=90, theta2=270,
                       edgecolor="#ccc", linewidth=1, linestyle=":")
    ax.add_patch(arc)

    # Rim
    ax.plot(0, 0, "o", color="#333", markersize=8, zorder=10)
    ax.annotate("Rim", (0, 0), textcoords="offset points", xytext=(8, -5),
                fontsize=7, color="#666")

    # Help defender zone
    if show_help:
        help_zone = plt.Circle((0, 1.5), 2.5, facecolor="#F44336", alpha=0.2,
                               edgecolor="#F44336", linewidth=2, linestyle="--")
        ax.add_patch(help_zone)
        ax.annotate("Help Defender\n(paint)", (0, 1.5), ha="center",
                    fontsize=8, color="#F44336", fontweight="bold")

    # On-ball defender zone (always present)
    onball_zone = plt.Circle((-1.5, -6), 2.0, facecolor="#FF9800", alpha=0.15,
                             edgecolor="#FF9800", linewidth=1.5, linestyle="--")
    ax.add_patch(onball_zone)
    ax.annotate("On-ball\ndefender", (-1.5, -6), ha="center",
                fontsize=7, color="#FF9800")

    # Draw corridors from the scenario
    viab_map = {v.edge_id: v.viability for v in snap.viabilities}

    for edge in graph.outgoing("screen_point", role="ball_handler"):
        pts = [(wp.x, wp.y) for wp in edge.corridor.waypoints]
        xs, ys = zip(*pts)
        viab = viab_map.get(edge.id, 1.0)

        if edge.id == "drive_left" and highlight_drive:
            color = "#4CAF50" if viab > 0.9 else "#FF9800" if viab > 0.5 else "#F44336"
            lw = 3
            alpha = 0.9
        else:
            color = "#2196F3"
            lw = 1.5
            alpha = 0.5

        ax.plot(xs, ys, color=color, linewidth=lw, alpha=alpha, zorder=3)
        # Arrow at end
        ax.annotate("", xy=(xs[-1], ys[-1]),
                    xytext=(xs[-2], ys[-2]),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw * 0.7),
                    zorder=3)
        # Label
        mid = len(pts) // 2
        label = f"{edge.id}\n{viab * 100:.0f}%"
        ax.annotate(label, (xs[mid], ys[mid]), textcoords="offset points",
                    xytext=(10, 5), fontsize=7, color=color, fontweight="bold")

    # Draw nodes
    for nid, node in graph.nodes.items():
        if node.node_type == "start":
            marker, color, size = "o", "#4CAF50", 10
        elif node.is_junction:
            marker, color, size = "D", "#FF9800", 9
        elif node.is_terminal:
            marker, color, size = "s", "#9E9E9E", 7
        else:
            continue
        ax.plot(node.position.x, node.position.y, marker,
                color=color, markersize=size, zorder=5)

    # Result box
    pressure = snap.field.space_pressure
    surviving = snap.field.surviving_volume
    if pressure < 0.5:
        box_color = "#4CAF50"
        label = "SPACE OPEN"
    else:
        box_color = "#F44336"
        label = "UNDER PRESSURE"

    props = dict(boxstyle="round,pad=0.4", facecolor=box_color, alpha=0.15,
                 edgecolor=box_color, linewidth=2)
    ax.text(0.5, 0.97,
            f"{label}\n"
            f"Pressure: {pressure * 100:.0f}% | "
            f"Surviving: {surviving * 100:.0f}%",
            transform=ax.transAxes, fontsize=9, verticalalignment="top",
            horizontalalignment="center", bbox=props, color=box_color,
            fontweight="bold")

    ax.grid(True, alpha=0.15)


def main():
    graph, baseline, result = run_scenarios()

    # Pick snapshots at t=1.5 (after divergence at t=1.2)
    baseline_snap = None
    replay_snap = None
    for snap in baseline:
        if snap.timestamp >= 1.5:
            baseline_snap = snap
            break
    for snap in result.replay_segment:
        if snap.timestamp >= 1.5:
            replay_snap = snap
            break

    # ── Figure 1: Two-panel court view ──
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    fig.suptitle("VoidLine: Help Defender Counterfactual (t=1.5s)",
                 fontsize=14, fontweight="bold", y=0.98)

    draw_court_scenario(ax1, "Baseline: Help Rotates Out",
                        baseline_snap, graph, show_help=False, highlight_drive=True)
    draw_court_scenario(ax2, "Counterfactual: Help Stays in Paint",
                        replay_snap, graph, show_help=True, highlight_drive=True)

    fig.text(0.5, 0.01,
             "Same play. Same ball handler. Same on-ball defender. "
             "One variable: does help rotate out of the paint?",
             ha="center", fontsize=11, style="italic", color="#555")

    plt.tight_layout(rect=[0, 0.04, 1, 0.95])
    plt.savefig("J:/projects/VoidLine/help_defender_flip.png", dpi=150,
                bbox_inches="tight", facecolor="white")
    print("Saved: help_defender_flip.png")
    plt.close()

    # ── Figure 2: Pressure over time ──
    fig2, ax = plt.subplots(figsize=(10, 5))

    times_b = [s.timestamp for s in baseline]
    pressure_b = [s.field.space_pressure * 100 for s in baseline]

    times_r = [s.timestamp for s in result.replay_segment]
    pressure_r = [s.field.space_pressure * 100 for s in result.replay_segment]

    ax.plot(times_b, pressure_b, "o-", color="#4CAF50", linewidth=2,
            markersize=4, label="Baseline (help rotates)")
    ax.plot(times_r, pressure_r, "s-", color="#F44336", linewidth=2,
            markersize=4, label="Counterfactual (help stays)")

    # Mark divergence
    ax.axvline(x=1.2, color="#999", linestyle="--", linewidth=1)
    ax.annotate("Help defender\nrotates out (t=1.2s)",
                xy=(1.2, 55), fontsize=9, ha="center", color="#666")

    # Fill the gap
    # Align lengths for fill_between
    min_len = min(len(times_b), len(times_r))
    if len(times_b) >= len(times_r):
        fill_t = times_r[:min_len]
        fill_b = pressure_b[:min_len]
        fill_r = pressure_r[:min_len]
    else:
        fill_t = times_b[:min_len]
        fill_b = pressure_b[:min_len]
        fill_r = pressure_r[:min_len]

    ax.fill_between(fill_t, fill_b, fill_r,
                    alpha=0.15, color="#F44336", where=[r > b for b, r in zip(fill_b, fill_r)])

    ax.set_xlabel("Time (seconds)", fontsize=11)
    ax.set_ylabel("Space Pressure (%)", fontsize=11)
    ax.set_title("Pressure Over Time: Help Defender Impact",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="upper right", fontsize=10)
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.2)

    # Annotate the delta
    ax.annotate("+20% pressure\nwhen help stays",
                xy=(1.6, 65), xytext=(1.8, 80),
                arrowprops=dict(arrowstyle="->", color="#F44336"),
                fontsize=10, color="#F44336", fontweight="bold")

    plt.tight_layout()
    plt.savefig("J:/projects/VoidLine/pressure_timeline.png", dpi=150,
                bbox_inches="tight", facecolor="white")
    print("Saved: pressure_timeline.png")
    plt.close()


if __name__ == "__main__":
    main()
