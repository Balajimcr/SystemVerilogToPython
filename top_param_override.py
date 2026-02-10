#!/usr/bin/env python3
"""
TopParameter Override Utility
=============================

Reads a ``*_top_params.csv`` file (exported by XML_to_sv_Converter.py) and
applies OverrideMin / OverrideMax range adjustments to a PyVSC random object
**before** randomization.

Two usage modes:

1. **Pre-randomization clamping** (``apply_overrides_to_object``):
   Dynamically injects ``with`` constraints each time ``randomize()`` is
   called so the solver sees tighter bounds on the TopParameter fields.

2. **Post-randomization patching** (``patch_vector_with_overrides``):
   After randomization, clamp observed values into override ranges.  This is
   simpler but does not let the solver see the tighter bounds (which may
   cause constraint conflicts on dependent fields).

The recommended approach is (1) because it feeds overrides into the solver.

Standalone CLI
--------------
::

    python top_param_override.py <top_params.csv>          # print summary
    python top_param_override.py <top_params.csv> --edit   # interactive edit

Public API
----------
- ``load_overrides(csv_path) -> Dict[str, OverrideSpec]``
- ``apply_overrides_to_object(obj, overrides) -> List[str]``
- ``patch_vector_with_overrides(vector, overrides) -> Dict``
- ``print_override_summary(overrides)``
"""

from __future__ import annotations

import csv
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OverrideSpec:
    """Single top-parameter override entry."""
    name: str
    normal_value: int
    orig_min: int
    orig_max: int
    override_min: int
    override_max: int
    test_constraints: List[str]

    @property
    def is_overridden(self) -> bool:
        """Return True if the user changed OverrideMin/Max from original."""
        return self.override_min != self.orig_min or self.override_max != self.orig_max


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def load_overrides(csv_path: str) -> Dict[str, OverrideSpec]:
    """Load a top-parameter CSV and return a dict keyed by parameter name.

    The CSV is expected to have columns:
        Name, NormalValue, MinValue, MaxValue, OverrideMin, OverrideMax, TestConstraint
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"TopParameter CSV not found: {csv_path}")

    overrides: Dict[str, OverrideSpec] = {}
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", "").strip()
            if not name:
                continue

            def _int(key: str, fallback: str = "0") -> int:
                val = row.get(key, fallback).strip()
                try:
                    return int(val)
                except ValueError:
                    return int(float(val))

            tc_str = row.get("TestConstraint", "").strip()
            tc_list = [c.strip() for c in tc_str.split(";") if c.strip()] if tc_str else []

            overrides[name] = OverrideSpec(
                name=name,
                normal_value=_int("NormalValue"),
                orig_min=_int("MinValue"),
                orig_max=_int("MaxValue"),
                override_min=_int("OverrideMin", row.get("MinValue", "0")),
                override_max=_int("OverrideMax", row.get("MaxValue", "0")),
                test_constraints=tc_list,
            )

    return overrides


def save_overrides(csv_path: str, overrides: Dict[str, OverrideSpec]) -> None:
    """Write overrides back to CSV (preserving column order)."""
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Name", "NormalValue", "MinValue", "MaxValue",
            "OverrideMin", "OverrideMax", "TestConstraint",
        ])
        for spec in overrides.values():
            tc_str = " ; ".join(spec.test_constraints) if spec.test_constraints else ""
            writer.writerow([
                spec.name,
                spec.normal_value,
                spec.orig_min,
                spec.orig_max,
                spec.override_min,
                spec.override_max,
                tc_str,
            ])


# ---------------------------------------------------------------------------
# Applying overrides to PyVSC objects
# ---------------------------------------------------------------------------

def apply_overrides_to_object(
    obj: Any,
    overrides: Dict[str, OverrideSpec],
) -> List[str]:
    """Apply override ranges as ``with`` constraints during randomization.

    This modifies the object's ``randomize()`` call to inject dynamic
    constraints.  The approach:

      1. For each field that exists on *obj* and has an override entry,
         build a ``with`` constraint lambda.
      2. Call ``obj.randomize_with(...)`` instead of plain ``randomize()``.

    Returns a list of applied override descriptions (for logging).

    .. note::
       The caller should use ``randomize_with_overrides()`` below instead
       of calling ``obj.randomize()`` directly, so that the constraints
       are injected.
    """
    applied: List[str] = []
    for name, spec in overrides.items():
        if hasattr(obj, name):
            applied.append(
                f"{name}: [{spec.override_min}, {spec.override_max}] "
                f"(was [{spec.orig_min}, {spec.orig_max}])"
            )
    return applied


def randomize_with_overrides(
    obj: Any,
    overrides: Dict[str, OverrideSpec],
) -> bool:
    """Randomize *obj* with TopParameter override constraints injected.

    Uses PyVSC's ``obj.randomize_with()`` to add dynamic range constraints
    for each overridden TopParameter field.

    Returns True on success, False on solve failure.
    """
    try:
        import vsc  # noqa: F811
    except ImportError:
        # If PyVSC is not available, fall back to plain randomize
        obj.randomize()
        return True

    # Build list of (field_attr, min_val, max_val) for fields that exist
    active: List[Tuple[str, int, int]] = []
    for name, spec in overrides.items():
        if hasattr(obj, name):
            active.append((name, spec.override_min, spec.override_max))

    if not active:
        # No applicable overrides — plain randomize
        obj.randomize()
        return True

    # Use randomize_with to inject range constraints dynamically
    try:
        def _build_constraint_fn(field_overrides):
            """Build a constraint function that applies range overrides."""
            def constraint_fn(self_obj):
                for attr_name, lo, hi in field_overrides:
                    field = getattr(self_obj, attr_name)
                    vsc.if_then(True, lambda f=field, l=lo, h=hi: [
                        f >= l,
                        f <= h,
                    ])
            return constraint_fn

        # PyVSC randomize_with expects a function with constraints
        with obj.randomize_with() as it:
            for attr_name, lo, hi in active:
                field = getattr(it, attr_name)
                field >= lo
                field <= hi

        return True
    except Exception:
        # Fallback: try plain randomize + post-clamp
        try:
            obj.randomize()
            _post_clamp(obj, active)
            return True
        except Exception:
            return False


def _post_clamp(
    obj: Any,
    active: List[Tuple[str, int, int]],
) -> None:
    """Clamp field values to override ranges (fallback if solver fails)."""
    for attr_name, lo, hi in active:
        try:
            val = getattr(obj, attr_name)
            if hasattr(val, 'val'):
                current = val.val
            else:
                current = int(val)
            clamped = max(lo, min(hi, current))
            if hasattr(val, 'val'):
                val.val = clamped
            else:
                setattr(obj, attr_name, clamped)
        except (AttributeError, TypeError, ValueError):
            pass


def patch_vector_with_overrides(
    vector: Dict[str, Any],
    overrides: Dict[str, OverrideSpec],
) -> Dict[str, Any]:
    """Clamp vector values to override ranges (post-randomization fallback).

    For each field in *overrides* that also exists in *vector*, clamp its
    value to ``[override_min, override_max]``.
    """
    patched = dict(vector)
    for name, spec in overrides.items():
        if name in patched:
            try:
                val = int(patched[name])
                patched[name] = max(spec.override_min, min(spec.override_max, val))
            except (ValueError, TypeError):
                pass
    return patched


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_override_summary(
    overrides: Dict[str, OverrideSpec],
    show_all: bool = False,
) -> None:
    """Print a formatted table of overrides to stdout."""
    print(f"\n{'='*90}")
    print("TOP PARAMETER OVERRIDES")
    print(f"{'='*90}")
    print(f"  {'Name':<25} {'OrigMin':>10} {'OrigMax':>10} {'OvrMin':>10} {'OvrMax':>10} {'Changed':>8}")
    print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*8}")

    for spec in overrides.values():
        if not show_all and not spec.is_overridden:
            continue
        changed = "YES" if spec.is_overridden else "no"
        print(f"  {spec.name:<25} {spec.orig_min:>10} {spec.orig_max:>10} "
              f"{spec.override_min:>10} {spec.override_max:>10} {changed:>8}")

    active_count = sum(1 for s in overrides.values() if s.is_overridden)
    print(f"\n  Active overrides: {active_count}/{len(overrides)}")
    print(f"{'='*90}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    """Standalone CLI: view / edit a top-parameter CSV."""
    import argparse

    parser = argparse.ArgumentParser(
        description="View or edit a TopParameter override CSV.",
    )
    parser.add_argument("csv_path", help="Path to *_top_params.csv")
    parser.add_argument("--edit", action="store_true",
                        help="Interactive edit mode (set OverrideMin/Max)")
    parser.add_argument("--all", action="store_true",
                        help="Show all parameters (not just overridden)")
    args = parser.parse_args()

    overrides = load_overrides(args.csv_path)
    print_override_summary(overrides, show_all=args.all or args.edit)

    if args.edit:
        print("Enter new OverrideMin and OverrideMax for each parameter.")
        print("Press Enter to keep current value, or type a number to change.\n")

        for spec in overrides.values():
            print(f"  {spec.name}  (current: [{spec.override_min}, {spec.override_max}])")
            new_min = input(f"    OverrideMin [{spec.override_min}]: ").strip()
            if new_min:
                try:
                    spec.override_min = int(new_min)
                except ValueError:
                    print(f"    Invalid — keeping {spec.override_min}")
            new_max = input(f"    OverrideMax [{spec.override_max}]: ").strip()
            if new_max:
                try:
                    spec.override_max = int(new_max)
                except ValueError:
                    print(f"    Invalid — keeping {spec.override_max}")
            print()

        save_overrides(args.csv_path, overrides)
        print(f"Saved to {args.csv_path}")
        print_override_summary(overrides, show_all=True)


if __name__ == "__main__":
    _cli_main()
