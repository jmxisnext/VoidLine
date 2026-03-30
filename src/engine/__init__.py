"""
engine — Tick loop orchestrator.

Advances time, computes possibility fields, lets agents
select from surviving space, updates memory.
"""

from src.engine.tick import EventKind, Snapshot, TickEngine, TickEvent

__all__ = ["EventKind", "Snapshot", "TickEngine", "TickEvent"]
