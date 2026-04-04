"""
integration_iso3.py
====================
End-to-end integration: ISO4D extraction + defensive scheme -> VoidLine.

Pipeline:
    1. Load frozen extraction artifact (offensive tracks)
    2. Transform coordinates (ui_halfcourt_normalized -> ISO4D feet)
    3. Generate defenders from scheme logic (adapter.scheme)
    4. Per-frame constraint generation (adapter.constraint_generator)
    5. Possibility field computation
    6. Compare: schemes x delay

Tests whether temporal input + scheme-driven defense produces stable,
meaningful, and timing-sensitive constraint behavior.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from adapter.constraint_generator import constraints_from_extraction
from adapter.scheme import Scheme, generate_defenders, inject_defenders
from src.envelope.field import compute_field
from src.field.space_model import COURT_HALF_LENGTH_FT, COURT_WIDTH_FT


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EXTRACTION_PATH = Path("J:/projects/ISO4D/data/reference/beta_is3_playui_tracks.json")
AGENT_ID = "PG"
DELAY_S = 0.3
SCHEMES = [Scheme.DROP, Scheme.ICE, Scheme.HELP_HEAVY]


# ---------------------------------------------------------------------------
# Coordinate transform
# ---------------------------------------------------------------------------

def transform_extraction(raw: dict) -> dict:
    """Convert ui_halfcourt_normalized -> ISO4D feet."""
    transformed = copy.deepcopy(raw)
    transformed["coordinate_system"] = "iso4d"

    for entity in transformed["entities"]:
        for frame in entity["frames"]:
            px, py = frame["pos"]
            vx, vy = frame["vel"]
            frame["pos"] = [
                (py - 1.0) * COURT_HALF_LENGTH_FT,
                (px - 0.5) * COURT_WIDTH_FT,
            ]
            frame["vel"] = [
                vy * COURT_HALF_LENGTH_FT,
                vx * COURT_WIDTH_FT,
            ]

    return transformed


# ---------------------------------------------------------------------------
# Per-frame evaluation
# ---------------------------------------------------------------------------

def evaluate_timeline(
    extraction: dict,
    agent_id: str,
    timestamps: list[float],
    time_offset: float = 0.0,
) -> list[dict]:
    """Evaluate constraints and field at each timestamp."""
    results = []
    for t in timestamps:
        read_t = t - time_offset

        constraints = constraints_from_extraction(extraction, agent_id, read_t)
        field = compute_field(agent_id, t, constraints)

        dominant = field.dominant_removal()

        # Collect per-constraint detail
        constraint_names = sorted(c.name for c in field.active_constraints)

        results.append({
            "t": t,
            "read_t": read_t,
            "pressure": field.space_pressure,
            "surviving": field.surviving_volume,
            "n_constraints": len(field.active_constraints),
            "dominant": dominant.constraint_name if dominant else "-",
            "dominant_vol": dominant.volume_removed if dominant else 0.0,
            "constraints": constraint_names,
        })

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_timeline(label: str, results: list[dict]) -> None:
    print(f"\n{'=' * 78}")
    print(f"  {label}")
    print(f"{'=' * 78}")
    print(f"  {'t':>5s}  {'press':>6s}  {'surv':>6s}  "
          f"{'#c':>3s}  {'dominant':>20s}  {'constraints'}")
    print(f"  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*3}  {'-'*20}  {'-'*30}")

    for r in results:
        cnames = ", ".join(r["constraints"]) if r["constraints"] else "-"
        print(f"  {r['t']:5.1f}  {r['pressure']:6.1%}  {r['surviving']:6.1%}  "
              f"{r['n_constraints']:3d}  {r['dominant']:>20s}  {cnames}")


def print_scheme_comparison(scheme_results: dict[str, list[dict]]) -> None:
    """Compare pressure across schemes at each timestamp."""
    print(f"\n{'=' * 78}")
    print("  SCHEME COMPARISON (normal read)")
    print(f"{'=' * 78}")

    names = list(scheme_results.keys())
    header = f"  {'t':>5s}"
    for name in names:
        header += f"  {name:>12s}"
    print(header)
    print(f"  {'-'*5}" + f"  {'-'*12}" * len(names))

    n_frames = len(next(iter(scheme_results.values())))
    for i in range(n_frames):
        t = next(iter(scheme_results.values()))[i]["t"]
        line = f"  {t:5.1f}"
        for name in names:
            p = scheme_results[name][i]["pressure"]
            line += f"  {p:12.1%}"
        print(line)


def print_delay_comparison(
    scheme_name: str,
    normal: list[dict],
    delayed: list[dict],
) -> None:
    print(f"\n{'=' * 78}")
    print(f"  {scheme_name}: normal vs +{DELAY_S:.1f}s delay")
    print(f"{'=' * 78}")
    print(f"  {'t':>5s}  {'normal':>8s}  {'delayed':>8s}  {'delta':>8s}  {'shift':>10s}")
    print(f"  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*10}")

    for n, d in zip(normal, delayed):
        delta = d["pressure"] - n["pressure"]
        shift = "MORE" if delta > 0.005 else ("LESS" if delta < -0.005 else "~same")
        print(f"  {n['t']:5.1f}  {n['pressure']:8.1%}  {d['pressure']:8.1%}  "
              f"{delta:+8.3f}  {shift:>10s}")

    deltas = [d["pressure"] - n["pressure"] for n, d in zip(normal, delayed)]
    print(f"\n  avg delta: {sum(deltas)/len(deltas):+.4f}   "
          f"max delta: {max(deltas, key=abs):+.4f}   "
          f"jitter(n): {_jitter(normal):.4f}   "
          f"jitter(d): {_jitter(delayed):.4f}")


def _jitter(results: list[dict]) -> float:
    if len(results) < 2:
        return 0.0
    diffs = [abs(results[i+1]["pressure"] - results[i]["pressure"])
             for i in range(len(results) - 1)]
    return sum(diffs) / len(diffs)


# ---------------------------------------------------------------------------
# Signal checks
# ---------------------------------------------------------------------------

def run_signal_checks(scheme_results: dict[str, tuple]) -> None:
    """Validate signal quality across all schemes."""
    print(f"\n{'=' * 78}")
    print("  SIGNAL CHECKS")
    print(f"{'=' * 78}")

    for scheme_name, (normal, delayed) in scheme_results.items():
        print(f"\n  --- {scheme_name} ---")

        # Smooth pressure
        jitter = _jitter(normal)
        print(f"  Smooth (jitter < 0.03):     {'PASS' if jitter < 0.03 else 'FAIL'} "
              f"({jitter:.4f})")

        # Delay produces shift
        deltas = [abs(d["pressure"] - n["pressure"]) for n, d in zip(normal, delayed)]
        max_d = max(deltas)
        print(f"  Delay shift (max > 0.01):   {'PASS' if max_d > 0.01 else 'FAIL'} "
              f"({max_d:.4f})")

        # Peak pressure meaningful
        peak = max(r["pressure"] for r in normal)
        print(f"  Peak pressure (> 0.15):     {'PASS' if peak > 0.15 else 'FAIL'} "
              f"({peak:.1%})")

        # Multiple constraint sources
        all_constraints = set()
        for r in normal:
            all_constraints.update(r["constraints"])
        spatial = [c for c in all_constraints if c.startswith("defender_")]
        print(f"  Multiple defenders active:  {'PASS' if len(spatial) >= 2 else 'FAIL'} "
              f"({len(spatial)} spatial: {', '.join(sorted(spatial))})")

    # Cross-scheme: pressure ordering
    print(f"\n  --- Cross-scheme ---")
    peaks = {name: max(r["pressure"] for r in nr)
             for name, (nr, _) in scheme_results.items()}
    print(f"  Peak pressures: " +
          ", ".join(f"{n}={p:.1%}" for n, p in sorted(peaks.items(), key=lambda x: -x[1])))
    if peaks.get("help_heavy", 0) > peaks.get("drop", 0):
        print(f"  help_heavy > drop:          PASS (scheme differentiation)")
    else:
        print(f"  help_heavy > drop:          CHECK (unexpected ordering)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not EXTRACTION_PATH.exists():
        print(f"ERROR: extraction artifact not found: {EXTRACTION_PATH}")
        sys.exit(1)

    with open(EXTRACTION_PATH) as f:
        raw = json.load(f)

    extraction = transform_extraction(raw)

    agent_entity = next(e for e in extraction["entities"] if e["id"] == AGENT_ID)
    timestamps = sorted(set(f["t"] for f in agent_entity["frames"]))

    print(f"Source:       {EXTRACTION_PATH.name}")
    print(f"Ball handler: {AGENT_ID}")
    print(f"Delay:        {DELAY_S}s")
    print(f"Frames:       {len(timestamps)} ({timestamps[0]:.1f} -> {timestamps[-1]:.1f})")
    print(f"Schemes:      {', '.join(s.value for s in SCHEMES)}")

    # Run each scheme
    all_normal: dict[str, list[dict]] = {}
    all_pairs: dict[str, tuple] = {}

    for scheme in SCHEMES:
        defenders = generate_defenders(extraction, AGENT_ID, scheme)
        combined = inject_defenders(extraction, defenders)

        defs_summary = ", ".join(
            f"{d['id']}" for d in defenders
        )
        print(f"\n  [{scheme.value}] defenders: {defs_summary}")

        normal = evaluate_timeline(combined, AGENT_ID, timestamps, time_offset=0.0)
        delayed = evaluate_timeline(combined, AGENT_ID, timestamps, time_offset=DELAY_S)

        print_timeline(f"{scheme.value.upper()} - normal", normal)
        print_delay_comparison(scheme.value.upper(), normal, delayed)

        all_normal[scheme.value] = normal
        all_pairs[scheme.value] = (normal, delayed)

    # Cross-scheme comparison
    print_scheme_comparison(all_normal)

    # Signal checks
    run_signal_checks(all_pairs)


if __name__ == "__main__":
    main()
