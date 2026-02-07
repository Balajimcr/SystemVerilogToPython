#!/usr/bin/env python3
"""
Test Vector Generator using PyVSC Constraint Randomization

This script generates randomized test vectors by:
1. Loading a PyVSC-generated constraint model
2. Reading field names from a hw_field.txt file
3. Randomizing the model N times
4. Writing each configuration to separate output files

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
import argparse
import importlib
import random
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime


def parse_hw_field_file(filepath: str) -> List[Tuple[str, str]]:
    """Parse hw_field.txt to get list of (field_name, default_value) tuples."""
    fields = []
    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
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


def get_field_value(obj, field_name: str) -> Optional[any]:
    """Get the value of a field from the randomized object."""
    try:
        value = getattr(obj, field_name)
        # Handle PyVSC field types - they may have a .val property or be directly accessible
        if hasattr(value, 'val'):
            return value.val
        return value
    except AttributeError:
        return None


def generate_test_vector(obj, fields: List[Tuple[str, str]], run_id: int) -> Dict[str, any]:
    """Generate a single test vector by randomizing the object."""
    try:
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

    return vector


def write_test_vector_file(vector: Dict[str, any], output_path: str, run_id: int):
    """Write a single test vector to a file."""
    with open(output_path, 'w') as f:
        f.write(f"# Test Vector Configuration - Run {run_id}\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("#\n")
        for field_name, value in vector.items():
            f.write(f"{field_name} {value}\n")


def write_summary_file(vectors: List[Dict[str, any]], output_dir: str, fields: List[Tuple[str, str]]):
    """Write a summary CSV file with all test vectors."""
    summary_path = os.path.join(output_dir, "test_vectors_summary.csv")
    with open(summary_path, 'w') as f:
        # Header
        field_names = [field[0] for field in fields]
        f.write("run_id," + ",".join(field_names) + "\n")

        # Data rows
        for run_id, vector in enumerate(vectors):
            values = [str(vector.get(name, "")) for name in field_names]
            f.write(f"{run_id}," + ",".join(values) + "\n")

    print(f"Summary written to: {summary_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate randomized test vectors using PyVSC constraint model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s example_sv_classes IspYuv2rgbCfg hw_field.txt 10
  %(prog)s example_sv_classes IspYuv2rgbCfg hw_field.txt 100 ./output
  %(prog)s my_constraints MyClass fields.txt 50 --seed 12345
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
            vsc.set_randstate(args.seed)
        except:
            pass

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
    print(f"=" * 50)

    # Parse field file
    fields = parse_hw_field_file(args.hw_field_file)
    print(f"\nLoaded {len(fields)} fields from {args.hw_field_file}")

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

    # Generate test vectors
    print(f"\nGenerating {args.num_runs} test vectors...")
    vectors = []
    successful = 0

    for run_id in range(args.num_runs):
        vector = generate_test_vector(obj, fields, run_id)
        vectors.append(vector)

        # Write individual file
        if args.format in ['txt', 'both']:
            output_path = os.path.join(args.output_dir, f"{args.prefix}_{run_id:04d}.txt")
            write_test_vector_file(vector, output_path, run_id)

        successful += 1

        # Progress indicator
        if (run_id + 1) % 10 == 0 or run_id == args.num_runs - 1:
            print(f"  Generated {run_id + 1}/{args.num_runs} vectors")

    # Write summary
    if args.format in ['csv', 'both']:
        write_summary_file(vectors, args.output_dir, fields)

    print(f"\nGeneration complete!")
    print(f"  Successful: {successful}/{args.num_runs}")
    print(f"  Output files in: {args.output_dir}")

    # Show sample output
    if vectors:
        print(f"\nSample output (Run 0):")
        for i, (field_name, _) in enumerate(fields[:10]):
            value = vectors[0].get(field_name, "N/A")
            print(f"  {field_name}: {value}")
        if len(fields) > 10:
            print(f"  ... and {len(fields) - 10} more fields")


if __name__ == '__main__':
    main()
