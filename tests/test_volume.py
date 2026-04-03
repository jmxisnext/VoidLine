"""Tests for geometric volume computation."""

import math
import pytest

from src.constraints.volume import compute_boundary_volume, HALF_COURT_AREA_SQFT
from src.field.space_model import Circle, Cone, Point


class TestComputeBoundaryVolume:
    def test_none_returns_zero(self):
        assert compute_boundary_volume(None) == 0.0

    def test_circle_volume_is_geometric(self):
        c = Circle(center=Point(x=0.0, y=0.0), radius=2.0)
        expected = math.pi * 4.0 / HALF_COURT_AREA_SQFT
        result = compute_boundary_volume(c)
        assert result == pytest.approx(expected, rel=1e-6)
        # ~0.0107, NOT the old magic 0.25
        assert result < 0.02

    def test_larger_circle_larger_volume(self):
        small = Circle(center=Point(x=0.0, y=0.0), radius=1.0)
        large = Circle(center=Point(x=0.0, y=0.0), radius=3.0)
        assert compute_boundary_volume(large) > compute_boundary_volume(small)

    def test_circle_volume_capped_at_one(self):
        huge = Circle(center=Point(x=0.0, y=0.0), radius=100.0)
        assert compute_boundary_volume(huge) == 1.0

    def test_cone_returns_positive(self):
        c = Cone(origin=Point(x=0.0, y=0.0), direction_deg=0.0, half_angle_deg=30.0)
        vol = compute_boundary_volume(c)
        assert 0.0 < vol < 1.0

    def test_wider_cone_larger_volume(self):
        narrow = Cone(origin=Point(x=0.0, y=0.0), direction_deg=0.0, half_angle_deg=15.0)
        wide = Cone(origin=Point(x=0.0, y=0.0), direction_deg=0.0, half_angle_deg=45.0)
        assert compute_boundary_volume(wide) > compute_boundary_volume(narrow)
