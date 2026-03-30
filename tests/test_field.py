"""
Tests for the possibility field — VoidLine's primary artifact.

These lock behavior before features get added.
"""

from src.field.space_model import Point, Circle, Cone, classify_zone
from src.constraints.types import (
    Constraint,
    SpatialConstraint,
    ConstraintDynamics,
    ConstraintSource,
    Stability,
)
from src.envelope.field import compute_field, FieldDiff


class TestSpatialPrimitives:
    def test_point_distance_from_hoop(self) -> None:
        p = Point(x=3.0, y=4.0)
        assert abs(p.distance_from_hoop - 5.0) < 1e-6

    def test_point_distance_to(self) -> None:
        a = Point(x=0.0, y=0.0)
        b = Point(x=3.0, y=4.0)
        assert abs(a.distance_to(b) - 5.0) < 1e-6

    def test_circle_contains(self) -> None:
        c = Circle(center=Point(x=0.0, y=0.0), radius=5.0)
        assert c.contains_point(Point(x=3.0, y=3.0))
        assert not c.contains_point(Point(x=10.0, y=10.0))

    def test_cone_contains(self) -> None:
        cone = Cone(origin=Point(x=0.0, y=0.0), direction_deg=0.0, half_angle_deg=45.0)
        # Point directly ahead (+X axis) should be inside
        assert cone.contains_point(Point(x=5.0, y=0.0))
        # Point at 30 degrees should be inside
        assert cone.contains_point(Point(x=5.0, y=2.9))
        # Point at 90 degrees should be outside
        assert not cone.contains_point(Point(x=0.0, y=5.0))


class TestZoneClassification:
    def test_restricted_area(self) -> None:
        assert classify_zone(Point(x=1.0, y=0.0)) == "restricted_area"

    def test_paint(self) -> None:
        assert classify_zone(Point(x=10.0, y=3.0)) == "paint"

    def test_above_break_3(self) -> None:
        assert classify_zone(Point(x=-25.0, y=0.0)) == "above_break_3"

    def test_backcourt(self) -> None:
        assert classify_zone(Point(x=-50.0, y=0.0)) == "backcourt"


class TestPossibilityField:
    def test_pnr_field_at_t0(self, pnr_constraints: list) -> None:
        """All 7 constraints active at t=0 → high pressure."""
        field = compute_field("PG_01", 0.0, pnr_constraints)
        assert len(field.active_constraints) == 7
        assert field.space_pressure > 0.8
        assert field.surviving_volume < 0.2

    def test_pnr_field_at_t1_2(self, pnr_constraints: list) -> None:
        """At t=1.2, three transient constraints have expired → pressure drops."""
        field = compute_field("PG_01", 1.2, pnr_constraints)
        # help_defender (ends 1.2), screen_not_set (ends 0.8), momentum (ends 0.4) gone
        assert len(field.active_constraints) == 4
        assert field.space_pressure < 0.5

    def test_field_diff_shows_reopened_space(self, pnr_constraints: list) -> None:
        """Diffing t=0 vs t=1.2 should show space reopened."""
        before = compute_field("PG_01", 0.0, pnr_constraints)
        after = compute_field("PG_01", 1.2, pnr_constraints)
        diff = FieldDiff(before=before, after=after)

        assert diff.volume_delta > 0  # space opened
        assert diff.pressure_delta < 0  # pressure decreased
        assert len(diff.removed_constraints) == 3
        assert len(diff.space_opened_by) == 3

    def test_dominant_removal(self, pnr_constraints: list) -> None:
        """On-ball defender should be the dominant removal at t=0."""
        field = compute_field("PG_01", 0.0, pnr_constraints)
        dom = field.dominant_removal()
        assert dom is not None
        assert dom.constraint_name == "onball_defender_left_shade"
        assert dom.volume_removed == 0.25

    def test_empty_constraints_full_freedom(self) -> None:
        """No constraints → full possibility."""
        field = compute_field("PG_01", 0.0, [])
        assert field.surviving_volume == 1.0
        assert field.space_pressure == 0.0
        assert not field.is_collapsed
