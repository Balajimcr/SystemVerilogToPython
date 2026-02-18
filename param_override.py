#!/usr/bin/env python3
"""
Parameter Range Override Utility
=================================

Reads an override CSV file and applies OverrideMin / OverrideMax range
adjustments to a PyVSC random object **during** randomization.

The CSV can contain **any** field from the PyVSC model — not just
TopParameters.  Use ``--generate-from <pyvsc_file>`` to produce a
CSV with every rand field pre-populated from the model's constraints.

Two override modes:

1. **Solver-level** (``randomize_with_overrides``):
   Injects ``with`` constraints so the solver sees tighter bounds.
   This is the recommended approach.

2. **Post-clamp fallback** (``patch_vector_with_overrides``):
   After randomization, clamp observed values into override ranges.
   Simpler but the solver does not see the tighter bounds.

Standalone CLI
--------------
::

    python param_override.py <overrides.csv>                      # print summary
    python param_override.py <overrides.csv> --edit               # interactive edit
    python param_override.py --generate-from model.py -o out.csv  # generate full CSV

Public API
----------
- ``load_overrides(csv_path) -> Dict[str, OverrideSpec]``
- ``save_overrides(csv_path, overrides)``
- ``randomize_with_overrides(obj, overrides) -> bool``
- ``patch_vector_with_overrides(vector, overrides) -> Dict``
- ``apply_overrides_to_sv_file(sv_path, overrides) -> Tuple[int, int]``
- ``print_override_summary(overrides)``
- ``generate_override_csv_from_pyvsc(pyvsc_path, csv_path, existing)``
"""

from __future__ import annotations

import csv
import os
import re
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OverrideSpec:
    """Single parameter override entry."""
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
    """Load an override CSV and return a dict keyed by parameter name.

    The CSV is expected to have columns:
        Name, NormalValue, MinValue, MaxValue, OverrideMin, OverrideMax, TestConstraint
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Override CSV not found: {csv_path}")

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
    """Return a list of descriptions for applicable overrides (logging only).

    This is informational — the actual constraint injection happens in
    ``randomize_with_overrides()``.
    """
    applied: List[str] = []
    for name, spec in overrides.items():
        if hasattr(obj, name) and spec.is_overridden:
            applied.append(
                f"{name}: [{spec.override_min}, {spec.override_max}] "
                f"(was [{spec.orig_min}, {spec.orig_max}])"
            )
    return applied


def randomize_with_overrides(
    obj: Any,
    overrides: Dict[str, OverrideSpec],
    verbose: bool = False,
) -> bool:
    """Randomize *obj* with override constraints injected.

    Uses PyVSC's ``obj.randomize_with()`` context manager to add
    dynamic range constraints for each overridden parameter field.

    Only fields where ``spec.is_overridden`` is True are constrained.

    Returns True on success, False on solve failure.
    """
    try:
        import vsc  # noqa: F811
    except ImportError:
        # If PyVSC is not available, fall back to plain randomize
        obj.randomize()
        return True

    # Build list of (field_attr, min_val, max_val) for overridden fields
    active: List[Tuple[str, int, int]] = []
    for name, spec in overrides.items():
        if hasattr(obj, name) and spec.is_overridden:
            active.append((name, spec.override_min, spec.override_max))

    if not active:
        # No applicable overrides — plain randomize
        obj.randomize()
        return True

    if verbose:
        print(f"  Injecting {len(active)} override constraint(s):")
        for attr_name, lo, hi in active:
            print(f"    {attr_name} in [{lo}, {hi}]")

    # Use randomize_with to inject range constraints dynamically
    try:
        with obj.randomize_with() as it:
            for attr_name, lo, hi in active:
                field = getattr(it, attr_name)
                field >= lo
                field <= hi

        return True
    except Exception as e:
        print(f"Warning: randomize_with() failed: {e}")
        if verbose:
            traceback.print_exc()
        print("  Falling back to plain randomize + post-clamp")
        # Fallback: plain randomize (no override constraints) + clamp
        try:
            obj.randomize()
            _post_clamp(obj, active)
            return True
        except Exception as e2:
            print(f"Error: Fallback randomize also failed: {e2}")
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
            if clamped != current:
                if hasattr(val, 'val'):
                    val.val = clamped
                else:
                    setattr(obj, attr_name, clamped)
        except (AttributeError, TypeError, ValueError) as e:
            print(f"  Warning: post-clamp failed for {attr_name}: {e}")


def patch_vector_with_overrides(
    vector: Dict[str, Any],
    overrides: Dict[str, OverrideSpec],
) -> Dict[str, Any]:
    """Clamp vector values to override ranges (post-randomization fallback).

    For each field in *overrides* that also exists in *vector* and has
    ``is_overridden == True``, clamp its value to
    ``[override_min, override_max]``.
    """
    patched = dict(vector)
    for name, spec in overrides.items():
        if name in patched and spec.is_overridden:
            try:
                val = int(patched[name])
                patched[name] = max(spec.override_min, min(spec.override_max, val))
            except (ValueError, TypeError):
                pass
    return patched


def apply_overrides_to_sv_file(
    sv_path: str,
    overrides: Dict[str, OverrideSpec],
    backup: bool = True,
) -> Tuple[int, int]:
    """Overwrite SV range constraints using CSV override ranges.

    Rewrites lines matching this shape:
        (<name> >= <lo> && <name> <= <hi>);
    when ``<name>`` exists in *overrides*.

    Args:
        sv_path: Path to the SystemVerilog source file.
        overrides: Override map from :func:`load_overrides`.
        backup: If True, create ``<sv_path>.bak`` before writing.

    Returns:
        Tuple ``(matched_constraints, updated_constraints)``.
    """
    if not os.path.exists(sv_path):
        raise FileNotFoundError(f"SystemVerilog source not found: {sv_path}")

    line_re = re.compile(
        r"^(?P<indent>\s*)\(\s*(?P<name>\w+)\s*>=\s*(?P<lo>-?\d+)\s*&&\s*"
        r"(?P=name)\s*<=\s*(?P<hi>-?\d+)\s*\)\s*;\s*(?P<trail>.*)$"
    )

    with open(sv_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    matched = 0
    updated = 0
    out_lines: List[str] = []

    for line in lines:
        nl = "\n" if line.endswith("\n") else ""
        body = line[:-1] if nl else line
        m = line_re.match(body)

        if not m:
            out_lines.append(line)
            continue

        matched += 1
        name = m.group("name")
        spec = overrides.get(name)
        if spec is None:
            out_lines.append(line)
            continue

        trail = m.group("trail").strip()
        base = (
            f"{m.group('indent')}({name} >= {spec.override_min} && "
            f"{name} <= {spec.override_max});"
        )
        if trail:
            base = f"{base} {trail}"
        new_line = f"{base}{nl}"
        out_lines.append(new_line)

        old_lo = int(m.group("lo"))
        old_hi = int(m.group("hi"))
        if old_lo != spec.override_min or old_hi != spec.override_max:
            updated += 1

    if updated > 0:
        if backup:
            bak_path = f"{sv_path}.bak"
            with open(bak_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        with open(sv_path, "w", encoding="utf-8") as f:
            f.writelines(out_lines)

    return matched, updated


# ---------------------------------------------------------------------------
# Generate full-field override CSV from PyVSC source
# ---------------------------------------------------------------------------

def generate_override_csv_from_pyvsc(
    pyvsc_path: str,
    csv_path: str,
    existing_overrides: Optional[Dict[str, OverrideSpec]] = None,
) -> Dict[str, OverrideSpec]:
    """Generate an override CSV containing ALL rand fields from a PyVSC file.

    Scans the PyVSC source for ``self.field = vsc.rand_*()`` declarations
    and ``self.field in vsc.rangelist(vsc.rng(min, max))`` constraints.
    Writes them to *csv_path* in the standard override CSV format.

    If *existing_overrides* is provided, user-edited OverrideMin/Max
    values are preserved for fields that already exist.

    Returns the generated overrides dict.
    """
    if not os.path.exists(pyvsc_path):
        raise FileNotFoundError(f"PyVSC source not found: {pyvsc_path}")

    with open(pyvsc_path, "r", encoding="utf-8") as f:
        content = f.read()

    # --- Extract field declarations ---
    type_patterns = [
        (r'vsc\.rand_bit_t\((\d+)\)', False, lambda m: int(m.group(1))),
        (r'vsc\.randc_bit_t\((\d+)\)', False, lambda m: int(m.group(1))),
        (r'vsc\.rand_uint8_t\(\)', False, lambda _: 8),
        (r'vsc\.rand_uint16_t\(\)', False, lambda _: 16),
        (r'vsc\.rand_uint32_t\(\)', False, lambda _: 32),
        (r'vsc\.rand_uint64_t\(\)', False, lambda _: 64),
        (r'vsc\.rand_int8_t\(\)', True, lambda _: 8),
        (r'vsc\.rand_int16_t\(\)', True, lambda _: 16),
        (r'vsc\.rand_int32_t\(\)', True, lambda _: 32),
        (r'vsc\.rand_int64_t\(\)', True, lambda _: 64),
        (r'vsc\.rand_enum_t\(\w+\)', False, lambda _: 32),
    ]

    fields: Dict[str, dict] = {}
    field_decl_pattern = r'self\.(\w+)\s*=\s*(vsc\.\w+(?:_t)?\([^)]*\))'
    for match in re.finditer(field_decl_pattern, content):
        field_name = match.group(1)
        type_expr = match.group(2)

        bit_width = 32
        is_signed = False
        for pattern, signed, width_fn in type_patterns:
            type_match = re.search(pattern, type_expr)
            if type_match:
                bit_width = width_fn(type_match)
                is_signed = signed
                break

        if is_signed:
            type_max = (1 << (bit_width - 1)) - 1
            type_min = -(1 << (bit_width - 1))
        else:
            type_max = (1 << bit_width) - 1
            type_min = 0

        fields[field_name] = {
            'bit_width': bit_width,
            'is_signed': is_signed,
            'type_min': type_min,
            'type_max': type_max,
            'spec_min': None,
            'spec_max': None,
        }

    # --- Extract constraint ranges ---
    range_pattern = r'self\.(\w+)\s+in\s+vsc\.rangelist\(vsc\.rng\((-?\d+),\s*(-?\d+)\)\)'
    for match in re.finditer(range_pattern, content):
        field_name = match.group(1)
        spec_min = int(match.group(2))
        spec_max = int(match.group(3))
        if field_name in fields:
            fields[field_name]['spec_min'] = spec_min
            fields[field_name]['spec_max'] = spec_max

    # --- Build overrides ---
    overrides: Dict[str, OverrideSpec] = {}
    for name, info in fields.items():
        min_val = info['spec_min'] if info['spec_min'] is not None else info['type_min']
        max_val = info['spec_max'] if info['spec_max'] is not None else info['type_max']

        # Preserve user edits from existing overrides
        ovr_min = min_val
        ovr_max = max_val
        normal_value = 0
        test_constraints: List[str] = []
        if existing_overrides and name in existing_overrides:
            ex = existing_overrides[name]
            ovr_min = ex.override_min
            ovr_max = ex.override_max
            normal_value = ex.normal_value
            test_constraints = ex.test_constraints

        overrides[name] = OverrideSpec(
            name=name,
            normal_value=normal_value,
            orig_min=min_val,
            orig_max=max_val,
            override_min=ovr_min,
            override_max=ovr_max,
            test_constraints=test_constraints,
        )

    # Also merge in any existing entries that aren't in the PyVSC file
    # (e.g., TopParameters that aren't declared as rand fields)
    if existing_overrides:
        for name, ex in existing_overrides.items():
            if name not in overrides:
                overrides[name] = ex

    save_overrides(csv_path, overrides)
    print(f"Generated override CSV with {len(overrides)} fields: {csv_path}")
    return overrides


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_override_summary(
    overrides: Dict[str, OverrideSpec],
    show_all: bool = False,
) -> None:
    """Print a formatted table of overrides to stdout."""
    print(f"\n{'='*90}")
    print("PARAMETER RANGE OVERRIDES")
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
    """Standalone CLI: view / edit / generate an override CSV."""
    import argparse

    parser = argparse.ArgumentParser(
        description="View, edit, or generate a parameter override CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s overrides.csv                          # print summary
  %(prog)s overrides.csv --all                    # show all parameters
  %(prog)s overrides.csv --edit                   # interactive edit
  %(prog)s --generate-from model.py -o out.csv    # generate from PyVSC file
  %(prog)s --generate-from model.py -o out.csv --merge existing.csv
        """
    )
    parser.add_argument("csv_path", nargs="?", default=None,
                        help="Path to override CSV (for view/edit)")
    parser.add_argument("--edit", action="store_true",
                        help="Interactive edit mode (set OverrideMin/Max)")
    parser.add_argument("--all", action="store_true",
                        help="Show all parameters (not just overridden)")
    parser.add_argument("--generate-from", metavar="PYVSC_FILE", default=None,
                        help="Generate override CSV from a PyVSC source file")
    parser.add_argument("-o", "--output", metavar="CSV", default=None,
                        help="Output CSV path (for --generate-from)")
    parser.add_argument("--merge", metavar="EXISTING_CSV", default=None,
                        help="Merge with existing CSV (preserves user edits)")
    args = parser.parse_args()

    if args.generate_from:
        # Generate mode
        if not args.output:
            stem = os.path.splitext(os.path.basename(args.generate_from))[0]
            args.output = f"{stem}_overrides.csv"

        existing = None
        if args.merge:
            existing = load_overrides(args.merge)
            print(f"Merging with {len(existing)} existing overrides from {args.merge}")

        overrides = generate_override_csv_from_pyvsc(
            args.generate_from, args.output, existing_overrides=existing
        )
        print_override_summary(overrides, show_all=True)
        return

    if not args.csv_path:
        parser.print_help()
        sys.exit(1)

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
