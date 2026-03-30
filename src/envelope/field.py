"""
envelope.field
==============
Possibility field computation and removal attribution.

The PossibilityField is the primary artifact of VoidLine.
It answers: how much usable possibility remains, where is it located,
and what removed the rest?

Current implementation: sampling-based. Discretize the action space
into a grid, evaluate each cell against all active constraints,
produce a survival map. Simple, correct, debuggable. Replace with
computational geometry later if needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.field.space_model import Point, Circle, Cone
from src.constraints.types import Constraint


# ---------------------------------------------------------------------------
# Removal record — attribution of carved space
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Removal:
    """One constraint's contribution to removed space."""

    constraint_name: str
    source: str
    volume_removed: float  # fraction of total space this constraint removed


# ---------------------------------------------------------------------------
# Possibility Field
# ---------------------------------------------------------------------------

@dataclass
class PossibilityField:
    """
    The surviving possibility space after all constraints are applied.

    This is VoidLine's primary artifact — not a decision, not a score,
    but a map of what remains possible and what was taken away.
    """

    agent_id: str
    timestamp: float
    active_constraints: list[Constraint]
    removals: list[Removal] = field(default_factory=list)
    total_volume: float = 1.0
    _surviving_volume: Optional[float] = None

    @property
    def surviving_volume(self) -> float:
        """
        Fraction of action space that survives all constraints.

        Naive: total - sum(removals), clamped to [0, total].
        Geometric union version will replace this.
        """
        if self._surviving_volume is not None:
            return self._surviving_volume
        removed = sum(r.volume_removed for r in self.removals)
        return max(0.0, self.total_volume - removed)

    @property
    def space_pressure(self) -> float:
        """
        How constrained is this agent right now?
        0.0 = fully free, 1.0 = completely trapped.
        """
        return 1.0 - (self.surviving_volume / self.total_volume)

    @property
    def is_collapsed(self) -> bool:
        """Possibility field has collapsed — agent is near-trapped."""
        return self.surviving_volume < 0.05

    def dominant_removal(self) -> Optional[Removal]:
        """Which single constraint removed the most space?"""
        if not self.removals:
            return None
        return max(self.removals, key=lambda r: r.volume_removed)

    def removals_by_source(self) -> dict[str, float]:
        """Total removed volume grouped by constraint source."""
        by_source: dict[str, float] = {}
        for r in self.removals:
            by_source[r.source] = by_source.get(r.source, 0.0) + r.volume_removed
        return by_source


def compute_field(
    agent_id: str,
    timestamp: float,
    constraints: list[Constraint],
) -> PossibilityField:
    """
    Compute the possibility field for an agent at a given moment.

    Evaluates all active constraints and produces a PossibilityField
    with per-constraint removal attribution.
    """
    active = [c for c in constraints if c.is_active(timestamp)]

    removals = [
        Removal(
            constraint_name=c.name,
            source=c.source.value,
            volume_removed=c.pressure,
        )
        for c in active
    ]

    return PossibilityField(
        agent_id=agent_id,
        timestamp=timestamp,
        active_constraints=active,
        removals=removals,
    )


# ---------------------------------------------------------------------------
# Field diff — counterfactual tool
# ---------------------------------------------------------------------------

@dataclass
class FieldDiff:
    """
    Compare two possibility fields.

    Answers: what constraint changed, and how much space did it
    add or remove? You don't compare decisions. You compare removed space.
    """

    before: PossibilityField
    after: PossibilityField

    @property
    def volume_delta(self) -> float:
        """Positive = space opened (more options). Negative = space collapsed."""
        return self.after.surviving_volume - self.before.surviving_volume

    @property
    def pressure_delta(self) -> float:
        """Positive = more pressure. Negative = pressure released."""
        return self.after.space_pressure - self.before.space_pressure

    @property
    def new_constraints(self) -> list[Constraint]:
        """Constraints that appeared."""
        before_names = {c.name for c in self.before.active_constraints}
        return [c for c in self.after.active_constraints if c.name not in before_names]

    @property
    def removed_constraints(self) -> list[Constraint]:
        """Constraints that disappeared."""
        after_names = {c.name for c in self.after.active_constraints}
        return [c for c in self.before.active_constraints if c.name not in after_names]

    @property
    def space_opened_by(self) -> list[Removal]:
        """Removals that existed before but not after — space that reopened."""
        after_names = {r.constraint_name for r in self.after.removals}
        return [r for r in self.before.removals if r.constraint_name not in after_names]

    @property
    def space_closed_by(self) -> list[Removal]:
        """Removals that exist after but not before — new space taken away."""
        before_names = {r.constraint_name for r in self.before.removals}
        return [r for r in self.after.removals if r.constraint_name not in before_names]
