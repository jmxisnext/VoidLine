"""
adapter — Bridges extraction output to VoidLine constraints.

Takes structured game state (positions, velocities) and generates
constraint objects suitable for the TickEngine.
"""

from adapter.constraint_generator import constraints_from_extraction  # noqa: F401
