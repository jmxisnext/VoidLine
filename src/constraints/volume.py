"""
constraints.volume
==================
Compute constraint volume from boundary geometry.

Replaces hand-authored magic numbers with geometrically derived values.
Volume = fraction of relevant court area removed by a constraint's boundary.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.field.space_model import Circle, Cone

# Half-court action space: 47 ft deep x 50 ft wide = 2350 sq ft.
# Effective action space is roughly half (one side of court): ~1175 sq ft.
HALF_COURT_AREA_SQFT = 47.0 * 25.0  # 1175.0


def compute_boundary_volume(
    boundary: Circle | Cone | None,
    court_area: float = HALF_COURT_AREA_SQFT,
) -> float:
    """Compute the fraction of court area removed by a boundary.

    Returns a float in [0, 1]. Zero for non-spatial boundaries.
    """
    if boundary is None:
        return 0.0

    type_name = type(boundary).__name__

    if type_name == "Circle":
        area = math.pi * boundary.radius ** 2
        return min(1.0, area / court_area)

    if type_name == "Cone":
        # Approximate cone as a circular sector.
        # Effective reach defaults to 10 ft if not inferrable.
        reach = 10.0
        sector_fraction = (2 * boundary.half_angle_deg) / 360.0
        area = math.pi * reach ** 2 * sector_fraction
        return min(1.0, area / court_area)

    return 0.0
