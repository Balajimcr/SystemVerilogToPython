#!/usr/bin/env python3
"""
Test Vector Generator using PyVSC Constraint Randomization

This script generates randomized test vectors by:
1. Loading a PyVSC-generated constraint model
2. Reading field names from a hw_field.txt file
3. Randomizing the model N times
4. Writing each configuration to separate output files
5. Computing statistics (min, max, bit range) for each field

Usage:
    python generate_test_vectors.py <pyvsc_module> <class_name> <hw_field_file> <num_runs> [output_dir]

Example:
    python generate_test_vectors.py example_sv_classes IspYuv2rgbCfg hw_field.txt 10 ./test_vectors

Arguments:
    pyvsc_module  : Python module name containing the PyVSC class (without .py)
    class_name    : Name of the @vsc.randobj class to instantiate
    hw_field_file : Text file with field names and initial values (one per line)
    num_runs      : Number of randomized configurations to generate
    output_dir    : Output directory for test vector files (default: ./test_vectors)
"""

import sys
import os
import re
import argparse
import importlib
import random
import math
import time
import multiprocessing
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

# TopParameter override support (optional import — module lives alongside)
try:
    from top_param_override import (
        load_overrides,
        randomize_with_overrides,
        patch_vector_with_overrides,
        print_override_summary,
        OverrideSpec,
    )
    _HAS_TOP_PARAM = True
except ImportError:
    _HAS_TOP_PARAM = False


@dataclass
class FieldSpec:
    """Specification for a field extracted from PyVSC source."""
    name: str
    bit_width: int = 32           # Register bit width from type declaration
    is_signed: bool = False       # Whether the type is signed
    spec_min: Optional[int] = None  # Min value from constraint (vsc.rng or rangelist)
    spec_max: Optional[int] = None  # Max value from constraint (vsc.rng or rangelist)
    type_name: str = ""           # Original PyVSC type name


@dataclass
class FieldStats:
    """Statistics for a single field across all test vectors."""
    name: str
    values: List[Any] = field(default_factory=list)
    min_val: Optional[int] = None       # Observed min from randomization
    max_val: Optional[int] = None       # Observed max from randomization
    bit_width: int = 0                  # Calculated bit width from observed values
    is_signed: bool = False             # Whether negative values were observed
    unique_count: int = 0
    spec: Optional[FieldSpec] = None    # Specification from PyVSC file

    def compute_stats(self):
        """Compute statistics from collected values."""
        if not self.values:
            return

        # Filter numeric values
        numeric_values = []
        for v in self.values:
            try:
                numeric_values.append(int(v))
            except (ValueError, TypeError):
                pass

        if not numeric_values:
            return

        self.min_val = min(numeric_values)
        self.max_val = max(numeric_values)
        self.unique_count = len(set(numeric_values))

        # Determine if signed (has negative values)
        self.is_signed = self.min_val < 0

        # Calculate bit width needed
        if self.is_signed:
            # Signed: need to accommodate both positive and negative
            abs_max = max(abs(self.min_val), abs(self.max_val))
            if abs_max == 0:
                self.bit_width = 1
            else:
                self.bit_width = int(math.ceil(math.log2(abs_max + 1))) + 1  # +1 for sign bit
        else:
            # Unsigned
            if self.max_val == 0:
                self.bit_width = 1
            else:
                self.bit_width = int(math.ceil(math.log2(self.max_val + 1)))

        # Ensure minimum bit width of 1
        self.bit_width = max(1, self.bit_width)


def parse_pyvsc_file(module_name: str) -> Dict[str, FieldSpec]:
    """Parse PyVSC source file to extract field specifications (bit widths, ranges)."""
    field_specs: Dict[str, FieldSpec] = {}

    # Try to find the source file
    pyvsc_file = f"{module_name}.py"
    if not os.path.exists(pyvsc_file):
        print(f"Warning: Could not find PyVSC source file: {pyvsc_file}")
        return field_specs

    with open(pyvsc_file, 'r') as f:
        content = f.read()

    # Parse field declarations in __init__
    # Pattern: self.field_name = vsc.rand_bit_t(N) or vsc.rand_int32_t() etc.
    # Use a list of tuples for ordered matching (more specific patterns first)
    type_patterns = [
        # Parameterized types (must come before fixed-width types)
        (r'vsc\.rand_bit_t\((\d+)\)', 'bit', lambda m: int(m.group(1)), False),
        (r'vsc\.randc_bit_t\((\d+)\)', 'randc_bit', lambda m: int(m.group(1)), False),
        # Fixed-width unsigned types
        (r'vsc\.rand_uint8_t\(\)', 'uint8', lambda m: 8, False),
        (r'vsc\.rand_uint16_t\(\)', 'uint16', lambda m: 16, False),
        (r'vsc\.rand_uint32_t\(\)', 'uint32', lambda m: 32, False),
        (r'vsc\.rand_uint64_t\(\)', 'uint64', lambda m: 64, False),
        # Fixed-width signed types
        (r'vsc\.rand_int8_t\(\)', 'int8', lambda m: 8, True),
        (r'vsc\.rand_int16_t\(\)', 'int16', lambda m: 16, True),
        (r'vsc\.rand_int32_t\(\)', 'int32', lambda m: 32, True),
        (r'vsc\.rand_int64_t\(\)', 'int64', lambda m: 64, True),
        # Enum type
        (r'vsc\.rand_enum_t\((\w+)\)', 'enum', lambda m: 32, False),
    ]

    # Find all field declarations
    field_decl_pattern = r'self\.(\w+)\s*=\s*(vsc\.\w+(?:_t)?\([^)]*\))'
    for match in re.finditer(field_decl_pattern, content):
        field_name = match.group(1)
        type_expr = match.group(2)

        matched = False
        for pattern, type_name, width_fn, is_signed in type_patterns:
            type_match = re.search(pattern, type_expr)
            if type_match:
                bit_width = width_fn(type_match)
                field_specs[field_name] = FieldSpec(
                    name=field_name,
                    bit_width=bit_width,
                    is_signed=is_signed,
                    type_name=type_name
                )
                matched = True
                break

        if not matched:
            # Default to 32-bit signed if unknown type
            field_specs[field_name] = FieldSpec(
                name=field_name,
                bit_width=32,
                is_signed=True,
                type_name='unknown'
            )

    # Parse constraint ranges: self.field in vsc.rangelist(vsc.rng(min, max))
    range_pattern = r'self\.(\w+)\s+in\s+vsc\.rangelist\(vsc\.rng\((-?\d+),\s*(-?\d+)\)\)'
    for match in re.finditer(range_pattern, content):
        field_name = match.group(1)
        spec_min = int(match.group(2))
        spec_max = int(match.group(3))

        if field_name in field_specs:
            field_specs[field_name].spec_min = spec_min
            field_specs[field_name].spec_max = spec_max
        else:
            # Create spec even if field declaration wasn't found
            field_specs[field_name] = FieldSpec(
                name=field_name,
                spec_min=spec_min,
                spec_max=spec_max
            )

    # Parse discrete value constraints: self.field in vsc.rangelist(val1, val2, ...)
    # Handle multi-line patterns with nested parentheses
    discrete_pattern = r'self\.(\w+)\s+in\s+vsc\.rangelist\(([^)]+(?:\([^)]*\)[^)]*)*)\)'
    for match in re.finditer(discrete_pattern, content):
        field_name = match.group(1)
        values_str = match.group(2)

        # Skip if it contains vsc.rng (already handled above)
        if 'vsc.rng' in values_str:
            continue

        # Extract numeric values and enum references
        values = []
        for val in values_str.split(','):
            val = val.strip()
            # Try to parse as integer
            try:
                values.append(int(val))
            except ValueError:
                # Could be an enum reference like YuvFormat.YUV_444
                # Try to extract the value from enum definition
                enum_match = re.search(r'(\w+)\.(\w+)', val)
                if enum_match:
                    enum_class = enum_match.group(1)
                    enum_member = enum_match.group(2)
                    # Look for enum definition with = value
                    enum_def_pattern = rf'{enum_member}\s*=\s*(-?\d+)'
                    enum_val_match = re.search(enum_def_pattern, content)
                    if enum_val_match:
                        values.append(int(enum_val_match.group(1)))

        if values:
            if field_name in field_specs:
                # Only set if not already set (vsc.rng takes priority)
                if field_specs[field_name].spec_min is None:
                    field_specs[field_name].spec_min = min(values)
                    field_specs[field_name].spec_max = max(values)
            else:
                # Create spec if field wasn't found in declarations
                field_specs[field_name] = FieldSpec(
                    name=field_name,
                    spec_min=min(values),
                    spec_max=max(values)
                )

    print(f"  Parsed {len(field_specs)} field specifications from {pyvsc_file}")

    # Debug: show some parsed specs
    if field_specs:
        print(f"  Sample specs:")
        for i, (name, spec) in enumerate(list(field_specs.items())[:5]):
            print(f"    {name}: bits={spec.bit_width}, signed={spec.is_signed}, range=[{spec.spec_min}, {spec.spec_max}]")
        if len(field_specs) > 5:
            print(f"    ... and {len(field_specs) - 5} more")

    return field_specs


def parse_hw_field_file(filepath: str) -> List[Tuple[str, str]]:
    """Parse hw_field.txt to get list of (field_name, default_value) tuples."""
    fields = []
    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            # Remove comments (everything after #)
            if '#' in line:
                line = line[:line.index('#')]
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                field_name = parts[0]
                default_value = parts[1]
                fields.append((field_name, default_value))
            elif len(parts) == 1:
                # Field name only, default to 0
                fields.append((parts[0], '0'))
            else:
                print(f"Warning: Skipping invalid line {line_num}: {line}")
    return fields


def load_pyvsc_class(module_name: str, class_name: str):
    """Dynamically load the PyVSC class from the specified module."""
    try:
        # Add current directory to path if needed
        if '.' not in sys.path:
            sys.path.insert(0, '.')

        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        return cls
    except ImportError as e:
        print(f"Error: Could not import module '{module_name}': {e}")
        sys.exit(1)
    except AttributeError as e:
        print(f"Error: Class '{class_name}' not found in module '{module_name}': {e}")
        sys.exit(1)


def get_field_value(obj, field_name: str) -> Optional[Any]:
    """Get the value of a field from the randomized object."""
    try:
        value = getattr(obj, field_name)
        # Handle PyVSC field types - they may have a .val property or be directly accessible
        if hasattr(value, 'val'):
            return value.val
        return value
    except AttributeError:
        return None


def generate_test_vector(obj, fields: List[Tuple[str, str]], run_id: int,
                         field_stats: Dict[str, FieldStats],
                         top_overrides: Optional[Dict] = None) -> Dict[str, Any]:
    """Generate a single test vector by randomizing the object.

    If *top_overrides* is provided (and the top_param_override module is
    available), overrides are applied during randomization and as a
    post-clamp fallback.
    """
    try:
        if top_overrides and _HAS_TOP_PARAM:
            ok = randomize_with_overrides(obj, top_overrides)
            if not ok:
                raise RuntimeError("randomize_with_overrides failed")
        else:
            obj.randomize()
    except Exception as e:
        print(f"Warning: Randomization failed for run {run_id}: {e}")
        print("  Using default/previous values")

    vector = {}
    for field_name, default_value in fields:
        value = get_field_value(obj, field_name)
        if value is not None:
            vector[field_name] = value
        else:
            # Field not found in object, use default
            vector[field_name] = default_value

        # Collect value for statistics
        if field_name in field_stats:
            field_stats[field_name].values.append(vector[field_name])

    # Apply post-clamp for any overrides (belt-and-suspenders)
    if top_overrides and _HAS_TOP_PARAM:
        vector = patch_vector_with_overrides(vector, top_overrides)

    return vector


def _randomize_worker(args_tuple):
    """Worker function for parallel randomization.

    Creates a fresh PyVSC instance per call to avoid any shared state.
    Each worker independently imports the module and instantiates the class.
    """
    module_name, class_name, fields, run_id, seed = args_tuple

    # Per-run deterministic seed
    if seed is not None:
        random.seed(seed + run_id)

    t0 = time.perf_counter()

    # Import and instantiate in worker process
    if '.' not in sys.path:
        sys.path.insert(0, '.')
    module = importlib.import_module(module_name)
    pyvsc_class = getattr(module, class_name)
    obj = pyvsc_class()

    # Randomize
    failed = False
    try:
        obj.randomize()
    except Exception as e:
        failed = True
        print(f"Warning: Randomization failed for run {run_id}: {e}")

    # Extract field values
    vector = {}
    for field_name, default_value in fields:
        value = get_field_value(obj, field_name)
        if value is not None:
            vector[field_name] = value
        else:
            vector[field_name] = default_value

    elapsed = time.perf_counter() - t0
    return run_id, vector, elapsed, failed


def write_test_vector_file(vector: Dict[str, Any], output_path: str, run_id: int):
    """Write a single test vector to a file."""
    with open(output_path, 'w') as f:
        f.write(f"# Test Vector Configuration - Run {run_id}\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("#\n")
        for field_name, value in vector.items():
            f.write(f"{field_name} {value}\n")


def write_summary_file(vectors: List[Dict[str, Any]], output_dir: str,
                       fields: List[Tuple[str, str]], field_stats: Dict[str, FieldStats]):
    """Write a summary CSV file with all test vectors and statistics."""
    summary_path = os.path.join(output_dir, "test_vectors_summary.csv")

    with open(summary_path, 'w') as f:
        # Header row
        field_names = [field[0] for field in fields]
        f.write("run_id," + ",".join(field_names) + "\n")

        # Data rows
        for run_id, vector in enumerate(vectors):
            values = [str(vector.get(name, "")) for name in field_names]
            f.write(f"{run_id}," + ",".join(values) + "\n")

    print(f"Summary written to: {summary_path}")

    # Write detailed statistics file
    stats_path = os.path.join(output_dir, "field_statistics.csv")
    with open(stats_path, 'w') as f:
        f.write("Field_Name,Reg_Bit_Width,Spec_Min,Spec_Max,Spec_Signed,Obs_Min,Obs_Max,Obs_Bit_Width,Obs_Signed,Unique_Values,Total_Samples\n")
        for field_name, _ in fields:
            stats = field_stats.get(field_name)
            if stats:
                stats.compute_stats()
                # Spec values
                reg_bit = stats.spec.bit_width if stats.spec else "N/A"
                spec_min = stats.spec.spec_min if stats.spec and stats.spec.spec_min is not None else "N/A"
                spec_max = stats.spec.spec_max if stats.spec and stats.spec.spec_max is not None else "N/A"
                spec_signed = "Yes" if stats.spec and stats.spec.is_signed else "No"
                # Observed values
                obs_min = stats.min_val if stats.min_val is not None else "N/A"
                obs_max = stats.max_val if stats.max_val is not None else "N/A"
                obs_signed = "Yes" if stats.is_signed else "No"
                f.write(f"{field_name},{reg_bit},{spec_min},{spec_max},{spec_signed},{obs_min},{obs_max},{stats.bit_width},{obs_signed},{stats.unique_count},{len(stats.values)}\n")

    print(f"Statistics written to: {stats_path}")

    # Write detailed report
    report_path = os.path.join(output_dir, "field_statistics_report.txt")
    with open(report_path, 'w') as f:
        f.write("=" * 140 + "\n")
        f.write("FIELD STATISTICS REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Test Vectors: {len(vectors)}\n")
        f.write("=" * 140 + "\n\n")

        # Header with both spec and observed columns
        f.write(f"{'Field Name':<35} {'RegBits':>8} {'SpecMin':>12} {'SpecMax':>12} {'ObsMin':>12} {'ObsMax':>12} {'ObsBits':>8} {'Unique':>8}\n")
        f.write("-" * 140 + "\n")

        for field_name, _ in fields:
            stats = field_stats.get(field_name)
            if stats:
                # Spec values
                reg_bit = str(stats.spec.bit_width) if stats.spec else "N/A"
                spec_min = str(stats.spec.spec_min) if stats.spec and stats.spec.spec_min is not None else "N/A"
                spec_max = str(stats.spec.spec_max) if stats.spec and stats.spec.spec_max is not None else "N/A"
                # Observed values
                obs_min = str(stats.min_val) if stats.min_val is not None else "N/A"
                obs_max = str(stats.max_val) if stats.max_val is not None else "N/A"
                f.write(f"{field_name:<35} {reg_bit:>8} {spec_min:>12} {spec_max:>12} {obs_min:>12} {obs_max:>12} {stats.bit_width:>8} {stats.unique_count:>8}\n")

        f.write("\n" + "=" * 140 + "\n")
        f.write("LEGEND:\n")
        f.write("  RegBits   : Register bit width from PyVSC type declaration (e.g., rand_int32_t = 32 bits)\n")
        f.write("  SpecMin   : Minimum value from PyVSC constraint (vsc.rangelist or vsc.rng)\n")
        f.write("  SpecMax   : Maximum value from PyVSC constraint (vsc.rangelist or vsc.rng)\n")
        f.write("  ObsMin    : Minimum value observed across all test vectors\n")
        f.write("  ObsMax    : Maximum value observed across all test vectors\n")
        f.write("  ObsBits   : Minimum bit width required to represent the observed range\n")
        f.write("  Unique    : Number of unique values observed\n")
        f.write("=" * 140 + "\n")

    print(f"Report written to: {report_path}")


def write_extended_summary_file(vectors: List[Dict[str, Any]], output_dir: str,
                                 fields: List[Tuple[str, str]], field_stats: Dict[str, FieldStats]):
    """Write an extended summary CSV with statistics in header."""
    extended_path = os.path.join(output_dir, "test_vectors_extended.csv")

    with open(extended_path, 'w') as f:
        field_names = [field[0] for field in fields]

        # Write metadata rows
        f.write("# FIELD SPECIFICATIONS (from PyVSC file)\n")

        # Field names row
        f.write("field_name," + ",".join(field_names) + "\n")

        # Register bit width row (from PyVSC type declaration)
        reg_bit_widths = []
        for name in field_names:
            stats = field_stats.get(name)
            if stats and stats.spec and stats.spec.bit_width:
                reg_bit_widths.append(str(stats.spec.bit_width))
            else:
                reg_bit_widths.append("N/A")
        f.write("reg_bit_width," + ",".join(reg_bit_widths) + "\n")

        # Spec min row (from constraint rangelist)
        spec_min_vals = []
        for name in field_names:
            stats = field_stats.get(name)
            if stats and stats.spec and stats.spec.spec_min is not None:
                spec_min_vals.append(str(stats.spec.spec_min))
            else:
                spec_min_vals.append("N/A")
        f.write("spec_min," + ",".join(spec_min_vals) + "\n")

        # Spec max row (from constraint rangelist)
        spec_max_vals = []
        for name in field_names:
            stats = field_stats.get(name)
            if stats and stats.spec and stats.spec.spec_max is not None:
                spec_max_vals.append(str(stats.spec.spec_max))
            else:
                spec_max_vals.append("N/A")
        f.write("spec_max," + ",".join(spec_max_vals) + "\n")

        # Spec signedness row
        spec_signed_vals = []
        for name in field_names:
            stats = field_stats.get(name)
            if stats and stats.spec:
                spec_signed_vals.append("signed" if stats.spec.is_signed else "unsigned")
            else:
                spec_signed_vals.append("N/A")
        f.write("spec_signedness," + ",".join(spec_signed_vals) + "\n")

        # Separator
        f.write("#\n")
        f.write("# OBSERVED STATISTICS (from randomization)\n")

        # Observed min values row
        min_vals = []
        for name in field_names:
            stats = field_stats.get(name)
            if stats and stats.min_val is not None:
                min_vals.append(str(stats.min_val))
            else:
                min_vals.append("N/A")
        f.write("obs_min," + ",".join(min_vals) + "\n")

        # Observed max values row
        max_vals = []
        for name in field_names:
            stats = field_stats.get(name)
            if stats and stats.max_val is not None:
                max_vals.append(str(stats.max_val))
            else:
                max_vals.append("N/A")
        f.write("obs_max," + ",".join(max_vals) + "\n")

        # Observed bit width row (calculated from observed values)
        bit_widths = []
        for name in field_names:
            stats = field_stats.get(name)
            if stats:
                bit_widths.append(str(stats.bit_width))
            else:
                bit_widths.append("N/A")
        f.write("obs_bit_width," + ",".join(bit_widths) + "\n")

        # Observed signedness row
        signed_vals = []
        for name in field_names:
            stats = field_stats.get(name)
            if stats:
                signed_vals.append("signed" if stats.is_signed else "unsigned")
            else:
                signed_vals.append("N/A")
        f.write("obs_signedness," + ",".join(signed_vals) + "\n")

        # Unique count row
        unique_counts = []
        for name in field_names:
            stats = field_stats.get(name)
            if stats:
                unique_counts.append(str(stats.unique_count))
            else:
                unique_counts.append("N/A")
        f.write("obs_unique," + ",".join(unique_counts) + "\n")

        # Separator
        f.write("#\n")
        f.write("# TEST VECTORS\n")

        # Header row for data
        f.write("run_id," + ",".join(field_names) + "\n")

        # Data rows
        for run_id, vector in enumerate(vectors):
            values = [str(vector.get(name, "")) for name in field_names]
            f.write(f"{run_id}," + ",".join(values) + "\n")

    print(f"Extended summary written to: {extended_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate randomized test vectors using PyVSC constraint model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s example_sv_classes IspYuv2rgbCfg hw_field.txt 10
  %(prog)s example_sv_classes IspYuv2rgbCfg hw_field.txt 100 ./output
  %(prog)s my_constraints MyClass fields.txt 50 --seed 12345
  %(prog)s example_sv_classes IspYuv2rgbCfg hw_field.txt 100 -j -1  # all cores
        """
    )

    parser.add_argument('pyvsc_module',
                        help='Python module name containing the PyVSC class (without .py)')
    parser.add_argument('class_name',
                        help='Name of the @vsc.randobj class to instantiate')
    parser.add_argument('hw_field_file',
                        help='Text file with field names and initial values')
    parser.add_argument('num_runs', type=int,
                        help='Number of randomized configurations to generate')
    parser.add_argument('output_dir', nargs='?', default='./test_vectors',
                        help='Output directory for test vector files (default: ./test_vectors)')
    parser.add_argument('--seed', type=int, default=None,
                        help='Random seed for reproducibility')
    parser.add_argument('--prefix', default='config',
                        help='Prefix for output files (default: config)')
    parser.add_argument('--format', choices=['txt', 'csv', 'both'], default='both',
                        help='Output format (default: both)')
    parser.add_argument('--jobs', '-j', type=int, default=-1,
                        help='Number of parallel workers (default: 1, use -1 for all cores)')
    parser.add_argument('--top-params', default=None, metavar='CSV',
                        help='TopParameter CSV file for range overrides '
                             '(exported by XML_to_sv_Converter)')

    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.hw_field_file):
        print(f"Error: Field file not found: {args.hw_field_file}")
        sys.exit(1)

    if args.num_runs < 1:
        print("Error: Number of runs must be at least 1")
        sys.exit(1)

    # Set random seed if provided
    if args.seed is not None:
        random.seed(args.seed)
        try:
            import vsc
            # vsc.set_randstate() does not exist in PyVSC.
            # Use Python random seed; PyVSC uses its own internal RNG.
            # Per-run seed offset provides deterministic per-run variation.
        except ImportError:
            print("Warning: PyVSC not imported for seed setup")

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Test Vector Generator")
    print(f"=" * 50)
    print(f"PyVSC Module : {args.pyvsc_module}")
    print(f"Class Name   : {args.class_name}")
    print(f"Field File   : {args.hw_field_file}")
    print(f"Num Runs     : {args.num_runs}")
    print(f"Output Dir   : {args.output_dir}")
    if args.seed:
        print(f"Random Seed  : {args.seed}")
    print(f"Jobs         : {args.jobs}")
    if args.top_params:
        print(f"Top Params   : {args.top_params}")
    print(f"=" * 50)

    # Parse field file
    fields = parse_hw_field_file(args.hw_field_file)
    print(f"\nLoaded {len(fields)} fields from {args.hw_field_file}")

    # Parse PyVSC source file for field specifications
    print(f"\nParsing PyVSC source file for field specifications...")
    field_specs = parse_pyvsc_file(args.pyvsc_module)

    # Initialize field statistics with specs
    field_stats: Dict[str, FieldStats] = {}
    for field_name, _ in fields:
        stats = FieldStats(name=field_name)
        # Attach spec if available
        if field_name in field_specs:
            stats.spec = field_specs[field_name]
        field_stats[field_name] = stats

    # Load PyVSC class
    print(f"Loading PyVSC class '{args.class_name}' from '{args.pyvsc_module}'...")
    pyvsc_class = load_pyvsc_class(args.pyvsc_module, args.class_name)

    # Create instance
    try:
        obj = pyvsc_class()
        print("PyVSC object created successfully")
    except Exception as e:
        print(f"Error: Could not instantiate class: {e}")
        sys.exit(1)

    # Load TopParameter overrides (if provided)
    top_overrides: Dict[str, 'OverrideSpec'] = {}
    if args.top_params:
        if not _HAS_TOP_PARAM:
            print("Warning: top_param_override module not found — ignoring --top-params")
        elif not os.path.exists(args.top_params):
            print(f"Warning: TopParameter CSV not found: {args.top_params}")
        else:
            top_overrides = load_overrides(args.top_params)
            print(f"\nLoaded {len(top_overrides)} TopParameter override(s)")
            # Show which overrides apply to this object
            applicable = [n for n in top_overrides if hasattr(obj, n)]
            non_applicable = [n for n in top_overrides if not hasattr(obj, n)]
            if applicable:
                print(f"  Applicable to model: {', '.join(applicable)}")
            if non_applicable:
                print(f"  Not in model (ignored): {', '.join(non_applicable)}")
            active = [n for n, s in top_overrides.items()
                      if s.is_overridden and n in applicable]
            if active:
                print(f"  Active overrides: {', '.join(active)}")
                for n in active:
                    s = top_overrides[n]
                    print(f"    {n}: [{s.orig_min},{s.orig_max}] -> [{s.override_min},{s.override_max}]")
            print_override_summary(top_overrides, show_all=True)

    # Resolve job count
    num_jobs = args.jobs
    if num_jobs == -1:
        num_jobs = multiprocessing.cpu_count()
    elif num_jobs < 1:
        num_jobs = 1
    num_jobs = min(num_jobs, args.num_runs)

    # Validate model: try a single randomize before batch
    print(f"\nValidating PyVSC model (single randomize)...")
    t_val = time.perf_counter()
    try:
        if top_overrides and _HAS_TOP_PARAM:
            ok = randomize_with_overrides(obj, top_overrides)
            if not ok:
                raise RuntimeError("randomize_with_overrides returned False")
        else:
            obj.randomize()
        val_time = time.perf_counter() - t_val
        print(f"  Validation OK ({val_time:.3f}s per randomize)")
        est_serial = val_time * args.num_runs
        print(f"  Estimated serial time for {args.num_runs} runs: {est_serial:.1f}s")
        if num_jobs > 1:
            print(f"  Using {num_jobs} parallel workers (est: {est_serial/num_jobs:.1f}s)")
    except Exception as e:
        print(f"  WARNING: Validation randomize failed: {e}")
        print(f"  Proceeding anyway — some runs may fail.")

    # Generate test vectors
    print(f"\nGenerating {args.num_runs} test vectors (jobs={num_jobs})...")
    gen_start = time.perf_counter()
    vectors = [None] * args.num_runs
    successful = 0
    total_solve_time = 0.0

    if num_jobs > 1:
        # Parallel execution: each worker creates its own instance
        # NOTE: TopParameter overrides are applied as post-clamp in parallel
        # mode because workers can't share the override state easily.
        worker_args = [
            (args.pyvsc_module, args.class_name, fields, run_id, args.seed)
            for run_id in range(args.num_runs)
        ]
        with multiprocessing.Pool(processes=num_jobs) as pool:
            for run_id, vector, elapsed, failed in pool.imap_unordered(
                    _randomize_worker, worker_args):
                # Apply TopParameter post-clamp for parallel workers
                if top_overrides and _HAS_TOP_PARAM:
                    vector = patch_vector_with_overrides(vector, top_overrides)
                vectors[run_id] = vector
                total_solve_time += elapsed
                if not failed:
                    successful += 1

                # Collect stats
                for field_name, _ in fields:
                    if field_name in field_stats:
                        field_stats[field_name].values.append(
                            vector.get(field_name, ''))

                # Progress
                done = sum(1 for v in vectors if v is not None)
                if done % max(1, args.num_runs // 10) == 0 or done == args.num_runs:
                    print(f"  Generated {done}/{args.num_runs} vectors")

        # Write individual files after collection (parallel writes cause I/O contention)
        if args.format in ['txt', 'both']:
            for run_id, vector in enumerate(vectors):
                output_path = os.path.join(
                    args.output_dir, f"{args.prefix}_{run_id:04d}.txt")
                write_test_vector_file(vector, output_path, run_id)
    else:
        # Serial execution: reuse single instance (no state accumulation issue)
        for run_id in range(args.num_runs):
            t_iter = time.perf_counter()
            vector = generate_test_vector(obj, fields, run_id, field_stats,
                                          top_overrides=top_overrides)
            elapsed = time.perf_counter() - t_iter
            total_solve_time += elapsed
            vectors[run_id] = vector

            # Write individual file
            if args.format in ['txt', 'both']:
                output_path = os.path.join(
                    args.output_dir, f"{args.prefix}_{run_id:04d}.txt")
                write_test_vector_file(vector, output_path, run_id)

            successful += 1

            # Progress with timing
            if (run_id + 1) % max(1, args.num_runs // 10) == 0 \
                    or run_id == args.num_runs - 1:
                print(f"  Generated {run_id + 1}/{args.num_runs} vectors "
                      f"({elapsed:.3f}s this iter)")

    gen_elapsed = time.perf_counter() - gen_start

    # Compute final statistics
    for stats in field_stats.values():
        stats.compute_stats()

    # Write summary files
    if args.format in ['csv', 'both']:
        write_summary_file(vectors, args.output_dir, fields, field_stats)
        write_extended_summary_file(vectors, args.output_dir, fields, field_stats)

    print(f"\nGeneration complete!")
    print(f"  Successful: {successful}/{args.num_runs}")
    print(f"  Wall time : {gen_elapsed:.2f}s")
    print(f"  Solve time: {total_solve_time:.2f}s "
          f"(avg {total_solve_time/max(1,args.num_runs):.3f}s/run)")
    print(f"  Output dir: {args.output_dir}")

    # Show sample statistics
    print(f"\n{'='*100}")
    print(f"FIELD STATISTICS SUMMARY (Spec from PyVSC, Observed from randomization)")
    print(f"{'='*100}")
    print(f"{'Field Name':<30} {'RegBits':>8} {'SpecMin':>10} {'SpecMax':>10} {'ObsMin':>10} {'ObsMax':>10}")
    print(f"{'-'*100}")

    for i, (field_name, _) in enumerate(fields[:15]):
        stats = field_stats.get(field_name)
        if stats:
            reg_bit = str(stats.spec.bit_width) if stats.spec else "N/A"
            spec_min = str(stats.spec.spec_min) if stats.spec and stats.spec.spec_min is not None else "N/A"
            spec_max = str(stats.spec.spec_max) if stats.spec and stats.spec.spec_max is not None else "N/A"
            obs_min = str(stats.min_val) if stats.min_val is not None else "N/A"
            obs_max = str(stats.max_val) if stats.max_val is not None else "N/A"
            print(f"{field_name:<30} {reg_bit:>8} {spec_min:>10} {spec_max:>10} {obs_min:>10} {obs_max:>10}")
        else:
            print(f"{field_name:<30} {'N/A':>8} {'N/A':>10} {'N/A':>10} {'N/A':>10} {'N/A':>10}")

    if len(fields) > 15:
        print(f"  ... and {len(fields) - 15} more fields (see field_statistics.csv)")

    print(f"\nOutput files:")
    print(f"  - test_vectors_summary.csv     : Basic CSV with all vectors")
    print(f"  - test_vectors_extended.csv    : CSV with statistics header")
    print(f"  - field_statistics.csv         : Statistics per field")
    print(f"  - field_statistics_report.txt  : Human-readable report")


if __name__ == '__main__':
    multiprocessing.freeze_support()  # Required for Windows
    main()