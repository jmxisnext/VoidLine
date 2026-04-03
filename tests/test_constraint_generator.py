"""
Tests for the constraint generator adapter.

Verifies that extraction output (dict) → VoidLine constraints works
correctly, with geometrically derived volumes and speed-dependent radii.
"""

import math
import sys
from copy import deepcopy
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)  # noqa: E402

from adapter.constraint_generator import (
    constraints_from_extraction,
    defender_constraint,
    momentum_constraint,
    BASE_DENIAL_RADIUS_FT,
    SPEED_FACTOR,
)
from src.constraints.types import SpatialConstraint, KinematicConstraint
from src.constraints.volume import HALF_COURT_AREA_SQFT


def _make_extraction(entities: list[dict]) -> dict:
    """Helper to build a minimal extraction dict."""
    return {
        "scenario": "test",
        "coordinate_system": "iso4d",
        "frame_rate_hz": 10.0,
        "duration_s": 3.0,
        "entities": entities,
    }


def _make_entity(eid: str, role: str, pos: tuple, vel: tuple, t: float = 1.2) -> dict:
    return {
        "id": eid,
        "role": role,
        "frames": [{"t": t, "pos": list(pos), "vel": list(vel)}],
    }


# ---------------------------------------------------------------------------
# Core generation tests
# ---------------------------------------------------------------------------


class TestConstraintsFromExtraction:
    def test_generates_constraints(self):
        """Basic: extraction with ball handler + 2 nearby defenders → constraints."""
        ext = _make_extraction([
            _make_entity("player_1", "ball_handler", (-16, 4), (5, 0)),
            _make_entity("player_3", "spacer", (-5, 22), (0, 0)),   # far away
            _make_entity("player_4", "defender", (-10, 2), (-3, 0)),  # close
            _make_entity("player_5", "defender", (-12, 6), (-2, -1)), # close
        ])
        constraints = constraints_from_extraction(ext, "player_1", t=1.2)
        # Should get defender constraints + momentum constraint
        assert len(constraints) >= 2
        spatial = [c for c in constraints if isinstance(c, SpatialConstraint)]
        assert len(spatial) >= 1  # at least one nearby defender

    def test_far_entities_excluded(self):
        """Entities beyond proximity threshold don't generate constraints."""
        ext = _make_extraction([
            _make_entity("player_1", "ball_handler", (-16, 4), (5, 0)),
            _make_entity("player_3", "spacer", (-5, 22), (0, 0)),  # 20+ ft away
        ])
        constraints = constraints_from_extraction(ext, "player_1", t=1.2)
        spatial = [c for c in constraints if isinstance(c, SpatialConstraint)]
        assert len(spatial) == 0

    def test_ball_entity_excluded(self):
        """Ball entity should not generate a defender constraint."""
        ext = _make_extraction([
            _make_entity("player_1", "ball_handler", (-16, 4), (5, 0)),
            _make_entity("ball", "ball", (-16, 4), (5, 0)),
        ])
        constraints = constraints_from_extraction(ext, "player_1", t=1.2)
        spatial = [c for c in constraints if isinstance(c, SpatialConstraint)]
        assert len(spatial) == 0


# ---------------------------------------------------------------------------
# Defender constraint geometry
# ---------------------------------------------------------------------------


class TestDefenderConstraint:
    def test_closer_defender_same_volume_formula(self):
        """Volume depends on radius, which depends on speed — not distance."""
        # Two defenders at different distances but same speed
        close = defender_constraint("d1", (-10, 2), (3, 0), "agent")
        far = defender_constraint("d2", (-30, 20), (3, 0), "agent")
        # Same speed → same radius → same volume
        assert close.volume == far.volume

    def test_faster_defender_larger_radius(self):
        """Faster defender creates a larger denial zone."""
        slow = defender_constraint("d1", (-10, 2), (1, 0), "agent")
        fast = defender_constraint("d2", (-10, 2), (5, 0), "agent")
        assert fast.boundary.radius > slow.boundary.radius
        assert fast.volume > slow.volume

    def test_radius_formula(self):
        """Verify radius = base + factor * speed."""
        speed = 4.0
        c = defender_constraint("d", (0, 0), (speed, 0), "agent")
        expected_radius = BASE_DENIAL_RADIUS_FT + SPEED_FACTOR * speed
        assert c.boundary.radius == expected_radius

    def test_volume_derived_from_geometry(self):
        """Volume must be pi*r^2/court_area, NOT a magic number."""
        c = defender_constraint("d", (0, 0), (0, 0), "agent")
        r = c.boundary.radius
        expected = math.pi * r**2 / HALF_COURT_AREA_SQFT
        assert abs(c.volume - expected) < 1e-10
        # Specifically NOT 0.25 or any round number
        assert c.volume != 0.25
        assert c.volume != 0.20


# ---------------------------------------------------------------------------
# Momentum constraint
# ---------------------------------------------------------------------------


class TestMomentumConstraint:
    def test_stationary_no_constraint(self):
        """Stationary handler has no momentum commitment."""
        assert momentum_constraint((0, 0), "agent") is None
        assert momentum_constraint((0.5, 0), "agent") is None

    def test_moving_produces_kinematic(self):
        """Moving handler gets a kinematic constraint."""
        mc = momentum_constraint((10, 0), "agent")
        assert mc is not None
        assert isinstance(mc, KinematicConstraint)
        assert mc.commitment_direction == 0.0  # moving in +x

    def test_volume_scales_with_speed(self):
        """Faster handler = more committed = higher volume."""
        slow = momentum_constraint((3, 0), "agent")
        fast = momentum_constraint((15, 0), "agent")
        assert fast.volume > slow.volume


# ---------------------------------------------------------------------------
# Novel input: "what if defender was 3 feet left?"
# ---------------------------------------------------------------------------


class TestNovelInput:
    def test_shift_defender_changes_constraints(self):
        """Modifying a defender's position and regenerating produces different constraints.

        This is the key test: proves the system can handle novel game states
        without hand-authoring.
        """
        ext = _make_extraction([
            _make_entity("player_1", "ball_handler", (-16, 4), (5, 0)),
            _make_entity("player_4", "defender", (-10, 2), (-3, 0)),
        ])

        original = constraints_from_extraction(ext, "player_1", t=1.2)

        # Shift defender 3 feet left (in y)
        shifted = deepcopy(ext)
        shifted["entities"][1]["frames"][0]["pos"][1] = -1.0  # was 2, now -1

        modified = constraints_from_extraction(shifted, "player_1", t=1.2)

        # Both should produce constraints
        assert len(original) > 0
        assert len(modified) > 0

        # The spatial constraints should have different centers
        orig_spatial = [c for c in original if isinstance(c, SpatialConstraint)]
        mod_spatial = [c for c in modified if isinstance(c, SpatialConstraint)]
        assert len(orig_spatial) == 1
        assert len(mod_spatial) == 1
        assert orig_spatial[0].boundary.center.y != mod_spatial[0].boundary.center.y
