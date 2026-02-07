#!/usr/bin/env python3
"""Test script to verify PyVSC file parsing works correctly."""

import os
import re
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class FieldSpec:
    """Specification for a field extracted from PyVSC source."""
    name: str
    bit_width: int = 32
    is_signed: bool = False
    spec_min: Optional[int] = None
    spec_max: Optional[int] = None
    type_name: str = ""


def parse_pyvsc_file(module_name: str) -> Dict[str, FieldSpec]:
    """Parse PyVSC source file to extract field specifications."""
    field_specs: Dict[str, FieldSpec] = {}

    pyvsc_file = f"{module_name}.py"
    if not os.path.exists(pyvsc_file):
        print(f"Warning: Could not find PyVSC source file: {pyvsc_file}")
        return field_specs

    with open(pyvsc_file, 'r') as f:
        content = f.read()

    print(f"File size: {len(content)} bytes")

    # Type patterns as list of tuples
    type_patterns = [
        (r'vsc\.rand_bit_t\((\d+)\)', 'bit', lambda m: int(m.group(1)), False),
        (r'vsc\.randc_bit_t\((\d+)\)', 'randc_bit', lambda m: int(m.group(1)), False),
        (r'vsc\.rand_uint8_t\(\)', 'uint8', lambda m: 8, False),
        (r'vsc\.rand_uint16_t\(\)', 'uint16', lambda m: 16, False),
        (r'vsc\.rand_uint32_t\(\)', 'uint32', lambda m: 32, False),
        (r'vsc\.rand_uint64_t\(\)', 'uint64', lambda m: 64, False),
        (r'vsc\.rand_int8_t\(\)', 'int8', lambda m: 8, True),
        (r'vsc\.rand_int16_t\(\)', 'int16', lambda m: 16, True),
        (r'vsc\.rand_int32_t\(\)', 'int32', lambda m: 32, True),
        (r'vsc\.rand_int64_t\(\)', 'int64', lambda m: 64, True),
        (r'vsc\.rand_enum_t\((\w+)\)', 'enum', lambda m: 32, False),
    ]

    # Find all field declarations
    field_decl_pattern = r'self\.(\w+)\s*=\s*(vsc\.\w+(?:_t)?\([^)]*\))'
    decl_matches = list(re.finditer(field_decl_pattern, content))
    print(f"Found {len(decl_matches)} field declarations")

    for match in decl_matches:
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
            field_specs[field_name] = FieldSpec(
                name=field_name,
                bit_width=32,
                is_signed=True,
                type_name='unknown'
            )

    # Parse constraint ranges
    range_pattern = r'self\.(\w+)\s+in\s+vsc\.rangelist\(vsc\.rng\((-?\d+),\s*(-?\d+)\)\)'
    range_matches = list(re.finditer(range_pattern, content))
    print(f"Found {len(range_matches)} range constraints")

    for match in range_matches:
        field_name = match.group(1)
        spec_min = int(match.group(2))
        spec_max = int(match.group(3))

        if field_name in field_specs:
            field_specs[field_name].spec_min = spec_min
            field_specs[field_name].spec_max = spec_max

    # Parse discrete value constraints
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
                enum_match = re.search(r'(\w+)\.(\w+)', val)
                if enum_match:
                    enum_member = enum_match.group(2)
                    enum_def_pattern = rf'{enum_member}\s*=\s*(-?\d+)'
                    enum_val_match = re.search(enum_def_pattern, content)
                    if enum_val_match:
                        values.append(int(enum_val_match.group(1)))

        if values:
            if field_name in field_specs:
                if field_specs[field_name].spec_min is None:
                    field_specs[field_name].spec_min = min(values)
                    field_specs[field_name].spec_max = max(values)

    print(f"Processed discrete value constraints")

    return field_specs


if __name__ == '__main__':
    print("Testing PyVSC file parsing...")
    print("=" * 60)

    specs = parse_pyvsc_file("example_sv_classes")

    print(f"\nParsed {len(specs)} field specifications:")
    print("-" * 80)
    print(f"{'Field Name':<35} {'Type':<10} {'Bits':>6} {'Signed':>8} {'Min':>10} {'Max':>10}")
    print("-" * 80)

    for name, spec in list(specs.items())[:20]:
        min_str = str(spec.spec_min) if spec.spec_min is not None else "N/A"
        max_str = str(spec.spec_max) if spec.spec_max is not None else "N/A"
        signed_str = "Yes" if spec.is_signed else "No"
        print(f"{name:<35} {spec.type_name:<10} {spec.bit_width:>6} {signed_str:>8} {min_str:>10} {max_str:>10}")

    if len(specs) > 20:
        print(f"... and {len(specs) - 20} more fields")
