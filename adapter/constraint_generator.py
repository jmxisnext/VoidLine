"""
adapter.constraint_generator
=============================
Generate VoidLine constraints from ISO4D extraction output.

Takes an extraction dict (ExtractionResult.to_dict()) and produces a list
of Constraint objects. This is the bridge between state extraction and
feasibility modeling.

Design decisions:
  - Accepts a dict, not an ExtractionResult class — avoids cross-repo import.
  - Defender denial radius derived from speed (closing defender = larger zone).
  - Volume computed from boundary geometry, not hand-authored.
"""

from __future__ import annotations

import math
from typing import Optional

from src.field.space_model import Point, Circle, TimeWindow
from src.constraints.types import (
    Constraint,
    SpatialConstraint,
    KinematicConstraint,
    ConstraintDynamics,
    ConstraintSource,
    Stability,
)
from src.constraints.volume import compute_boundary_volume


# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

BASE_DENIAL_RADIUS_FT = 1.5     # minimum denial zone for any defender
SPEED_FACTOR = 0.3              # additional radius per ft/s of defender speed
PROXIMITY_THRESHOLD_FT = 15.0   # only generate constraints for defenders within this range
MAX_SPEED_FT_S = 30.0           # near-max NBA sprint speed, for momentum normalization


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def constraints_from_extraction(
    extraction_dict: dict,
    agent_id: str,
    t: float,
) -> list[Constraint]:
    """Generate constraints from an ISO4D extraction at a specific time.

    Parameters
    ----------
    extraction_dict : dict
        Output of ExtractionResult.to_dict(). Must have 'entities' key.
    agent_id : str
        The constrained agent (typically the ball handler entity id).
    t : float
        Timestamp in seconds to evaluate.

    Returns
    -------
    list[Constraint]
        Spatial constraints for nearby defenders + kinematic constraint
        for ball handler momentum.
    """
    entities = extraction_dict.get("entities", [])
    if not entities:
        return []

    # Find ball handler
    ball_handler = _find_entity(entities, agent_id)
    if ball_handler is None:
        return []

    bh_frame = _frame_at_time(ball_handler, t)
    if bh_frame is None:
        return []

    bh_pos = (bh_frame["pos"][0], bh_frame["pos"][1])
    bh_vel = (bh_frame["vel"][0], bh_frame["vel"][1])

    constraints: list[Constraint] = []

    # Generate spatial constraints for each nearby non-handler entity
    for entity in entities:
        if entity["id"] == agent_id:
            continue
        if entity.get("role") == "ball":
            continue

        frame = _frame_at_time(entity, t)
        if frame is None:
            continue

        pos = (frame["pos"][0], frame["pos"][1])
        vel = (frame["vel"][0], frame["vel"][1])

        dist = math.hypot(pos[0] - bh_pos[0], pos[1] - bh_pos[1])
        if dist > PROXIMITY_THRESHOLD_FT:
            continue

        c = defender_constraint(
            name=f"defender_{entity['id']}",
            pos=pos,
            vel=vel,
            agent_id=agent_id,
        )
        constraints.append(c)

    # Add momentum constraint for ball handler
    mc = momentum_constraint(bh_vel, agent_id)
    if mc is not None:
        constraints.append(mc)

    return constraints


def defender_constraint(
    name: str,
    pos: tuple[float, float],
    vel: tuple[float, float],
    agent_id: str,
) -> SpatialConstraint:
    """Create a spatial constraint from a defender's position and velocity.

    Radius scales with speed: a closing defender controls more space.
    Volume is geometrically derived from circle area / court area.
    """
    speed = math.hypot(vel[0], vel[1])
    radius = BASE_DENIAL_RADIUS_FT + SPEED_FACTOR * speed

    boundary = Circle(
        center=Point(x=pos[0], y=pos[1]),
        radius=radius,
    )

    return SpatialConstraint(
        name=name,
        source=ConstraintSource.OPPONENT,
        dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
        boundary=boundary,
        volume=compute_boundary_volume(boundary),
        agent_id=agent_id,
    )


def momentum_constraint(
    vel: tuple[float, float],
    agent_id: str,
) -> Optional[KinematicConstraint]:
    """Create a kinematic constraint from ball handler velocity.

    Fast-moving handlers are committed to their direction — they can't
    instantly reverse. Volume scales with speed.
    """
    speed = math.hypot(vel[0], vel[1])
    if speed < 1.0:
        return None  # stationary — no momentum commitment

    direction = math.degrees(math.atan2(vel[1], vel[0]))
    volume = min(0.20, speed / MAX_SPEED_FT_S)

    return KinematicConstraint(
        name="ball_handler_momentum",
        source=ConstraintSource.SELF,
        dynamics=ConstraintDynamics(stability=Stability.TRANSIENT),
        boundary=None,
        volume=volume,
        agent_id=agent_id,
        max_velocity=speed,
        max_acceleration=15.0,  # reasonable NBA deceleration
        commitment_direction=direction,
        recovery_time=0.3,  # time to change direction
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_entity(entities: list[dict], entity_id: str) -> Optional[dict]:
    """Find an entity by id."""
    for e in entities:
        if e["id"] == entity_id:
            return e
    return None


def _frame_at_time(entity: dict, t: float, tolerance: float = 0.05) -> Optional[dict]:
    """Find the frame closest to time t."""
    best = None
    best_dt = float("inf")
    for frame in entity.get("frames", []):
        dt = abs(frame["t"] - t)
        if dt < best_dt:
            best_dt = dt
            best = frame
    if best is not None and best_dt <= tolerance:
        return best
    return None
