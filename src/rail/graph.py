"""
rail.graph
==========
RailGraph loader and topology model.

The rail is scaffold — it defines where agents CAN go.
The possibility field (envelope) defines what's actually viable right now.

This module loads a RailGraph from JSON, validates it against the schema,
and exposes topology queries. Corridor viability is computed by projecting
the possibility field onto each edge's physical geometry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import jsonschema

from src.field.space_model import Point, Corridor, Circle, Cone
from src.constraints.types import Constraint

SCHEMA_PATH = Path(__file__).parent.parent.parent / "schemas" / "railgraph.schema.json"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RailNode:
    """A position or decision point in the authored topology."""

    id: str
    node_type: str  # start | junction | terminal | waypoint
    position: Point
    roles_allowed: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)

    @property
    def is_junction(self) -> bool:
        return self.node_type == "junction"

    @property
    def is_terminal(self) -> bool:
        return self.node_type == "terminal"


@dataclass(frozen=True)
class RailEdge:
    """
    A corridor connecting two nodes — the physical space on court
    that an agent traverses. Corridor geometry is what gets tested
    against the possibility field.
    """

    id: str
    from_node: str
    to_node: str
    corridor: Corridor
    nominal_duration: float = 1.0
    capacity: int = 1
    roles_allowed: tuple[str, ...] = ()
    action_type: str = ""
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Corridor viability — the bridge between continuous space and topology
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CorridorViability:
    """
    How much of an edge's corridor survives the current constraint field.

    This is the projection from "2D region is invalidated" to
    "this outgoing edge is degraded by X%."
    """

    edge_id: str
    action_type: str
    total_samples: int
    surviving_samples: int
    blocked_by: dict[str, int] = field(default_factory=dict)  # constraint_name → blocked count

    @property
    def viability(self) -> float:
        """0.0 = fully blocked, 1.0 = fully open."""
        if self.total_samples == 0:
            return 0.0
        return self.surviving_samples / self.total_samples

    @property
    def is_blocked(self) -> bool:
        return self.viability < 0.01

    @property
    def dominant_blocker(self) -> Optional[str]:
        """Which constraint is blocking the most sample points?"""
        if not self.blocked_by:
            return None
        return max(self.blocked_by, key=self.blocked_by.get)  # type: ignore[arg-type]


def compute_corridor_viability(
    edge: RailEdge,
    constraints: list[Constraint],
    timestamp: float,
    sample_spacing: float = 0.5,
) -> CorridorViability:
    """
    Sample points along a corridor and test each against active spatial
    constraints. Returns the fraction of the corridor that survives.

    Only constraints with Circle boundaries participate in spatial testing.
    Non-spatial constraints (temporal, role, risk) affect viability through
    the PossibilityField, not through corridor geometry.
    """
    samples = edge.corridor.sample_points(spacing=sample_spacing)
    if not samples:
        return CorridorViability(
            edge_id=edge.id,
            action_type=edge.action_type,
            total_samples=0,
            surviving_samples=0,
        )

    active_spatial = [
        c for c in constraints
        if c.is_active(timestamp) and isinstance(c.boundary, (Circle, Cone))
    ]

    blocked_by: dict[str, int] = {}
    surviving = 0

    for pt in samples:
        blocked = False
        for c in active_spatial:
            if isinstance(c.boundary, Circle) and c.boundary.contains_point(pt):
                blocked_by[c.name] = blocked_by.get(c.name, 0) + 1
                blocked = True
                break  # first blocker wins for this sample
            if isinstance(c.boundary, Cone) and c.boundary.contains_point(pt):
                blocked_by[c.name] = blocked_by.get(c.name, 0) + 1
                blocked = True
                break
        if not blocked:
            surviving += 1

    return CorridorViability(
        edge_id=edge.id,
        action_type=edge.action_type,
        total_samples=len(samples),
        surviving_samples=surviving,
        blocked_by=blocked_by,
    )


# ---------------------------------------------------------------------------
# RailGraph — the full topology
# ---------------------------------------------------------------------------

class RailGraph:
    """
    Authored topology loaded from JSON.

    Provides topology queries and corridor viability computation
    against the current constraint field.
    """

    def __init__(
        self,
        nodes: dict[str, RailNode],
        edges: dict[str, RailEdge],
        meta: dict,
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.meta = meta

        # Build adjacency: node_id → list of outgoing edge ids
        self._outgoing: dict[str, list[str]] = {nid: [] for nid in nodes}
        for eid, edge in edges.items():
            if edge.from_node in self._outgoing:
                self._outgoing[edge.from_node].append(eid)

    # --- Topology queries ---

    def outgoing(self, node_id: str, role: Optional[str] = None) -> list[RailEdge]:
        """Edges leaving a node, optionally filtered by role."""
        out = [self.edges[eid] for eid in self._outgoing.get(node_id, [])]
        if role is not None:
            out = [
                e for e in out
                if not e.roles_allowed or role in e.roles_allowed
            ]
        return out

    def junctions(self) -> list[RailNode]:
        """All junction nodes."""
        return [n for n in self.nodes.values() if n.is_junction]

    def terminals(self) -> list[RailNode]:
        """All terminal nodes."""
        return [n for n in self.nodes.values() if n.is_terminal]

    def start_nodes(self) -> list[RailNode]:
        """All start nodes."""
        return [n for n in self.nodes.values() if n.node_type == "start"]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    # --- Corridor viability across all outgoing edges ---

    def corridor_viabilities(
        self,
        node_id: str,
        constraints: list[Constraint],
        timestamp: float,
        role: Optional[str] = None,
        sample_spacing: float = 0.5,
    ) -> list[CorridorViability]:
        """
        Compute viability of every outgoing corridor from a node
        against the current constraint field.

        This is the key bridge: continuous negative space projected
        onto discrete topology.
        """
        out_edges = self.outgoing(node_id, role=role)
        return [
            compute_corridor_viability(edge, constraints, timestamp, sample_spacing)
            for edge in out_edges
        ]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_railgraph(path: str | Path) -> RailGraph:
    """
    Load a RailGraph from a JSON file, validate against schema.

    Raises jsonschema.ValidationError if the file doesn't conform.
    """
    path = Path(path)
    with open(path) as f:
        raw = json.load(f)

    schema = _load_schema()
    jsonschema.validate(instance=raw, schema=schema)

    meta = raw["meta"]

    # Build nodes
    nodes: dict[str, RailNode] = {}
    for n in raw["nodes"]:
        pos = n["position"]
        nodes[n["id"]] = RailNode(
            id=n["id"],
            node_type=n["type"],
            position=Point(x=pos[0], y=pos[1], z=pos[2] if len(pos) > 2 else 0.0),
            roles_allowed=tuple(n.get("roles_allowed", [])),
            metadata=n.get("metadata", {}),
        )

    # Build edges
    edges: dict[str, RailEdge] = {}
    for e in raw["edges"]:
        waypoints = tuple(Point(x=wp[0], y=wp[1]) for wp in e["corridor"])
        corridor = Corridor(waypoints=waypoints, width=e.get("corridor_width", 1.5))
        edges[e["id"]] = RailEdge(
            id=e["id"],
            from_node=e["from"],
            to_node=e["to"],
            corridor=corridor,
            nominal_duration=e.get("nominal_duration", 1.0),
            capacity=e.get("capacity", 1),
            roles_allowed=tuple(e.get("roles_allowed", [])),
            action_type=e.get("action_type", ""),
            metadata=e.get("metadata", {}),
        )

    # Validate referential integrity
    for eid, edge in edges.items():
        if edge.from_node not in nodes:
            raise ValueError(f"Edge '{eid}' references unknown from_node '{edge.from_node}'")
        if edge.to_node not in nodes:
            raise ValueError(f"Edge '{eid}' references unknown to_node '{edge.to_node}'")

    return RailGraph(nodes=nodes, edges=edges, meta=meta)
