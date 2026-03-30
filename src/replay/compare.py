"""
replay.compare
==============
Compare two aligned timelines to produce per-tick divergence records
and an aggregate summary.

Both timelines must have the same length and matching timestamps
(guaranteed when the replay is produced by ``fork.run_replay``).
"""

from __future__ import annotations

from typing import Optional

from src.engine.tick import Snapshot, TickEvent
from src.replay.models import (
    CORRIDOR_CHANGE_THRESHOLD,
    TickDivergence,
    ReplaySummary,
)


# ---------------------------------------------------------------------------
# Per-tick comparison
# ---------------------------------------------------------------------------

def _event_names(events: list[TickEvent]) -> set[tuple[str, str]]:
    """Hashable identity for events: (kind.value, name)."""
    return {(e.kind.value, e.name) for e in events}


def _compare_tick(baseline: Snapshot, replay: Snapshot) -> TickDivergence:
    volume_delta = replay.field.surviving_volume - baseline.field.surviving_volume
    pressure_delta = replay.field.space_pressure - baseline.field.space_pressure

    # Viability deltas keyed by edge_id
    base_viab = {v.edge_id: v.viability for v in baseline.viabilities}
    rep_viab = {v.edge_id: v.viability for v in replay.viabilities}
    all_edges = set(base_viab) | set(rep_viab)
    viability_deltas = {
        eid: rep_viab.get(eid, 0.0) - base_viab.get(eid, 0.0)
        for eid in sorted(all_edges)
    }

    # Event diff
    base_ids = _event_names(baseline.events)
    rep_ids = _event_names(replay.events)
    baseline_only = [e for e in baseline.events if (e.kind.value, e.name) not in rep_ids]
    replay_only = [e for e in replay.events if (e.kind.value, e.name) not in base_ids]

    return TickDivergence(
        timestamp=baseline.timestamp,
        volume_delta=volume_delta,
        pressure_delta=pressure_delta,
        viability_deltas=viability_deltas,
        baseline_only_events=baseline_only,
        replay_only_events=replay_only,
    )


# ---------------------------------------------------------------------------
# Full timeline comparison
# ---------------------------------------------------------------------------

def compare_timelines(
    baseline_segment: list[Snapshot],
    replay_segment: list[Snapshot],
) -> tuple[list[TickDivergence], Optional[int]]:
    """
    Compare two aligned timelines tick-by-tick.

    Returns ``(divergences, first_divergence_index)``.
    ``first_divergence_index`` is ``None`` if timelines are identical.
    """
    divergences: list[TickDivergence] = []
    first_div: Optional[int] = None

    for i, (b, r) in enumerate(zip(baseline_segment, replay_segment)):
        div = _compare_tick(b, r)
        divergences.append(div)
        if first_div is None and div.is_divergent:
            first_div = i

    return divergences, first_div


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def compute_summary(
    divergences: list[TickDivergence],
    first_divergence_index: Optional[int],
) -> ReplaySummary:
    """Build aggregate metrics from per-tick divergence records."""
    if not divergences:
        return ReplaySummary(
            fork_timestamp=0.0,
            end_timestamp=0.0,
            total_ticks=0,
            divergent_ticks=0,
            first_divergence_timestamp=None,
            max_volume_delta=0.0,
            max_pressure_delta=0.0,
            corridors_changed=[],
            max_corridor_delta_by_edge={},
        )

    fork_ts = divergences[0].timestamp
    end_ts = divergences[-1].timestamp
    divergent_count = sum(1 for d in divergences if d.is_divergent)

    first_div_ts: Optional[float] = None
    if first_divergence_index is not None:
        first_div_ts = divergences[first_divergence_index].timestamp

    max_vol = max((abs(d.volume_delta) for d in divergences), default=0.0)
    max_pres = max((abs(d.pressure_delta) for d in divergences), default=0.0)

    # Per-edge max absolute delta across all ticks
    edge_max: dict[str, float] = {}
    for d in divergences:
        for eid, delta in d.viability_deltas.items():
            edge_max[eid] = max(edge_max.get(eid, 0.0), abs(delta))

    corridors_changed = sorted(
        eid for eid, delta in edge_max.items()
        if delta >= CORRIDOR_CHANGE_THRESHOLD
    )

    return ReplaySummary(
        fork_timestamp=fork_ts,
        end_timestamp=end_ts,
        total_ticks=len(divergences),
        divergent_ticks=divergent_count,
        first_divergence_timestamp=first_div_ts,
        max_volume_delta=max_vol,
        max_pressure_delta=max_pres,
        corridors_changed=corridors_changed,
        max_corridor_delta_by_edge=edge_max,
    )
