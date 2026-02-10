#!/usr/bin/env python3
"""
XML to SystemVerilog Converter (Dummy/Placeholder)

Converts XML register/constraint definitions to SystemVerilog (.sv) files.
This is a placeholder implementation. Replace with the actual converter.

Usage:
    python XML_to_sv_Converter.py input.xml output.sv

API Usage:
    from XML_to_sv_Converter import XMLtoSVConverter
    converter = XMLtoSVConverter()
    result = converter.convert_file("input.xml", "output.sv")
    # result.success: bool
    # result.sv_code: str
    # result.warnings: list[str]
    # result.output_path: str
"""

from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import List, Tuple

# -----------------------------------------------------------------------------
# Precompiled regex patterns
# -----------------------------------------------------------------------------
_PATTERN_MIN_VALUE = re.compile(r'<MinValue>(.*?)<\/MinValue>')
_PATTERN_MAX_VALUE = re.compile(r'<MaxValue>(.*?)<\/MaxValue>')
_PATTERN_PARAM_NAME = re.compile(r'<Parameter[^>]*name=["\']([^"\']+)')
_PATTERN_FIELD_NAME = re.compile(r'<Field[^>]*name=["\']([^"\']+)')
_PATTERN_TO_END = re.compile(r'</TestConstraint>')

# -----------------------------------------------------------------------------
# XML entity translations
# -----------------------------------------------------------------------------
_XML_ENTITY_MAP = {
    "&lt;": "<",
    "&gt;": ">",
    "&amp;": "&",
    "&apos;": "'",
    "&quot;": '"',
}

# -----------------------------------------------------------------------------
# Utility helpers
# -----------------------------------------------------------------------------
def decode_entities(lines: List[str]) -> List[str]:
    translated = []
    for line in lines:
        for src, dst in _XML_ENTITY_MAP.items():
            line = line.replace(src, dst)
        translated.append(line)
    return translated


def print_progress(current: int, total: int, bar_len: int = 40) -> None:
    if total == 0:
        return
    filled = int(bar_len * current / total)
    bar = '█' * filled + '-' * (bar_len - filled)
    perc = int(100 * current / total)
    sys.stdout.write(f'\rParsing XML: [{bar}] {perc:3d}%')
    sys.stdout.flush()


# -----------------------------------------------------------------------------
# XML block extraction helpers
# -----------------------------------------------------------------------------
def extract_name_from_block(block: List[str], is_field: bool) -> str | None:
    first_line = block[0]
    pattern = _PATTERN_FIELD_NAME if is_field else _PATTERN_PARAM_NAME
    match = pattern.search(first_line)
    if not match:
        return None

    name = match.group(1)
    if '"' in name or "'" in name:
        return None
    return name


def extract_value_range(block: List[str]) -> Tuple[int, int, bool]:
    min_value = 0
    max_value = 0
    has_min = False

    for stmt in block:
        if "<MinValue>" in stmt:
            m = _PATTERN_MIN_VALUE.search(stmt)
            if m:
                min_value = int(m.group(1))
                has_min = True

        if "<MaxValue>" in stmt:
            m = _PATTERN_MAX_VALUE.search(stmt)
            if m:
                max_value = int(m.group(1))

    return min_value, max_value, has_min


def extract_test_constraints(block: List[str]) -> List[str]:
    out: List[str] = []
    i = 0

    while i < len(block):
        line = block[i]
        if "<TestConstraint>" not in line:
            i += 1
            continue

        end_idx = -1
        for j in range(i, len(block)):
            if _PATTERN_TO_END.search(block[j]):
                end_idx = j
                break

        if end_idx == -1:
            i += 1
            continue

        if i == end_idx:
            m = re.search(r'<TestConstraint>(.*?)</TestConstraint>', line)
            if m:
                out.append(f"    {m.group(1)};\n")
        else:
            first = line.replace("<TestConstraint>", "").strip()
            out.append(f"    {first}\n")
            for k in range(i + 1, end_idx):
                out.append(f"    {block[k].strip()}\n")
            last = block[end_idx].replace("</TestConstraint>", "").strip()
            if last:
                out.append(f"    {last}\n")

        i = end_idx + 1

    return out


# -----------------------------------------------------------------------------
# Block processing
# -----------------------------------------------------------------------------
def process_block(
    block: List[str],
    idx: int,
    is_field: bool,
) -> Tuple[List[str], List[str]]:

    name = extract_name_from_block(block, is_field)
    if name is None:
        return [], []

    min_v, max_v, has_range = extract_value_range(block)
    tc_body = extract_test_constraints(block)

    tc_body = [l.replace('$', name) for l in tc_body]

    lines: List[str] = []
    constraints: List[str] = []

    # Variable declaration
    if min_v >= 0:
        lines.append(f"rand bit [31:0] {name};\n")
    else:
        lines.append(f"rand bit signed [31:0] {name};\n")

    # Range constraint
    if has_range:
        lines.extend([
            f"constraint CR_VAR_RANGE_{name} {{\n",
            f"    {name} >= {min_v};\n",
            f"    {name} <= {max_v};\n",
            "}\n",
        ])

    # TestConstraint
    if tc_body:
        constraints.append(f"constraint cr{idx} {{\n")
        constraints.extend(tc_body)
        constraints.append("}\n")

    return lines, constraints


def process_parameter_block(block: List[str], idx: int):
    return process_block(block, idx, is_field=False)


def process_field_block(block: List[str], idx: int):
    return process_block(block, idx, is_field=True)


# -----------------------------------------------------------------------------
# Main generator
# -----------------------------------------------------------------------------
def generate_rand_item(xml_path: str, sv_path: str) -> None:
    print(f"Processing: {xml_path}")

    try:
        raw = Path(xml_path).read_text(encoding="ascii", errors="ignore").splitlines()
    except Exception as e:
        print(f"ERROR: {e}")
        return

    xml = decode_entities(raw)

    ip_name = "unknown_ip"
    param_blocks: List[List[str]] = []
    field_blocks: List[List[str]] = []

    in_sim_param = False
    total = len(xml)

    for i, line in enumerate(xml):
        print_progress(i + 1, total)
        s = line.strip()

        if 'FunctionMap IP' in line:
            ip_name = line.split('"')[1].lower()

        if s.startswith("<SimParameter"):
            in_sim_param = True
        if s.startswith("</SimParameter>"):
            in_sim_param = False

        if not in_sim_param and _PATTERN_PARAM_NAME.search(line):
            end = next(j for j in range(i, len(xml)) if "</Parameter>" in xml[j])
            param_blocks.append(xml[i:end + 1])

        if _PATTERN_FIELD_NAME.search(line):
            end = next(j for j in range(i, len(xml)) if "</Field>" in xml[j])
            field_blocks.append(xml[i:end + 1])

    print("\nGenerating SystemVerilog...")

    with open(sv_path, "w", encoding="ascii", errors="ignore") as f:
        f.write(f"// Auto-generated from XML for {ip_name}\n")
        f.write(f"class {ip_name}_rand_item extends uvm_sequence_item;\n\n")

        idx = 0
        for blk in param_blocks:
            lines, cons = process_parameter_block(blk, idx)
            for l in lines:
                f.write(f"    {l}")
            for c in cons:
                f.write(f"    {c}")
            idx += 1

        for blk in field_blocks:
            lines, cons = process_field_block(blk, idx)
            for l in lines:
                f.write(f"    {l}")
            for c in cons:
                f.write(f"    {c}")
            idx += 1

        f.write("endclass\n")

    print(f"Generated: {sv_path}")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python XML_to_Sv_Converter.py <input.xml> <output.sv>")

    generate_rand_item(sys.argv[1], sys.argv[2])
