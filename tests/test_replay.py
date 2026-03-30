"""
Tests for the replay system — single-fork counterfactual analysis.

Covers:
  - The "help defender not rotated" demo case
  - Snapshot immutability contract
  - Precondition validation
  - Fork-tick event comparison semantics
  - ConstraintChanges precedence rules
  - Summary fields (first_divergence_timestamp, max_corridor_delta_by_edge)
  - No-change replay produces no divergence
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from src.field.space_model import Point, Circle, TimeWindow
from src.constraints.types import (
    Constraint,
    SpatialConstraint,
    ConstraintDynamics,
    ConstraintSource,
    Stability,
)
from src.engine.tick import EventKind, Snapshot, TickEngine
from src.rail.graph import load_railgraph
from src.replay import (
    ConstraintChanges,
    ReplayPreconditionError,
    ReplayResult,
    replay_from_tick,
)
from src.replay.models import VOLUME_EPSILON, VIABILITY_EPSILON, CORRIDOR_CHANGE_THRESHOLD


SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"


@pytest.fixture
def pnr_graph():
    return load_railgraph(SCENARIOS_DIR / "pnr_basic.json")


@pytest.fixture
def baseline(pnr_graph, pnr_constraints):
    """Baseline PNR timeline, t=0.0 to t=2.0, dt=0.1."""
    engine = TickEngine(
        pnr_graph, pnr_constraints, "PG_01", "screen_point", role="ball_handler",
    )
    return engine.run(duration=2.0, dt=0.1)


# ---------------------------------------------------------------------------
# Demo: "What if the help defender had not rotated?"
# ---------------------------------------------------------------------------

class TestHelpDefenderDemo:
    def test_help_persists_increases_late_pressure(self, baseline, pnr_graph, pnr_constraints):
        """
        Replace help_defender_paint (expires t=1.2) with a sustained version
        that never expires.  Pressure should stay higher in the replay.
        """
        help_original = next(c for c in pnr_constraints if c.name == "help_defender_paint")
        help_persistent = SpatialConstraint(
            name="help_defender_paint",
            source=help_original.source,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=help_original.boundary,
            volume=help_original.volume,
            agent_id=help_original.agent_id,
        )
        changes = ConstraintChanges(replace={"help_defender_paint": help_persistent})
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )

        # After t=1.2, baseline help expired → lower pressure.
        # Replay help persists → higher pressure.
        late_div = [d for d in result.divergences if d.timestamp >= 1.2]
        assert len(late_div) > 0
        for d in late_div:
            assert d.pressure_delta > 0  # replay has more pressure

    def test_drive_left_stays_degraded(self, baseline, pnr_graph, pnr_constraints):
        """drive_left should be less viable in replay where help persists."""
        help_original = next(c for c in pnr_constraints if c.name == "help_defender_paint")
        help_persistent = SpatialConstraint(
            name="help_defender_paint",
            source=help_original.source,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=help_original.boundary,
            volume=help_original.volume,
            agent_id=help_original.agent_id,
        )
        changes = ConstraintChanges(replace={"help_defender_paint": help_persistent})
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )

        # After help would have expired, drive_left should be worse in replay
        late_div = [d for d in result.divergences if d.timestamp >= 1.3]
        for d in late_div:
            assert d.viability_deltas["drive_left"] < 0  # replay worse

    def test_first_divergence_near_help_expiry(self, baseline, pnr_graph, pnr_constraints):
        """First divergence should be around t=1.2 when help would have expired."""
        help_original = next(c for c in pnr_constraints if c.name == "help_defender_paint")
        help_persistent = SpatialConstraint(
            name="help_defender_paint",
            source=help_original.source,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=help_original.boundary,
            volume=help_original.volume,
            agent_id=help_original.agent_id,
        )
        changes = ConstraintChanges(replace={"help_defender_paint": help_persistent})
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )

        assert result.first_divergence_index is not None
        div_ts = result.summary.first_divergence_timestamp
        assert div_ts is not None
        # First material field divergence should be at or just after 1.2
        assert 1.1 <= div_ts <= 1.3

    def test_summary_corridors_changed(self, baseline, pnr_graph, pnr_constraints):
        """Summary should identify drive_left as a changed corridor."""
        help_original = next(c for c in pnr_constraints if c.name == "help_defender_paint")
        help_persistent = SpatialConstraint(
            name="help_defender_paint",
            source=help_original.source,
            dynamics=ConstraintDynamics(stability=Stability.SUSTAINED),
            boundary=help_original.boundary,
            volume=help_original.volume,
            agent_id=help_original.agent_id,
        )
        changes = ConstraintChanges(replace={"help_defender_paint": help_persistent})
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )

        assert "drive_left" in result.summary.corridors_changed
        assert "drive_left" in result.summary.max_corridor_delta_by_edge
        assert result.summary.max_corridor_delta_by_edge["drive_left"] >= CORRIDOR_CHANGE_THRESHOLD


# ---------------------------------------------------------------------------
# Snapshot immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_baseline_unchanged_after_replay(self, baseline, pnr_graph, pnr_constraints):
        """Replay must not mutate the baseline timeline."""
        baseline_copy = copy.deepcopy(baseline)

        changes = ConstraintChanges(remove=["onball_defender_left_shade"])
        replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )

        # Compare every snapshot's field and viability values
        for orig, saved in zip(baseline, baseline_copy):
            assert orig.timestamp == saved.timestamp
            assert orig.field.surviving_volume == saved.field.surviving_volume
            assert len(orig.field.active_constraints) == len(saved.field.active_constraints)
            for v1, v2 in zip(orig.viabilities, saved.viabilities):
                assert v1.viability == v2.viability

    def test_original_constraints_unchanged(self, baseline, pnr_graph, pnr_constraints):
        """The original constraint list must not be mutated."""
        names_before = [c.name for c in pnr_constraints]
        volumes_before = [c.volume for c in pnr_constraints]

        changes = ConstraintChanges(remove=["onball_defender_left_shade"])
        replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )

        assert [c.name for c in pnr_constraints] == names_before
        assert [c.volume for c in pnr_constraints] == volumes_before


# ---------------------------------------------------------------------------
# Precondition validation
# ---------------------------------------------------------------------------

class TestPreconditions:
    def test_empty_baseline_raises(self, pnr_graph, pnr_constraints):
        with pytest.raises(ReplayPreconditionError, match="empty"):
            replay_from_tick(
                [], pnr_graph, pnr_constraints,
                fork_tick=0, changes=ConstraintChanges(),
                node_id="screen_point",
            )

    def test_fork_tick_out_of_range_raises(self, baseline, pnr_graph, pnr_constraints):
        with pytest.raises(ReplayPreconditionError, match="out of range"):
            replay_from_tick(
                baseline, pnr_graph, pnr_constraints,
                fork_tick=999, changes=ConstraintChanges(),
                node_id="screen_point",
            )

    def test_negative_fork_tick_raises(self, baseline, pnr_graph, pnr_constraints):
        with pytest.raises(ReplayPreconditionError, match="out of range"):
            replay_from_tick(
                baseline, pnr_graph, pnr_constraints,
                fork_tick=-1, changes=ConstraintChanges(),
                node_id="screen_point",
            )

    def test_unknown_node_raises(self, baseline, pnr_graph, pnr_constraints):
        with pytest.raises(ReplayPreconditionError, match="not found in graph"):
            replay_from_tick(
                baseline, pnr_graph, pnr_constraints,
                fork_tick=0, changes=ConstraintChanges(),
                node_id="nonexistent_node",
            )

    def test_unknown_remove_name_raises(self, baseline, pnr_graph, pnr_constraints):
        with pytest.raises(ReplayPreconditionError, match="unknown constraint"):
            replay_from_tick(
                baseline, pnr_graph, pnr_constraints,
                fork_tick=0, changes=ConstraintChanges(remove=["ghost"]),
                node_id="screen_point",
            )

    def test_unknown_replace_name_raises(self, baseline, pnr_graph, pnr_constraints):
        dummy = SpatialConstraint(
            name="ghost", source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=None, volume=0.1,
        )
        with pytest.raises(ReplayPreconditionError, match="unknown constraint"):
            replay_from_tick(
                baseline, pnr_graph, pnr_constraints,
                fork_tick=0, changes=ConstraintChanges(replace={"ghost": dummy}),
                node_id="screen_point",
            )


# ---------------------------------------------------------------------------
# Fork-tick event semantics
# ---------------------------------------------------------------------------

class TestForkTickEventSemantics:
    def test_fork_at_zero_no_baseline_events(self, baseline, pnr_graph, pnr_constraints):
        """Fork at tick 0: baseline tick 0 has no events (no prev), replay also has none."""
        changes = ConstraintChanges(remove=["onball_defender_left_shade"])
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )
        fork_div = result.divergences[0]
        assert fork_div.baseline_only_events == []
        assert fork_div.replay_only_events == []

    def test_fork_midstream_baseline_events_appear(self, baseline, pnr_graph, pnr_constraints):
        """
        Fork at a tick where baseline has events (constraint just expired).
        Those events should appear as baseline_only, because the replay
        engine has no _prev at its first tick.
        """
        # Find a baseline tick with events
        event_ticks = [(i, s) for i, s in enumerate(baseline) if s.events]
        if not event_ticks:
            pytest.skip("No baseline ticks with events in this run")

        fork_idx, fork_snap = event_ticks[0]
        changes = ConstraintChanges()  # no changes — just re-fork
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=fork_idx, changes=changes, node_id="screen_point", role="ball_handler",
        )
        fork_div = result.divergences[0]
        # Baseline events at fork tick have no replay counterpart
        assert len(fork_div.baseline_only_events) == len(fork_snap.events)

    def test_meaningful_event_divergence_after_fork_tick(self, baseline, pnr_graph, pnr_constraints):
        """
        After fork_tick + 1, both engines have _prev, so event comparison
        is meaningful.  A no-change replay should have no event divergence
        from tick 1 onward.
        """
        changes = ConstraintChanges()
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )
        for div in result.divergences[1:]:
            assert div.baseline_only_events == []
            assert div.replay_only_events == []


# ---------------------------------------------------------------------------
# ConstraintChanges precedence rules
# ---------------------------------------------------------------------------

class TestConstraintChangesPrecedence:
    def test_remove_wins_over_replace(self):
        """If a name is in both remove and replace, remove wins."""
        c = SpatialConstraint(
            name="x", source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=None, volume=0.2,
        )
        replacement = SpatialConstraint(
            name="x", source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=None, volume=0.9,
        )
        changes = ConstraintChanges(remove=["x"], replace={"x": replacement})
        result = changes.apply([c])
        assert len(result) == 0  # removed, not replaced

    def test_add_collision_raises(self):
        """Adding a constraint whose name already exists raises ValueError."""
        existing = SpatialConstraint(
            name="defender", source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=None, volume=0.2,
        )
        duplicate = SpatialConstraint(
            name="defender", source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=None, volume=0.5,
        )
        changes = ConstraintChanges(add=[duplicate])
        with pytest.raises(ValueError, match="collision"):
            changes.apply([existing])

    def test_add_after_remove_no_collision(self):
        """Removing then re-adding a name is allowed."""
        existing = SpatialConstraint(
            name="defender", source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=None, volume=0.2,
        )
        new_version = SpatialConstraint(
            name="defender", source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=None, volume=0.8,
        )
        changes = ConstraintChanges(remove=["defender"], add=[new_version])
        result = changes.apply([existing])
        assert len(result) == 1
        assert result[0].volume == 0.8

    def test_replace_produces_deepcopy(self):
        """Replaced constraint should not share identity with the input."""
        existing = SpatialConstraint(
            name="x", source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=None, volume=0.2,
        )
        replacement = SpatialConstraint(
            name="x", source=ConstraintSource.OPPONENT,
            dynamics=ConstraintDynamics(stability=Stability.STATIC),
            boundary=None, volume=0.9,
        )
        changes = ConstraintChanges(replace={"x": replacement})
        result = changes.apply([existing])
        assert result[0] is not replacement
        assert result[0].volume == 0.9

    def test_is_empty(self):
        assert ConstraintChanges().is_empty
        assert not ConstraintChanges(remove=["x"]).is_empty


# ---------------------------------------------------------------------------
# Summary fields
# ---------------------------------------------------------------------------

class TestSummaryFields:
    def test_first_divergence_timestamp_present(self, baseline, pnr_graph, pnr_constraints):
        changes = ConstraintChanges(remove=["help_defender_paint"])
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )
        assert result.summary.first_divergence_timestamp is not None
        assert result.summary.first_divergence_timestamp >= 0.0

    def test_max_corridor_delta_by_edge_populated(self, baseline, pnr_graph, pnr_constraints):
        changes = ConstraintChanges(remove=["help_defender_paint"])
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )
        assert len(result.summary.max_corridor_delta_by_edge) > 0
        # All deltas should be non-negative (they're absolute values)
        for delta in result.summary.max_corridor_delta_by_edge.values():
            assert delta >= 0.0

    def test_summary_tick_counts(self, baseline, pnr_graph, pnr_constraints):
        changes = ConstraintChanges(remove=["help_defender_paint"])
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )
        assert result.summary.total_ticks == len(result.divergences)
        assert result.summary.divergent_ticks <= result.summary.total_ticks
        assert result.summary.divergent_ticks > 0  # removing help DOES cause divergence


# ---------------------------------------------------------------------------
# No-change replay
# ---------------------------------------------------------------------------

class TestNoChangeReplay:
    def test_empty_changes_no_divergence(self, baseline, pnr_graph, pnr_constraints):
        """Replay with no constraint changes should produce zero divergence."""
        changes = ConstraintChanges()
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=0, changes=changes, node_id="screen_point", role="ball_handler",
        )
        assert result.first_divergence_index is None
        assert result.summary.divergent_ticks == 0
        assert result.summary.max_volume_delta < VOLUME_EPSILON
        assert result.summary.first_divergence_timestamp is None

    def test_empty_changes_mid_timeline(self, baseline, pnr_graph, pnr_constraints):
        """Fork mid-timeline with no changes: still no divergence (except fork-tick events)."""
        changes = ConstraintChanges()
        result = replay_from_tick(
            baseline, pnr_graph, pnr_constraints,
            fork_tick=5, changes=changes, node_id="screen_point", role="ball_handler",
        )
        # Divergence at fork tick may exist due to event framing (see fork-tick semantics)
        # but field/viability should be identical everywhere
        for div in result.divergences:
            assert abs(div.volume_delta) < VOLUME_EPSILON
            for delta in div.viability_deltas.values():
                assert abs(delta) < VIABILITY_EPSILON
