"""
constraints.types
=================
The six constraint categories and their base type.

Each constraint removes a region of possibility from the action space.
The system computes what survives — that surviving space is the product.

Design:
    - Every constraint carries a concrete boundary (Circle, Cone, TimeWindow)
    - Every constraint knows its own temporal dynamics (static/sustained/transient/decaying)
    - Constraints compose via union of their invalidated regions
    - The envelope is total_space minus that union
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union

from src.field.space_model import Point, Circle, Cone, TimeWindow


# ---------------------------------------------------------------------------
# Dynamics
# ---------------------------------------------------------------------------

class Stability(Enum):
    """How stable is this constraint over time?"""

    STATIC = "static"        # holds for entire possession (court bounds)
    SUSTAINED = "sustained"  # holds for multiple seconds (defensive positioning)
    TRANSIENT = "transient"  # flickers on/off within frames (passing window)
    DECAYING = "decaying"    # weakens over time (fatigue-based kinematic limit)


@dataclass(frozen=True)
class ConstraintDynamics:
    """Temporal behavior of a constraint."""

    stability: Stability
    active_window: Optional[TimeWindow] = None
    refresh_rate_hz: Optional[float] = None
    decay_half_life: Optional[float] = None


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------

class ConstraintSource(Enum):
    """What generates this constraint."""

    PHYSICS = "physics"        # court bounds, collision, gravity
    OPPONENT = "opponent"      # defender position, help rotation
    SELF = "self"              # own kinematics, fatigue, commitment
    RULES = "rules"            # shot clock, violations, role assignment
    PERCEPTION = "perception"  # what the agent can/cannot see
    RISK = "risk"              # threshold-based policy constraints


# ---------------------------------------------------------------------------
# Boundary type
# ---------------------------------------------------------------------------

Boundary = Union[Circle, Cone, TimeWindow, None]


# ---------------------------------------------------------------------------
# Base constraint
# ---------------------------------------------------------------------------

@dataclass
class Constraint:
    """
    A named, sourced, temporally-aware function that removes a region
    of possibility from the action space.

    Every constraint answers: what space does it remove, why, and for how long?
    """

    name: str
    source: ConstraintSource
    dynamics: ConstraintDynamics
    boundary: Boundary
    volume: float  # normalized 0..1 estimate of space removed
    agent_id: Optional[str] = None
    priority: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def pressure(self) -> float:
        """How much of total action space this single constraint removes."""
        return self.volume

    def is_active(self, t: float) -> bool:
        """Is this constraint alive at time t?"""
        if self.dynamics.active_window is None:
            return True
        return self.dynamics.active_window.contains(t)


# ---------------------------------------------------------------------------
# Six constraint categories
# ---------------------------------------------------------------------------

@dataclass
class SpatialConstraint(Constraint):
    """
    Removes physical court regions.

    Examples: defender denial area, out-of-bounds, blocked driving lane,
    screen geometry creating dead zones.
    """

    def __post_init__(self) -> None:
        if self.source is None:
            self.source = ConstraintSource.OPPONENT


@dataclass
class TemporalConstraint(Constraint):
    """
    Removes time windows from action space.

    Examples: shot clock expiring, pass too early, help defender arriving.
    """

    deadline: Optional[float] = None

    def __post_init__(self) -> None:
        if self.source is None:
            self.source = ConstraintSource.RULES


@dataclass
class KinematicConstraint(Constraint):
    """
    Removes action space based on movement physics.

    Examples: cannot decelerate in time, overcommitted momentum,
    fatigue reducing max acceleration, landing recovery.
    """

    max_velocity: Optional[float] = None
    max_acceleration: Optional[float] = None
    commitment_direction: Optional[Point] = None
    recovery_time: Optional[float] = None

    def __post_init__(self) -> None:
        if self.source is None:
            self.source = ConstraintSource.SELF


@dataclass
class RoleConstraint(Constraint):
    """
    Removes actions invalid for this agent's current role.

    Examples: not the ball handler, assigned weak-side, screener must hold.
    """

    required_role: Optional[str] = None
    current_role: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source is None:
            self.source = ConstraintSource.RULES


@dataclass
class PerceptualConstraint(Constraint):
    """
    Removes actions requiring information the agent doesn't have.

    Examples: target behind vision cone, delayed awareness of help rotation.
    """

    awareness_delay: Optional[float] = None

    def __post_init__(self) -> None:
        if self.source is None:
            self.source = ConstraintSource.PERCEPTION


@dataclass
class RiskConstraint(Constraint):
    """
    Removes actions exceeding acceptable risk thresholds.

    Examples: turnover probability too high, contested shot below threshold.
    """

    risk_value: float = 0.0
    threshold: float = 0.5
    risk_type: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source is None:
            self.source = ConstraintSource.RISK
