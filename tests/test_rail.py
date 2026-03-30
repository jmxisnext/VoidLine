"""
Tests for the rail topology and corridor viability.

Proves: given authored topology + time-varying constraints,
VoidLine can show which corridors survive, which collapse, and why.
"""

from pathlib import Path

import pytest

from src.field.space_model import Point, Circle, Corridor
from src.constraints.types import (
    Constraint,
    SpatialConstraint,
    ConstraintDynamics,
    ConstraintSource,
    Stability,
)
from src.rail.graph import (
    RailGraph,
    RailEdge,
    load_railgraph,
    compute_corridor_viability,
    CorridorViability,
)


SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"


# ---------------------------------------------------------------------------
# Schema + loader
# ---------------------------------------------------------------------------

class TestRailGraphLoader:
    def test_load_pnr_basic(self) -> None:
        """PNR scenario loads and validates against schema."""
        graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
        assert graph.node_count == 7
        assert graph.edge_count == 7
        assert graph.meta["name"] == "pnr_basic"

    def test_node_types(self) -> None:
        graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
        assert len(graph.start_nodes()) == 1
        assert len(graph.junctions()) == 2
        assert len(graph.terminals()) == 4

    def test_outgoing_edges(self) -> None:
        graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
        # screen_point junction has 5 outgoing edges
        out = graph.outgoing("screen_point")
        assert len(out) == 5

    def test_outgoing_role_filter(self) -> None:
        graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
        # roll_man can only take roll_to_rim from roll_pocket
        out = graph.outgoing("roll_pocket", role="roll_man")
        assert len(out) == 1
        assert out[0].id == "roll_to_rim"

    def test_positions_are_iso4d_aligned(self) -> None:
        """Coordinates should be in feet from basket center."""
        graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
        rim = graph.nodes["rim"]
        assert rim.position.x == 0.0
        assert rim.position.y == 0.0

    def test_corridor_geometry_exists(self) -> None:
        graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
        drive = graph.edges["drive_left"]
        assert drive.corridor.length > 0
        assert len(drive.corridor.waypoints) == 4

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        """Missing required fields should fail validation."""
        bad = tmp_path / "bad.json"
        bad.write_text('{"meta": {"name": "x"}, "nodes": [], "edges": []}')
        with pytest.raises(Exception):
            load_railgraph(bad)


# ---------------------------------------------------------------------------
# Corridor viability
# ---------------------------------------------------------------------------

class TestCorridorViability:
    def _make_straight_edge(
        self, start: Point, end: Point, width: float = 1.5
    ) -> RailEdge:
        return RailEdge(
            id="test_edge",
            from_node="a",
            to_node="b",
            corridor=Corridor(waypoints=(start, end), width=width),
            action_type="drive",
        )

    def test_unconstrained_corridor_fully_viable(self) -> None:
        """No constraints → viability = 1.0."""
        edge = self._make_straight_edge(Point(x=-20.0, y=0.0), Point(x=0.0, y=0.0))
        v = compute_corridor_viability(edge, [], 0.0)
        assert v.viability == 1.0
        assert not v.is_blocked
        assert v.dominant_blocker is None

    def test_blocking_constraint_reduces_viability(self) -> None:
        """A circle sitting on the corridor should reduce viability."""
        edge = self._make_straight_edge(Point(x=-10.0, y=0.0), Point(x=10.0, y=0.0))
        blocker = SpatialConstraint(
            name="paint_defender",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=Circle(center=Point(x=0.0, y=0.0), radius=3.0),
            volume=0.2,
        )
        v = compute_corridor_viability(edge, [blocker], 0.0)
        assert 0.0 < v.viability < 1.0
        assert v.blocked_by.get("paint_defender", 0) > 0
        assert v.dominant_blocker == "paint_defender"

    def test_off_corridor_constraint_no_effect(self) -> None:
        """A constraint far from the corridor shouldn't block it."""
        edge = self._make_straight_edge(Point(x=-10.0, y=0.0), Point(x=10.0, y=0.0))
        far_away = SpatialConstraint(
            name="corner_defender",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=Circle(center=Point(x=0.0, y=25.0), radius=2.0),
            volume=0.1,
        )
        v = compute_corridor_viability(edge, [far_away], 0.0)
        assert v.viability == 1.0

    def test_expired_constraint_no_effect(self) -> None:
        """A transient constraint that's expired should not block."""
        from src.field.space_model import TimeWindow

        edge = self._make_straight_edge(Point(x=-10.0, y=0.0), Point(x=10.0, y=0.0))
        expired = SpatialConstraint(
            name="help_defender",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(
                stability=Stability.TRANSIENT,
                active_window=TimeWindow(start=0.0, end=1.0),
            ),
            boundary=Circle(center=Point(x=0.0, y=0.0), radius=3.0),
            volume=0.2,
        )
        # At t=0.5: active, should block
        v_active = compute_corridor_viability(edge, [expired], 0.5)
        assert v_active.viability < 1.0

        # At t=1.5: expired, should not block
        v_expired = compute_corridor_viability(edge, [expired], 1.5)
        assert v_expired.viability == 1.0

    def test_multiple_constraints_stack(self) -> None:
        """Two constraints on the same corridor should block more samples."""
        edge = self._make_straight_edge(Point(x=-10.0, y=0.0), Point(x=10.0, y=0.0))
        c1 = SpatialConstraint(
            name="defender_a",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=Circle(center=Point(x=-3.0, y=0.0), radius=2.0),
            volume=0.1,
        )
        c2 = SpatialConstraint(
            name="defender_b",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=Circle(center=Point(x=5.0, y=0.0), radius=2.0),
            volume=0.1,
        )
        v_one = compute_corridor_viability(edge, [c1], 0.0)
        v_both = compute_corridor_viability(edge, [c1, c2], 0.0)
        assert v_both.viability < v_one.viability

    def test_dominant_blocker_attribution(self) -> None:
        """The constraint blocking more samples should be identified."""
        edge = self._make_straight_edge(Point(x=-10.0, y=0.0), Point(x=10.0, y=0.0))
        small = SpatialConstraint(
            name="small_zone",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=Circle(center=Point(x=-8.0, y=0.0), radius=1.0),
            volume=0.05,
        )
        big = SpatialConstraint(
            name="big_zone",
            source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=Circle(center=Point(x=0.0, y=0.0), radius=4.0),
            volume=0.15,
        )
        v = compute_corridor_viability(edge, [small, big], 0.0)
        assert v.dominant_blocker == "big_zone"


# ---------------------------------------------------------------------------
# Integrated: RailGraph + constraints → corridor viabilities
# ---------------------------------------------------------------------------

class TestIntegratedViability:
    def test_pnr_viabilities_at_screen_point(self, pnr_constraints: list) -> None:
        """
        At the PNR decision junction with all constraints active,
        some corridors should be more viable than others.
        """
        graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
        viabilities = graph.corridor_viabilities(
            "screen_point", pnr_constraints, timestamp=0.0, role="ball_handler"
        )
        # screen_point has 5 outgoing edges for ball_handler
        # (drive_left, pullup_right, reset_left, kick_corner, pocket_pass)
        assert len(viabilities) == 5

        by_id = {v.edge_id: v for v in viabilities}

        # drive_left goes through the paint where help defender sits → should be degraded
        assert by_id["drive_left"].viability < 1.0

        # kick_corner goes far right — away from both defenders → should be less degraded
        # (the on-ball defender is at left side, help is in paint)
        assert by_id["kick_corner"].viability >= by_id["drive_left"].viability

    def test_pnr_viabilities_improve_after_rotation(self, pnr_constraints: list) -> None:
        """
        At t=1.2, help defender has rotated out and momentum expired.
        Drive corridor viability should improve.
        """
        graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")

        v_before = graph.corridor_viabilities(
            "screen_point", pnr_constraints, timestamp=0.0, role="ball_handler"
        )
        v_after = graph.corridor_viabilities(
            "screen_point", pnr_constraints, timestamp=1.2, role="ball_handler"
        )

        drive_before = next(v for v in v_before if v.edge_id == "drive_left")
        drive_after = next(v for v in v_after if v.edge_id == "drive_left")

        # Drive should be more viable after help defender leaves paint
        assert drive_after.viability > drive_before.viability

    def test_all_corridors_survive_without_constraints(self) -> None:
        """With no constraints, every corridor is fully viable."""
        graph = load_railgraph(SCENARIOS_DIR / "pnr_basic.json")
        viabilities = graph.corridor_viabilities("screen_point", [], timestamp=0.0)
        for v in viabilities:
            assert v.viability == 1.0
