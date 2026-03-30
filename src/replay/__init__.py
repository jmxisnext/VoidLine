"""
replay — Counterfactual analysis via single-fork constraint diff.

Fork a baseline timeline at one tick, alter the constraint set,
rerun the engine, and compare the two aligned timelines to surface
where and why they diverge.
"""

from __future__ import annotations

from typing import Optional

from src.constraints.types import Constraint
from src.engine.tick import Snapshot
from src.rail.graph import RailGraph
from src.replay.compare import compare_timelines, compute_summary
from src.replay.fork import ReplayPreconditionError, run_replay
from src.replay.models import (
    CORRIDOR_CHANGE_THRESHOLD,
    VIABILITY_EPSILON,
    VOLUME_EPSILON,
    ConstraintChanges,
    ReplayResult,
    ReplaySummary,
    TickDivergence,
)

__all__ = [
    "CORRIDOR_CHANGE_THRESHOLD",
    "VIABILITY_EPSILON",
    "VOLUME_EPSILON",
    "ConstraintChanges",
    "ReplayPreconditionError",
    "ReplayResult",
    "ReplaySummary",
    "TickDivergence",
    "replay_from_tick",
]


def replay_from_tick(
    baseline: list[Snapshot],
    graph: RailGraph,
    constraints: list[Constraint],
    fork_tick: int,
    changes: ConstraintChanges,
    node_id: str,
    role: Optional[str] = None,
    sample_spacing: float = 0.5,
) -> ReplayResult:
    """
    Fork a baseline timeline at ``fork_tick``, apply ``changes`` to
    the constraint set, rerun the engine over the same timestamps,
    and compare the two timelines.

    Parameters
    ----------
    baseline : list[Snapshot]
        The original timeline produced by ``TickEngine.run()``.
    graph : RailGraph
        The rail topology (shared, read-only).
    constraints : list[Constraint]
        The **full** original constraint set (not just those active
        at fork time — inactive constraints with future windows
        must be present).
    fork_tick : int
        Index into *baseline* at which to fork.
    changes : ConstraintChanges
        Constraint diff to apply at fork time.
    node_id : str
        Node in *graph* to compute corridor viabilities from.
    role : str, optional
        Role filter for outgoing edges.
    sample_spacing : float
        Corridor sample spacing in feet.

    Returns
    -------
    ReplayResult
        Contains both timeline segments, per-tick divergences,
        first divergence index, and aggregate summary.

    Raises
    ------
    ReplayPreconditionError
        If any precondition is violated (empty baseline, invalid
        fork_tick, unknown node_id, unknown constraint names in changes).
    """
    baseline_segment = baseline[fork_tick:]
    replay_segment = run_replay(
        baseline, graph, constraints, fork_tick, changes,
        node_id, role, sample_spacing,
    )
    divergences, first_div = compare_timelines(baseline_segment, replay_segment)
    summary = compute_summary(divergences, first_div)

    return ReplayResult(
        baseline_segment=baseline_segment,
        replay_segment=replay_segment,
        divergences=divergences,
        first_divergence_index=first_div,
        changes=changes,
        summary=summary,
    )
