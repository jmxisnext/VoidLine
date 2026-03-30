"""
replay.models
=============
Data types for the replay system.

Replay forks a baseline timeline at a single tick, applies constraint
changes, reruns the engine, and compares the two aligned timelines to
surface divergence.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

from src.constraints.types import Constraint
from src.engine.tick import TickEvent


# ---------------------------------------------------------------------------
# Thresholds — named constants for divergence detection
# ---------------------------------------------------------------------------

VOLUME_EPSILON: float = 1e-6
"""Minimum |volume_delta| to count as divergent."""

VIABILITY_EPSILON: float = 1e-6
"""Minimum |viability_delta| per corridor to count as divergent."""

CORRIDOR_CHANGE_THRESHOLD: float = 0.05
"""Minimum |viability_delta| for a corridor to appear in summary.corridors_changed."""


# ---------------------------------------------------------------------------
# ConstraintChanges — the replay diff
# ---------------------------------------------------------------------------

@dataclass
class ConstraintChanges:
    """
    Describes how the constraint set differs between baseline and replay.

    Precedence rules (deterministic, applied in order):
      1. ``remove`` — drop any constraint whose name is in this list.
      2. ``replace`` — if a surviving constraint's name matches a key,
         substitute the replacement.  A name that appears in both
         ``remove`` **and** ``replace`` is **removed** (remove wins).
      3. ``add`` — append new constraints.  An ``add`` whose name
         collides with an existing (non-removed, non-replaced) constraint
         raises ``ValueError`` during ``apply()``.
    """

    remove: list[str] = field(default_factory=list)
    add: list[Constraint] = field(default_factory=list)
    replace: dict[str, Constraint] = field(default_factory=dict)

    def apply(self, constraints: list[Constraint]) -> list[Constraint]:
        """
        Produce a new constraint list with changes applied.

        Every returned constraint is a **deepcopy** — no shared references
        with the input list.

        Raises ``ValueError`` on name collisions between ``add`` and
        surviving constraints.
        """
        remove_names = set(self.remove)

        # Step 1 + 2: filter removed, apply replacements
        result: list[Constraint] = []
        for c in constraints:
            if c.name in remove_names:
                continue
            if c.name in self.replace:
                # remove wins over replace if name is in both
                if c.name in remove_names:
                    continue
                result.append(copy.deepcopy(self.replace[c.name]))
            else:
                result.append(copy.deepcopy(c))

        # Step 3: add new constraints (collision check)
        surviving_names = {c.name for c in result}
        for c in self.add:
            if c.name in surviving_names:
                raise ValueError(
                    f"ConstraintChanges.add collision: '{c.name}' already exists "
                    f"in the surviving constraint set. Use 'replace' to override."
                )
            result.append(copy.deepcopy(c))

        return result

    @property
    def is_empty(self) -> bool:
        return not self.remove and not self.add and not self.replace


# ---------------------------------------------------------------------------
# Per-tick divergence
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TickDivergence:
    """
    Comparison of one aligned tick between baseline and replay.

    Fork-tick event semantics
    -------------------------
    At the fork tick, the replay engine has no ``_prev`` snapshot, so it
    emits no events.  If the baseline snapshot at the fork tick carries
    events (because the baseline engine *did* have a previous tick),
    those appear as ``baseline_only_events``.  This is **accurate**:
    those transitions occurred in the baseline's history but have no
    counterpart in the replay's frame of reference.  Event divergence
    at the fork tick reflects this framing difference, not a real
    behavioural split.  Meaningful event divergence starts at
    ``fork_tick + 1``.
    """

    timestamp: float
    volume_delta: float
    pressure_delta: float
    viability_deltas: dict[str, float]
    baseline_only_events: list[TickEvent]
    replay_only_events: list[TickEvent]

    @property
    def is_divergent(self) -> bool:
        return (
            abs(self.volume_delta) > VOLUME_EPSILON
            or any(abs(d) > VIABILITY_EPSILON for d in self.viability_deltas.values())
            or bool(self.baseline_only_events)
            or bool(self.replay_only_events)
        )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReplaySummary:
    """Aggregate metrics over the full replay comparison."""

    fork_timestamp: float
    end_timestamp: float
    total_ticks: int
    divergent_ticks: int
    first_divergence_timestamp: Optional[float]
    max_volume_delta: float
    max_pressure_delta: float
    corridors_changed: list[str]
    max_corridor_delta_by_edge: dict[str, float]


# ---------------------------------------------------------------------------
# Top-level result
# ---------------------------------------------------------------------------

@dataclass
class ReplayResult:
    """
    Complete output of a single-fork replay.

    Contains both timelines (aligned by timestamp), per-tick divergence
    records, and an aggregate summary.
    """

    baseline_segment: list  # list[Snapshot] — avoid circular import
    replay_segment: list
    divergences: list[TickDivergence]
    first_divergence_index: Optional[int]
    changes: ConstraintChanges
    summary: ReplaySummary
