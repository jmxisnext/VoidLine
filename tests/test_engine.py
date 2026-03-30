"""
Tests for the tick engine — time-evolving constraint fields.

Proves: the tick loop advances time, recomputes fields each step,
detects constraint expiry and corridor state changes.
"""

from pathlib import Path

import pytest

from src.field.space_model import Point, Circle, TimeWindow
from src.constraints.types import (
    Constraint,
    SpatialConstraint,
    ConstraintDynamics,
    ConstraintSource,
    Stability,
)
from src.rail.graph import load_railgraph
from src.engine.tick import TickEngine, EventKind, Snapshot


SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"


@pytest.fixture
def pnr_graph():
    return load_railgraph(SCENARIOS_DIR / "pnr_basic.json")


# ---------------------------------------------------------------------------
# Basic tick behavior
# ---------------------------------------------------------------------------

class TestTickBasics:
    def test_single_tick_produces_snapshot(self, pnr_graph, pnr_constraints):
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        snap = engine.tick(0.0)
        assert isinstance(snap, Snapshot)
        assert snap.timestamp == 0.0
        assert snap.field.agent_id == "PG_01"

    def test_run_produces_timeline(self, pnr_graph, pnr_constraints):
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=1.0, dt=0.5)
        # t=0.0, 0.5, 1.0
        assert len(timeline) == 3
        assert timeline[0].timestamp == 0.0
        assert timeline[-1].timestamp == 1.0

    def test_timestamps_advance(self, pnr_graph, pnr_constraints):
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=2.0, dt=0.1)
        timestamps = [s.timestamp for s in timeline]
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i - 1]

    def test_no_events_on_first_tick(self, pnr_graph, pnr_constraints):
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        snap = engine.tick(0.0)
        assert snap.events == []


# ---------------------------------------------------------------------------
# Time-evolving field
# ---------------------------------------------------------------------------

class TestTimeEvolvingField:
    def test_pressure_decreases_as_constraints_expire(self, pnr_graph, pnr_constraints):
        """Three transient constraints expire by t=1.2 — pressure should drop."""
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=1.5, dt=0.1)

        pressure_start = timeline[0].field.space_pressure
        pressure_end = timeline[-1].field.space_pressure
        assert pressure_end < pressure_start

    def test_active_constraint_count_drops(self, pnr_graph, pnr_constraints):
        """More constraints active at t=0 than at t=1.5."""
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        snap_0 = engine.tick(0.0)
        snap_late = engine.tick(1.5)
        assert len(snap_late.field.active_constraints) < len(snap_0.field.active_constraints)

    def test_surviving_volume_increases(self, pnr_graph, pnr_constraints):
        """As constraints expire, surviving volume should grow."""
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=1.5, dt=0.5)
        volumes = [s.field.surviving_volume for s in timeline]
        # Volume should generally increase (constraints are expiring)
        assert volumes[-1] > volumes[0]


# ---------------------------------------------------------------------------
# Corridor viability evolution
# ---------------------------------------------------------------------------

class TestCorridorViabilityEvolution:
    def test_viabilities_present_each_tick(self, pnr_graph, pnr_constraints):
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=1.0, dt=0.5)
        for snap in timeline:
            assert len(snap.viabilities) == 5  # 5 outgoing edges for ball_handler

    def test_drive_viability_improves_after_help_expires(self, pnr_graph, pnr_constraints):
        """Help defender expires at t=1.2 — drive_left should improve."""
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=1.5, dt=0.1)

        def drive_viability(snap: Snapshot) -> float:
            return next(v.viability for v in snap.viabilities if v.edge_id == "drive_left")

        v_early = drive_viability(timeline[0])
        v_late = drive_viability(timeline[-1])
        assert v_late > v_early

    def test_viable_and_blocked_corridor_helpers(self, pnr_graph, pnr_constraints):
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        snap = engine.tick(0.0)
        total = len(snap.viable_corridors) + len(snap.blocked_corridors)
        assert total == len(snap.viabilities)


# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------

class TestEventDetection:
    def test_constraint_expired_event(self, pnr_graph, pnr_constraints):
        """Stepping past a constraint's active_window should emit CONSTRAINT_EXPIRED."""
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=1.5, dt=0.1)

        all_events = [e for snap in timeline for e in snap.events]
        expired_events = [e for e in all_events if e.kind == EventKind.CONSTRAINT_EXPIRED]
        expired_names = {e.name for e in expired_events}

        # These three transient constraints should expire during the run
        assert "rightward_momentum" in expired_names  # ends at 0.4
        assert "screen_not_yet_set" in expired_names  # ends at 0.8
        assert "help_defender_paint" in expired_names  # ends at 1.2

    def test_corridor_opened_event(self, pnr_graph):
        """A corridor blocked by a transient constraint should emit CORRIDOR_OPENED when it expires."""
        # Create a constraint that fully blocks drive_left then expires
        blocker = SpatialConstraint(
            name="total_blocker",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(
                stability=Stability.TRANSIENT,
                active_window=TimeWindow(start=0.0, end=0.5),
            ),
            boundary=Circle(center=Point(x=-8.0, y=2.0), radius=15.0),
            volume=0.5,
        )
        engine = TickEngine(pnr_graph, [blocker], "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=1.0, dt=0.1)

        opened = [
            e for snap in timeline for e in snap.events
            if e.kind == EventKind.CORRIDOR_OPENED
        ]
        assert len(opened) > 0

    def test_corridor_collapsed_event(self, pnr_graph):
        """Adding a massive constraint mid-run should emit CORRIDOR_COLLAPSED."""
        engine = TickEngine(pnr_graph, [], "PG_01", "screen_point", role="ball_handler")
        # First tick — everything open
        engine.tick(0.0)
        # Add wall
        engine.add_constraint(SpatialConstraint(
            name="wall",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=Circle(center=Point(x=-8.0, y=2.0), radius=20.0),
            volume=0.9,
        ))
        snap = engine.tick(0.1)
        collapsed = [e for e in snap.events if e.kind == EventKind.CORRIDOR_COLLAPSED]
        assert len(collapsed) > 0

    def test_no_spurious_events_on_stable_field(self, pnr_graph):
        """Static constraints only — no events after first tick."""
        static = SpatialConstraint(
            name="wall",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=Circle(center=Point(x=0.0, y=0.0), radius=2.0),
            volume=0.1,
        )
        engine = TickEngine(pnr_graph, [static], "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=1.0, dt=0.2)
        # After the first tick (which has no prev), no events should fire
        for snap in timeline[1:]:
            assert snap.events == []


# ---------------------------------------------------------------------------
# Constraint schedule (add/remove mid-simulation)
# ---------------------------------------------------------------------------

class TestConstraintSchedule:
    def test_add_constraint_increases_pressure(self, pnr_graph):
        engine = TickEngine(pnr_graph, [], "PG_01", "screen_point", role="ball_handler")
        snap_free = engine.tick(0.0)
        assert snap_free.field.space_pressure == 0.0

        engine.add_constraint(SpatialConstraint(
            name="new_defender",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=Circle(center=Point(x=0.0, y=0.0), radius=3.0),
            volume=0.3,
        ))
        snap_after = engine.tick(0.1)
        assert snap_after.field.space_pressure > 0.0

    def test_remove_constraint_decreases_pressure(self, pnr_graph, pnr_constraints):
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        snap_before = engine.tick(0.0)

        removed = engine.remove_constraint("onball_defender_left_shade")
        assert removed is not None
        snap_after = engine.tick(0.0)
        assert snap_after.field.space_pressure < snap_before.field.space_pressure

    def test_remove_nonexistent_returns_none(self, pnr_graph):
        engine = TickEngine(pnr_graph, [], "PG_01", "screen_point")
        assert engine.remove_constraint("ghost") is None


# ---------------------------------------------------------------------------
# Run with t_start offset
# ---------------------------------------------------------------------------

class TestRunOffset:
    def test_run_with_nonzero_start(self, pnr_graph, pnr_constraints):
        engine = TickEngine(pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler")
        timeline = engine.run(duration=0.5, dt=0.1, t_start=1.0)
        assert timeline[0].timestamp == 1.0
        assert abs(timeline[-1].timestamp - 1.5) < 1e-9
