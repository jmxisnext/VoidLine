"""
engine.tick
===========
Tick-loop orchestrator for time-evolving constraint fields.

Advances time in discrete steps, recomputes the possibility field and
corridor viabilities each tick, and emits events when the field changes
materially (constraint expired, corridor opened/collapsed).

Usage::

    engine = TickEngine(graph, constraints, agent_id="PG_01", node_id="screen_point")
    timeline = engine.run(duration=3.0, dt=0.1)
    for snap in timeline:
        print(snap.timestamp, snap.field.space_pressure, snap.events)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.constraints.types import Constraint
from src.envelope.field import PossibilityField, compute_field
from src.rail.graph import RailGraph, CorridorViability


# ---------------------------------------------------------------------------
# Events — what changed this tick
# ---------------------------------------------------------------------------

class EventKind(Enum):
    CONSTRAINT_EXPIRED = "constraint_expired"
    CONSTRAINT_ACTIVATED = "constraint_activated"
    CORRIDOR_OPENED = "corridor_opened"
    CORRIDOR_COLLAPSED = "corridor_collapsed"
    FIELD_COLLAPSED = "field_collapsed"


@dataclass(frozen=True)
class TickEvent:
    """Something noteworthy that happened this tick."""

    kind: EventKind
    name: str  # constraint or corridor id
    detail: str = ""


# ---------------------------------------------------------------------------
# Tick snapshot — one frame of the simulation
# ---------------------------------------------------------------------------

@dataclass
class Snapshot:
    """Complete state at one point in time."""

    timestamp: float
    field: PossibilityField
    viabilities: list[CorridorViability]
    events: list[TickEvent] = field(default_factory=list)

    @property
    def viable_corridors(self) -> list[CorridorViability]:
        """Corridors with viability > 0."""
        return [v for v in self.viabilities if not v.is_blocked]

    @property
    def blocked_corridors(self) -> list[CorridorViability]:
        """Corridors that are fully blocked."""
        return [v for v in self.viabilities if v.is_blocked]


# ---------------------------------------------------------------------------
# TickEngine
# ---------------------------------------------------------------------------

class TickEngine:
    """
    Advances time over a constraint field and a rail topology.

    Each tick:
      1. Compute the PossibilityField at current time.
      2. Compute corridor viabilities from the current node.
      3. Diff against previous tick to detect events.
      4. Store snapshot.
    """

    def __init__(
        self,
        graph: RailGraph,
        constraints: list[Constraint],
        agent_id: str,
        node_id: str,
        role: Optional[str] = None,
        sample_spacing: float = 0.5,
    ) -> None:
        self.graph = graph
        self.constraints = list(constraints)
        self.agent_id = agent_id
        self.node_id = node_id
        self.role = role
        self.sample_spacing = sample_spacing
        self._prev: Optional[Snapshot] = None

    # --- Core loop ---

    def tick(self, t: float) -> Snapshot:
        """Compute one snapshot at time t and diff against previous."""
        pf = compute_field(self.agent_id, t, self.constraints)
        viabilities = self.graph.corridor_viabilities(
            self.node_id,
            self.constraints,
            timestamp=t,
            role=self.role,
            sample_spacing=self.sample_spacing,
        )
        events = self._detect_events(t, pf, viabilities)
        snap = Snapshot(timestamp=t, field=pf, viabilities=viabilities, events=events)
        self._prev = snap
        return snap

    def run(self, duration: float, dt: float, t_start: float = 0.0) -> list[Snapshot]:
        """Run the tick loop from t_start to t_start + duration."""
        timeline: list[Snapshot] = []
        t = t_start
        while t <= t_start + duration + dt * 0.01:  # epsilon for float precision
            timeline.append(self.tick(t))
            t = round(t + dt, 10)
        return timeline

    # --- Constraint schedule ---

    def add_constraint(self, constraint: Constraint) -> None:
        """Add a constraint mid-simulation."""
        self.constraints.append(constraint)

    def remove_constraint(self, name: str) -> Optional[Constraint]:
        """Remove a constraint by name. Returns it if found."""
        for i, c in enumerate(self.constraints):
            if c.name == name:
                return self.constraints.pop(i)
        return None

    # --- Event detection ---

    def _detect_events(
        self,
        t: float,
        current_field: PossibilityField,
        current_viabilities: list[CorridorViability],
    ) -> list[TickEvent]:
        events: list[TickEvent] = []
        if self._prev is None:
            return events

        prev_active = {c.name for c in self._prev.field.active_constraints}
        curr_active = {c.name for c in current_field.active_constraints}

        # Constraints that expired
        for name in prev_active - curr_active:
            events.append(TickEvent(
                kind=EventKind.CONSTRAINT_EXPIRED,
                name=name,
                detail=f"expired at t={t:.3f}",
            ))

        # Constraints that activated
        for name in curr_active - prev_active:
            events.append(TickEvent(
                kind=EventKind.CONSTRAINT_ACTIVATED,
                name=name,
                detail=f"activated at t={t:.3f}",
            ))

        # Corridor state changes
        prev_viab = {v.edge_id: v for v in self._prev.viabilities}
        for v in current_viabilities:
            prev = prev_viab.get(v.edge_id)
            if prev is None:
                continue
            was_blocked = prev.is_blocked
            now_blocked = v.is_blocked
            if was_blocked and not now_blocked:
                events.append(TickEvent(
                    kind=EventKind.CORRIDOR_OPENED,
                    name=v.edge_id,
                    detail=f"viability {prev.viability:.2f} -> {v.viability:.2f}",
                ))
            elif not was_blocked and now_blocked:
                events.append(TickEvent(
                    kind=EventKind.CORRIDOR_COLLAPSED,
                    name=v.edge_id,
                    detail=f"viability {prev.viability:.2f} -> {v.viability:.2f}",
                ))

        # Field collapse
        if not self._prev.field.is_collapsed and current_field.is_collapsed:
            events.append(TickEvent(
                kind=EventKind.FIELD_COLLAPSED,
                name=self.agent_id,
                detail=f"surviving_volume={current_field.surviving_volume:.3f}",
            ))

        return events
