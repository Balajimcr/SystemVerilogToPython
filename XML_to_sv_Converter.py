from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple
import concurrent.futures

# Precompiled regex patterns for performance
_PATTERN_MIN_VALUE = re.compile(r"<MinValue>(.+?)</MinValue>")
_PATTERN_MAX_VALUE = re.compile(r"<MaxValue>(.+?)</MaxValue>")
_PATTERN_PARAM_NAME = re.compile(r'<Parameter[^>]*name="([^"]+)")
_PATTERN_FIELD_NAME = re.compile(r'<Field[^>]*name="([^"]+)")
_PATTERN_TC_END = re.compile(r"</TestConstraint>")

# XML entity translations (moved to constant)
_XML_ENTITY_MAP = {
    "&lt;": "<",
    "&gt;": ">",'&amp;': '&',
    "&apos;": "'",
    "&quot;": '"',
}

def _decode_entities(lines: List[str]) -> List[str]:
    """Replace XML character entities with their literal characters."""
    translated = []
    for line in lines:
        translated_line = line
        for src, dst in _XML_ENTITY_MAP.items():
            translated_line = translated_line.replace(src, dst)
        translated.append(translated_line)
    return translated

def _extract_name_from_block(block: List[str], is_field: bool) -> str | None:
    """Extract parameter or field name from block, return None if invalid."""
    first_line = block[0]
    pattern = _PATTERN_FIELD_NAME if is_field else _PATTERN_PARAM_NAME
    match = pattern.search(first_line)
    if not match:
        return None
    
    name = match.group(1)
    return None if ("." in name or "|" in name) else name

def _extract_value_range(block: List[str]) -> Tuple[int, int, bool]:
    """Extract min and max values from block."""
    min_value = max_value = 0
    has_min_value = False
    
    for stmt in block:
        if "<MinValue>" in stmt:
            match = _PATTERN_MIN_VALUE.search(stmt)
            if match:
                min_value = int(match.group(1))
                has_min_value = True
        if "<MaxValue>" in stmt:
            match = _PATTERN_MAX_VALUE.search(stmt)
            if match:
                max_value = int(match.group(1))
    
    return min_value, max_value, has_min_value

def _extract_test_constraints(block: List[str]) -> List[str]:
    """Extract all TestConstraint content from block."""
    constraint_body = []
    i = 0
    
    while i < len(block):
        stmt = block[i]
        if "<TestConstraint>" in stmt:
            # Find closing tag
            tc_end_idx = -1
            for j in range(i, len(block)):
                if _PATTERN_TC_END.search(block[j]):
                    tc_end_idx = j
                    break
            
            if tc_end_idx == -1:
                i += 1
                continue
            
            if tc_end_idx == i:
                # Single-line constraint
                match = re.search(r"<TestConstraint>(.*?)</TestConstraint>", stmt)
                if match:
                    constraint_body.append(f"       {match.group(1)}")
                    constraint_body.append("\n")
            else:
                # Multi-line constraint
                first = stmt.replace("<TestConstraint>", "").strip()
                constraint_body.append(f"       {first}\n")
                for j in range(i + 1, tc_end_idx):
                    constraint_body.append(f"       {block[j].strip()}\n")
                last_match = re.search(r"(.*?)</TestConstraint>", block[tc_end_idx])
                if last_match:
                    constraint_body.append(f"       {last_match.group(1)}")
                constraint_body.append("\n")
            
            i = tc_end_idx + 1
        else:
            i += 1
    
    return constraint_body

def _process_block(
    block: List[str],
    idx_offset: int,
    is_field: bool,
) -> Tuple[List[str], List[str]]:
    """
    Process a Parameter or Field block.
    Returns (lines, test_constraints).
    """
    name = _extract_name_from_block(block, is_field)
    if name is None:
        return [], []
    
    min_value, max_value, has_min_value = _extract_value_range(block)
    constraint_body = _extract_test_constraints(block)
    
    # Replace $ with variable name in constraints
    const = [c.replace("$", name) for c in constraint_body]
    
    # Build SystemVerilog fragments
    lines: List[str] = []
    test_constraints: List[str] = []
    
    # Declare variable
    if min_value >= 0:
        lines.append(f" rand bit [31:0] {name};\n")
    else:
        lines.append(f" rand bit signed [31:0] {name};\n")
    lines.append(f" `uvm_field_int({name}, UVM_DEFAULT)\n")
    
    # Add range constraint if min/max present
    if has_min_value:
        lines.extend([
            f"   constraint CR_VAR_RANGE_{name}\n",
            "     {\n",
            f"       ({name} >= {min_value} && {name} <= {max_value});\n",
            "     }\n\n",
        ])
    
    # Add test constraints if present
    if constraint_body:
        test_constraints.extend([
            f"   constraint cr{idx_offset}\n",
            "     {\n",
            *const,
            "     }\n\n",
        ])
    
    return lines, test_constraints

def _process_parameter_block(
    block: List[str],
    idx_offset: int,
) -> Tuple[List[str], List[str]]:
    """Parse a <Parameter> block; returns (lines, test_constraints)."""
    return _process_block(block, idx_offset, is_field=False)

def _process_field_block(
    block: List[str],
    idx_offset: int,
) -> Tuple[List[str], List[str]]:
    """Parse a <Field> block; returns (lines, test_constraints)."""
    return _process_block(block, idx_offset, is_field=True)

def _classify_and_collect_lines(all_lines: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """Classify lines into rand declarations, uvm_fields, and constraints."""
    rand: List[str] = []
    uvm_field: List[str] = []
    constraint: List[str] = []
    
    i = 0
    while i < len(all_lines):
        txt = all_lines[i]
        if "rand bit" in txt:
            rand.append(txt)
        elif "`uvm" in txt:
            uvm_field.append(txt)
        elif " constraint CR_VAR_RANGE_" in txt:
            constraint.extend(all_lines[i:i + 4])
            i += 3
        i += 1
    
    return rand, uvm_field, constraint

def generate_rand_item(xml_path: str, sv_path: str) -> None:
    """Parse xml_path and write the generated UVM random-item class to sv_path."""
    # Read XML file
    print(f"Processing file: {xml_path} …", end=" ")
    try:
        with open(xml_path, "r", encoding="ascii", errors="ignore") as f:
            raw_xml = f.readlines()
        print("opened")
    except Exception as e:
        print(f"failed ({e})")
        return
    
    # Decode XML entities
    xml = _decode_entities(raw_xml)
    
    # Scan for IP name and collect Parameter/Field blocks
    ip_name = ""
    param_blocks: List[List[str]] = []
    field_blocks: List[List[str]] = []
    in_sim_parameter = False
    total = len(xml)
    
    for i, line in enumerate(xml):
        # Extract IP name
        if 'FunctionMap IP' in line:
            ip_name = line.split('"')[1].lower()
        
        # Track SimParameter blocks
        stripped = line.strip()
        in_sim_parameter = (
            in_sim_parameter if not stripped.startswith("<SimParameter") else True
        )
        if stripped.startswith("</SimParameter"):
            in_sim_parameter = False
        
        # Collect Parameter blocks (skip SimParameter)
        if not in_sim_parameter and _PATTERN_PARAM_NAME.search(line):
            end_idx = next(
                (j for j in range(i + 1, len(xml)) if "</Parameter>" in xml[j]),
                len(xml),
            )
            param_blocks.append(xml[i:end_idx + 1])
        
        # Collect Field blocks
        if 'Field name' in line:
            end_idx = next(
                (j for j in range(i + 1, len(xml)) if "</Field>" in xml[j]),
                len(xml),
            )
            field_blocks.append(xml[i:end_idx + 1])
    
    sys.stdout.write("\n")
    
    # Process blocks in parallel
    all_lines: List[str] = []
    all_test_constraints: List[str] = []
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        param_results = list(executor.map(
            _process_parameter_block,
            param_blocks,
            range(len(param_blocks)),
        ))
        field_offset_start = len(param_blocks) + 1
        field_results = list(executor.map(
            _process_field_block,
            field_blocks,
            range(field_offset_start, field_offset_start + len(field_blocks)),
        ))
    
    # Gather results
    for lines, tests in param_results + field_results:
        all_lines.extend(lines)
        all_test_constraints.extend(tests)
    
    # Classify and reorganize lines
    rand, uvm_field, constraint = _classify_and_collect_lines(all_lines)
    
    # Assemble final SystemVerilog class
    my_file = [
        f"class {ip_name}_rand_item extends uvm_sequence_item;\n\n",
        *rand,
        "\n",
        f"`uvm_object_utils_begin({ip_name}_rand_item)\n",
        *uvm_field,
        "`uvm_object_utils_end\n",
        *constraint,
        *all_test_constraints,
        "endclass\n",
    ]
    
    # Write output file
    Path(sv_path).write_text("".join(my_file), encoding="ascii", errors="ignore")
    print(f"Generated {sv_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python xml_to_rand.py <source_xml> <dest_sv>")
    generate_rand_item(sys.argv[1], sys.argv[2])
