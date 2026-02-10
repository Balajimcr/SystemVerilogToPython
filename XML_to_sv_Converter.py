from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import List, Tuple

# -----------------------------------------------------------------------------
# Compiled regex patterns
# -----------------------------------------------------------------------------
RE_MIN_VALUE = re.compile(r'<MinValue>(.*?)</MinValue>')
RE_MAX_VALUE = re.compile(r'<MaxValue>(.*?)</MaxValue>')
RE_PARAMETER_NAME = re.compile(r'<Parameter[^>]*name=["\']([^"\']+)')
RE_FIELD_NAME = re.compile(r'<Field[^>]*name=["\']([^"\']+)')
RE_TEST_CONSTRAINT_END = re.compile(r'</TestConstraint>')

# -----------------------------------------------------------------------------
# XML entity decoding map
# -----------------------------------------------------------------------------
XML_ENTITY_MAP = {
    "&lt;": "<",
    "&gt;": ">",
    "&amp;": "&",
    "&apos;": "'",
    "&quot;": '"',
}

# -----------------------------------------------------------------------------
# Utility helpers
# -----------------------------------------------------------------------------
def decode_xml_entities(lines: List[str]) -> List[str]:
    decoded_lines = []
    for line in lines:
        for src, dst in XML_ENTITY_MAP.items():
            line = line.replace(src, dst)
        decoded_lines.append(line)
    return decoded_lines


def print_progress(current: int, total: int) -> None:
    if total == 0 or current % 50:
        return
    percent = int(100 * current / total)
    sys.stdout.write(f"\rParsing XML: {percent:3d}%")
    sys.stdout.flush()


# -----------------------------------------------------------------------------
# XML block extraction helpers
# -----------------------------------------------------------------------------
def extract_block_name(block: List[str], is_field: bool) -> str | None:
    pattern = RE_FIELD_NAME if is_field else RE_PARAMETER_NAME
    match = pattern.search(block[0])
    if not match:
        return None

    name = match.group(1)
    if '"' in name or "'" in name:
        return None
    return name


def extract_value_range(block: List[str]) -> Tuple[int, int, bool]:
    min_value = 0
    max_value = 0
    has_min_value = False

    for line in block:
        if "<MinValue>" in line:
            match = RE_MIN_VALUE.search(line)
            if match:
                min_value = int(match.group(1))
                has_min_value = True
        elif "<MaxValue>" in line:
            match = RE_MAX_VALUE.search(line)
            if match:
                max_value = int(match.group(1))

    return min_value, max_value, has_min_value


def extract_test_constraints(block: List[str]) -> List[str]:
    constraints = []
    index = 0
    block_len = len(block)

    while index < block_len:
        line = block[index]
        if "<TestConstraint>" not in line:
            index += 1
            continue

        end_index = index
        while end_index < block_len and not RE_TEST_CONSTRAINT_END.search(block[end_index]):
            end_index += 1
        if end_index >= block_len:
            break

        if index == end_index:
            body = line.split("<TestConstraint>")[1].split("</TestConstraint>")[0]
            constraints.append(f"    {body};\n")
        else:
            constraints.append(f"    {line.replace('<TestConstraint>', '').strip()}\n")
            for mid in range(index + 1, end_index):
                constraints.append(f"    {block[mid].strip()}\n")
            tail = block[end_index].replace("</TestConstraint>", "").strip()
            if tail:
                constraints.append(f"    {tail}\n")

        index = end_index + 1

    return constraints


# -----------------------------------------------------------------------------
# Block processing
# -----------------------------------------------------------------------------
def process_block(block: List[str], constraint_index: int, is_field: bool) -> Tuple[List[str], List[str]]:
    name = extract_block_name(block, is_field)
    if not name:
        return [], []

    min_value, max_value, has_range = extract_value_range(block)
    test_constraints = extract_test_constraints(block)
    test_constraints = [line.replace("$", name) for line in test_constraints]

    declaration = (
        f"rand bit [31:0] {name};\n"
        if min_value >= 0
        else f"rand bit signed [31:0] {name};\n"
    )

    declarations = [declaration]
    constraints = []

    if has_range:
        declarations.extend([
            f"constraint CR_VAR_RANGE_{name} {{\n",
            f"    {name} >= {min_value};\n",
            f"    {name} <= {max_value};\n",
            "}\n",
        ])

    if test_constraints:
        constraints.append(f"constraint cr{constraint_index} {{\n")
        constraints.extend(test_constraints)
        constraints.append("}\n")

    return declarations, constraints


# -----------------------------------------------------------------------------
# Main generator
# -----------------------------------------------------------------------------
def generate_rand_item(xml_path: str, sv_path: str) -> None:
    print(f"Processing: {xml_path}")

    xml_lines = decode_xml_entities(
        Path(xml_path).read_text(encoding="ascii", errors="ignore").splitlines()
    )

    ip_name = "unknown_ip"
    parameter_blocks: List[List[str]] = []
    field_blocks: List[List[str]] = []

    index = 0
    total_lines = len(xml_lines)
    inside_sim_parameter = False

    while index < total_lines:
        line = xml_lines[index]
        stripped = line.strip()
        print_progress(index, total_lines)

        if 'FunctionMap IP' in line:
            ip_name = line.split('"')[1].lower()

        if stripped.startswith("<SimParameter"):
            inside_sim_parameter = True
        elif stripped.startswith("</SimParameter>"):
            inside_sim_parameter = False

        if not inside_sim_parameter and RE_PARAMETER_NAME.search(line):
            start = index
            while index < total_lines and "</Parameter>" not in xml_lines[index]:
                index += 1
            parameter_blocks.append(xml_lines[start:index + 1])

        elif RE_FIELD_NAME.search(line):
            start = index
            while index < total_lines and "</Field>" not in xml_lines[index]:
                index += 1
            field_blocks.append(xml_lines[start:index + 1])

        index += 1

    print("\nGenerating SystemVerilog...")

    with open(sv_path, "w", encoding="ascii", errors="ignore") as sv_file:
        sv_file.write(f"// Auto-generated from XML for {ip_name}\n")
        sv_file.write(f"class {ip_name}_rand_item extends uvm_sequence_item;\n\n")

        constraint_index = 0

        for block in parameter_blocks:
            decls, cons = process_block(block, constraint_index, False)
            for line in decls:
                sv_file.write(f"    {line}")
            for line in cons:
                sv_file.write(f"    {line}")
            constraint_index += 1

        for block in field_blocks:
            decls, cons = process_block(block, constraint_index, True)
            for line in decls:
                sv_file.write(f"    {line}")
            for line in cons:
                sv_file.write(f"    {line}")
            constraint_index += 1

        sv_file.write("endclass\n")

    print(f"Generated: {sv_path}")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python xml_to_sv_converter.py <input.xml> <output.sv>")
    generate_rand_item(sys.argv[1], sys.argv[2])
