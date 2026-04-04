"""
adapter.scheme
==============
Defensive scheme engine: generates defender entities from offensive state
and scheme logic.

This is not state extraction. This is constraint generation from scheme
rules — exactly the kind of spatial reasoning VoidLine is built to evaluate.

Pipeline position:
    Offensive extraction (ISO4D) + Scheme
        -> scheme.generate_defenders()
        -> injected into extraction dict
        -> adapter.constraints_from_extraction() (unchanged)
        -> VoidLine engine (unchanged)

Design decisions:
    - Defenders are entity dicts in the same format as extraction entities.
      This means existing adapter code works without modification.
    - Each defender archetype has position logic driven by the ball handler's
      state and the scheme parameters.
    - Reaction delay is modeled by reading ball handler state from N frames
      ago, creating natural defensive lag.
    - Velocities are derived from position via central differences.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Scheme definitions
# ---------------------------------------------------------------------------

class Scheme(Enum):
    DROP = "drop"
    ICE = "ice"
    HELP_HEAVY = "help_heavy"


# Per-scheme tuning.  Each key controls one aspect of defender behavior.
#   onball_gap:          distance (ft) between on-ball defender and handler
#   onball_deny_middle:  if True, position to force baseline rather than
#                        splitting the handler-to-basket line
#   help_rotation:       0..1, how aggressively help rotates toward ball
#   help_home:           (x, y) base position in ISO4D feet
#   rim_anchor:          (x, y) base position for rim protector
#   rim_drift:           0..1, how much rim protector drifts toward ball side
#   reaction_frames:     frames of lag before defenders react to handler motion

SCHEME_PARAMS: dict[Scheme, dict] = {
    Scheme.DROP: {
        "onball_gap": 5.0,
        "onball_deny_middle": False,
        "help_depth": 0.65,        # fraction of handler-to-basket distance
        "help_lane_offset": 3.0,   # feet toward lane center (y toward 0)
        "help_rotation": 0.35,     # moderate gap awareness
        "rim_depth": 0.85,         # fraction of handler-to-basket distance
        "rim_lane_offset": 3.0,
        "reaction_frames": 3,      # slow reaction — drop = passive
    },
    Scheme.ICE: {
        "onball_gap": 4.0,
        "onball_deny_middle": True,
        "help_depth": 0.60,
        "help_lane_offset": 5.0,   # wider — denies middle, protects weak side
        "help_rotation": 0.25,
        "rim_depth": 0.80,
        "rim_lane_offset": 2.0,
        "reaction_frames": 2,
    },
    Scheme.HELP_HEAVY: {
        "onball_gap": 3.0,
        "onball_deny_middle": False,
        "help_depth": 0.65,        # closer to ball — aggressive gap help
        "help_lane_offset": 2.0,   # tight to driving lane
        "help_rotation": 0.7,
        "rim_depth": 0.75,
        "rim_lane_offset": 4.0,
        "reaction_frames": 1,      # fast reaction — help-heavy = aggressive
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_defenders(
    extraction: dict,
    ball_handler_id: str,
    scheme: Scheme,
) -> list[dict]:
    """Generate defender entities from offensive state and scheme logic.

    Parameters
    ----------
    extraction : dict
        Transformed extraction dict (ISO4D coordinates, feet).
    ball_handler_id : str
        Entity id of the ball handler.
    scheme : Scheme
        Defensive scheme to apply.

    Returns
    -------
    list[dict]
        Defender entity dicts ready to inject into extraction["entities"].
    """
    params = SCHEME_PARAMS[scheme]

    # Get ball handler frames
    bh = _find_entity(extraction, ball_handler_id)
    if bh is None:
        return []

    bh_frames = sorted(bh["frames"], key=lambda f: f["t"])

    defenders = [
        _onball_defender(bh_frames, params),
        _help_defender(bh_frames, params),
        _rim_protector(bh_frames, params),
    ]

    return defenders


def inject_defenders(extraction: dict, defenders: list[dict]) -> dict:
    """Return a new extraction dict with defender entities added."""
    import copy
    combined = copy.deepcopy(extraction)
    combined["entities"].extend(defenders)
    return combined


# ---------------------------------------------------------------------------
# Defender archetypes
# ---------------------------------------------------------------------------

def _onball_defender(bh_frames: list[dict], params: dict) -> dict:
    """On-ball defender: tracks ball handler with scheme-dependent gap.

    DROP/HELP_HEAVY: positions between handler and basket (deny drive).
    ICE: positions to deny middle, forcing baseline.
    """
    gap = params["onball_gap"]
    deny_middle = params["onball_deny_middle"]
    lag = params["reaction_frames"]

    positions: list[tuple[float, float]] = []

    for i, frame in enumerate(bh_frames):
        # Read from lagged frame for reaction delay
        src = bh_frames[max(0, i - lag)]
        bx, by = src["pos"]

        dist = math.hypot(bx, by)
        if dist < 0.1:
            dist = 0.1

        if deny_middle:
            # ICE: offset perpendicular to baseline, toward center court
            # Forces handler toward sideline/baseline
            ux = -bx / dist  # toward basket (x component)
            # Shift toward y=0 (middle of court) to deny that path
            middle_dir = -1.0 if by > 0 else 1.0
            dx = bx + ux * gap * 0.5
            dy = by + middle_dir * gap * 0.87  # sin(60deg) offset
        else:
            # Standard: between handler and basket
            ux, uy = -bx / dist, -by / dist
            dx = bx + ux * gap
            dy = by + uy * gap

        positions.append((dx, dy))

    frames = _positions_to_frames(bh_frames, positions)
    return {"id": "D1_onball", "role": "defender", "frames": frames}


def _help_defender(bh_frames: list[dict], params: dict) -> dict:
    """Help-side defender: positions in the driving gap between handler and basket.

    Position is ball-relative: a fraction of the way from handler to basket,
    offset toward the lane center. This keeps the help defender in the
    driving lane regardless of where the ball handler is on the court.

    help_depth controls how deep toward the basket (0 = at handler, 1 = at rim).
    help_lane_offset shifts toward y=0 (lane center), denying middle drives.
    help_rotation controls how much the help closes toward the ball under pressure.
    """
    depth = params["help_depth"]
    lane_offset = params["help_lane_offset"]
    rotation = params["help_rotation"]
    lag = params["reaction_frames"]

    positions: list[tuple[float, float]] = []

    for i, frame in enumerate(bh_frames):
        src = bh_frames[max(0, i - lag)]
        bx, by = src["pos"]

        # Base position: fraction of the way from handler to basket
        base_x = bx * (1.0 - depth)  # depth=0.5 → halfway to basket
        base_y = by * (1.0 - depth)

        # Offset toward lane center (y=0)
        if abs(by) > 0.1:
            lane_dir = -1.0 if by > 0 else 1.0
        else:
            lane_dir = 0.0
        base_y += lane_dir * lane_offset

        # Rotation: close toward ball under pressure (blend toward handler)
        hx = base_x + rotation * (bx - base_x)
        hy = base_y + rotation * (by - base_y)

        positions.append((hx, hy))

    frames = _positions_to_frames(bh_frames, positions)
    return {"id": "D2_help", "role": "defender", "frames": frames}


def _rim_protector(bh_frames: list[dict], params: dict) -> dict:
    """Rim protector: deep in the lane, shading toward ball side.

    Position is ball-relative: deep toward the basket (high depth fraction),
    offset toward the lane center. Provides paint denial and weak-side help.
    """
    depth = params["rim_depth"]
    lane_offset = params["rim_lane_offset"]
    lag = params["reaction_frames"]

    positions: list[tuple[float, float]] = []

    for i, frame in enumerate(bh_frames):
        src = bh_frames[max(0, i - lag)]
        bx, by = src["pos"]

        # Deep position along handler-to-basket line
        rx = bx * (1.0 - depth)
        ry = by * (1.0 - depth)

        # Offset toward lane center
        if abs(by) > 0.1:
            lane_dir = -1.0 if by > 0 else 1.0
        else:
            lane_dir = 0.0
        ry += lane_dir * lane_offset

        positions.append((rx, ry))

    frames = _positions_to_frames(bh_frames, positions)
    return {"id": "D3_rim", "role": "defender", "frames": frames}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_entity(extraction: dict, entity_id: str) -> Optional[dict]:
    for e in extraction.get("entities", []):
        if e["id"] == entity_id:
            return e
    return None


def _positions_to_frames(
    reference_frames: list[dict],
    positions: list[tuple[float, float]],
) -> list[dict]:
    """Convert position list to frame dicts with computed velocities.

    Velocities via central differences; endpoints use forward/backward.
    """
    n = len(positions)
    frames = []

    for i in range(n):
        t = reference_frames[i]["t"]
        x, y = positions[i]

        # Central difference velocity
        if i == 0:
            dt = reference_frames[1]["t"] - reference_frames[0]["t"]
            vx = (positions[1][0] - positions[0][0]) / dt
            vy = (positions[1][1] - positions[0][1]) / dt
        elif i == n - 1:
            dt = reference_frames[-1]["t"] - reference_frames[-2]["t"]
            vx = (positions[-1][0] - positions[-2][0]) / dt
            vy = (positions[-1][1] - positions[-2][1]) / dt
        else:
            dt = reference_frames[i + 1]["t"] - reference_frames[i - 1]["t"]
            vx = (positions[i + 1][0] - positions[i - 1][0]) / dt
            vy = (positions[i + 1][1] - positions[i - 1][1]) / dt

        frames.append({"t": t, "pos": [x, y], "vel": [vx, vy]})

    return frames
