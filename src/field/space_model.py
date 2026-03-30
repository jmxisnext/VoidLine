"""
field.space_model
=================
Spatial primitives for the possibility field.

Coordinate convention matches ISO4D exactly:
    Origin = basket center, units = feet, +X = baseline, +Y = right wing.

These types are the foundation everything else builds on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Court constants (NBA standard, feet)
# ---------------------------------------------------------------------------

COURT_FULL_LENGTH_FT: float = 94.0
COURT_WIDTH_FT: float = 50.0
COURT_HALF_LENGTH_FT: float = COURT_FULL_LENGTH_FT / 2  # 47 ft

THREE_PT_ARC_RADIUS_FT: float = 23.75
THREE_PT_CORNER_FT: float = 22.0
FREE_THROW_LINE_FT: float = 15.0
PAINT_WIDTH_FT: float = 16.0
PAINT_LENGTH_FT: float = 19.0
RESTRICTED_AREA_RADIUS_FT: float = 4.0


# ---------------------------------------------------------------------------
# Spatial primitives
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Point:
    """A position in court space (feet from basket center)."""

    x: float
    y: float
    z: float = 0.0
    label: Optional[str] = field(default=None, compare=False)

    @property
    def distance_from_hoop(self) -> float:
        return math.hypot(self.x, self.y)

    @property
    def angle_from_hoop_deg(self) -> float:
        return math.degrees(math.atan2(self.y, self.x))

    def distance_to(self, other: Point) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def bearing_to(self, other: Point) -> float:
        """Bearing in degrees, clockwise from +X axis."""
        dx = other.x - self.x
        dy = other.y - self.y
        return math.degrees(math.atan2(dy, dx)) % 360

    def __repr__(self) -> str:
        lbl = f", label='{self.label}'" if self.label else ""
        return f"Point(x={self.x:.2f}, y={self.y:.2f}, z={self.z:.2f}{lbl})"


@dataclass(frozen=True)
class TimeWindow:
    """Half-open interval [start, end) in seconds from possession start."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def contains(self, t: float) -> bool:
        return self.start <= t < self.end


# ---------------------------------------------------------------------------
# Geometry primitives for constraint boundaries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Circle:
    """Circular region on the court floor."""

    center: Point
    radius: float

    def contains_point(self, p: Point) -> bool:
        return self.center.distance_to(p) <= self.radius

    @property
    def area(self) -> float:
        return math.pi * self.radius ** 2


@dataclass(frozen=True)
class Cone:
    """Vision or influence cone projected from a point."""

    origin: Point
    direction_deg: float  # center direction, degrees from +X
    half_angle_deg: float  # half the cone width

    def contains_point(self, p: Point) -> bool:
        bearing = self.origin.bearing_to(p)
        delta = abs((bearing - self.direction_deg + 180) % 360 - 180)
        return delta <= self.half_angle_deg


@dataclass(frozen=True)
class Corridor:
    """
    A polyline path with width — represents an edge's physical space on court.
    Used to compute how much of a route survives constraint removal.
    """

    waypoints: Tuple[Point, ...]
    width: float  # half-width in feet from centerline

    @property
    def length(self) -> float:
        total = 0.0
        for i in range(len(self.waypoints) - 1):
            total += self.waypoints[i].distance_to(self.waypoints[i + 1])
        return total

    def sample_points(self, spacing: float = 0.5) -> list[Point]:
        """Generate evenly-spaced sample points along the corridor centerline."""
        points: list[Point] = []
        for i in range(len(self.waypoints) - 1):
            a, b = self.waypoints[i], self.waypoints[i + 1]
            seg_len = a.distance_to(b)
            if seg_len < 1e-6:
                continue
            n_samples = max(1, int(seg_len / spacing))
            for s in range(n_samples + 1):
                t = s / max(n_samples, 1)
                points.append(Point(
                    x=a.x + t * (b.x - a.x),
                    y=a.y + t * (b.y - a.y),
                ))
        return points


# ---------------------------------------------------------------------------
# Zone classification
# ---------------------------------------------------------------------------

def classify_zone(p: Point) -> str:
    """Return court zone label for a point. Matches ISO4D zone taxonomy."""
    dist = p.distance_from_hoop
    in_paint_x = 0 <= p.x <= PAINT_LENGTH_FT
    in_paint_y = abs(p.y) <= PAINT_WIDTH_FT / 2

    if p.x < -COURT_HALF_LENGTH_FT:
        return "backcourt"
    if dist <= RESTRICTED_AREA_RADIUS_FT:
        return "restricted_area"
    if in_paint_x and in_paint_y:
        return "paint"
    if abs(p.y) >= (COURT_WIDTH_FT / 2 - THREE_PT_CORNER_FT) and dist <= THREE_PT_ARC_RADIUS_FT:
        return "corner_3_right" if p.y >= 0 else "corner_3_left"
    if dist >= THREE_PT_ARC_RADIUS_FT:
        return "above_break_3"
    return "mid_range"
