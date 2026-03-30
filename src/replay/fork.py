"""
replay.fork
============
Fork a baseline timeline at a given tick and rerun with altered constraints.

Preconditions are validated before any work is done.  The replay engine
receives a fully independent (deepcopied) constraint list — baseline
state is never mutated.
"""

from __future__ import annotations

from typing import Optional

from src.constraints.types import Constraint
from src.engine.tick import Snapshot, TickEngine
from src.rail.graph import RailGraph
from src.replay.models import ConstraintChanges


# ---------------------------------------------------------------------------
# Precondition validation
# ---------------------------------------------------------------------------

class ReplayPreconditionError(Exception):
    """A precondition for replay was not met."""


def _validate_preconditions(
    baseline: list[Snapshot],
    graph: RailGraph,
    constraints: list[Constraint],
    fork_tick: int,
    changes: ConstraintChanges,
    node_id: str,
) -> None:
    if not baseline:
        raise ReplayPreconditionError("Baseline timeline is empty.")

    if fork_tick < 0 or fork_tick >= len(baseline):
        raise ReplayPreconditionError(
            f"fork_tick={fork_tick} out of range [0, {len(baseline) - 1}]."
        )

    if node_id not in graph.nodes:
        raise ReplayPreconditionError(
            f"node_id='{node_id}' not found in graph "
            f"(available: {sorted(graph.nodes.keys())})."
        )

    # Validate that removed/replaced names exist in the constraint set
    constraint_names = {c.name for c in constraints}
    for name in changes.remove:
        if name not in constraint_names:
            raise ReplayPreconditionError(
                f"ConstraintChanges.remove references unknown constraint '{name}'."
            )
    for name in changes.replace:
        if name not in constraint_names:
            raise ReplayPreconditionError(
                f"ConstraintChanges.replace references unknown constraint '{name}'."
            )


# ---------------------------------------------------------------------------
# Fork + run
# ---------------------------------------------------------------------------

def run_replay(
    baseline: list[Snapshot],
    graph: RailGraph,
    constraints: list[Constraint],
    fork_tick: int,
    changes: ConstraintChanges,
    node_id: str,
    role: Optional[str] = None,
    sample_spacing: float = 0.5,
) -> list[Snapshot]:
    """
    Create a replay engine with altered constraints and tick it at
    every timestamp in ``baseline[fork_tick:]``.

    Returns the replay snapshot list, aligned 1:1 with the baseline
    segment.
    """
    _validate_preconditions(baseline, graph, constraints, fork_tick, changes, node_id)

    agent_id = baseline[fork_tick].field.agent_id
    altered = changes.apply(constraints)

    engine = TickEngine(
        graph=graph,
        constraints=altered,
        agent_id=agent_id,
        node_id=node_id,
        role=role,
        sample_spacing=sample_spacing,
    )

    replay_timeline: list[Snapshot] = []
    for snap in baseline[fork_tick:]:
        replay_timeline.append(engine.tick(snap.timestamp))

    return replay_timeline
