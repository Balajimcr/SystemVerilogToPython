from __future__ import annotations

import csv
import re
import sys
from bisect import bisect_left
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Precompiled regex patterns for performance
_PATTERN_MIN_VALUE = re.compile(r"<MinValue>(.+?)</MinValue>")
_PATTERN_MAX_VALUE = re.compile(r"<MaxValue>(.+?)</MaxValue>")
_PATTERN_NORMAL_VALUE = re.compile(r"<NormalValue>(.+?)</NormalValue>")
_PATTERN_PARAM_NAME = re.compile(r'<Parameter[^>]*name="([^"]+)"')
_PATTERN_FIELD_NAME = re.compile(r'<Field[^>]*name="([^"]+)"')
_PATTERN_TC_END = re.compile(r"</TestConstraint>")
_PATTERN_TC_INLINE = re.compile(r"<TestConstraint>(.*?)</TestConstraint>")
_PATTERN_TC_LAST = re.compile(r"(.*?)</TestConstraint>")

# XML entity translations — single-pass via compiled alternation
_XML_ENTITY_MAP = {
    "&lt;": "<",
    "&gt;": ">",
    '&amp;': '&',
    "&apos;": "'",
    "&quot;": '"',
}
_XML_ENTITY_RE = re.compile("|".join(re.escape(k) for k in _XML_ENTITY_MAP))


def _entity_replacer(m: re.Match) -> str:
    return _XML_ENTITY_MAP[m.group()]


def _decode_entities(lines: List[str]) -> List[str]:
    """Replace XML character entities with their literal characters."""
    sub = _XML_ENTITY_RE.sub
    repl = _entity_replacer
    return [sub(repl, line) for line in lines]


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
                match = _PATTERN_TC_INLINE.search(stmt)
                if match:
                    constraint_body.append(f"       {match.group(1)}")
                    constraint_body.append("\n")
            else:
                # Multi-line constraint
                first = stmt.replace("<TestConstraint>", "").strip()
                constraint_body.append(f"       {first}\n")
                for j in range(i + 1, tc_end_idx):
                    constraint_body.append(f"       {block[j].strip()}\n")
                last_match = _PATTERN_TC_LAST.search(block[tc_end_idx])
                if last_match:
                    constraint_body.append(f"       {last_match.group(1)}")
                constraint_body.append("\n")

            i = tc_end_idx + 1
        else:
            i += 1

    return constraint_body


# -----------------------------------------------------------------------------
# TopParameter data structure
# -----------------------------------------------------------------------------

class TopParamInfo:
    """Holds metadata for a single top-level parameter extracted from XML."""
    __slots__ = ("name", "normal_value", "min_value", "max_value",
                 "override_min", "override_max", "test_constraints")

    def __init__(
        self,
        name: str,
        normal_value: str = "0",
        min_value: str = "0",
        max_value: str = "0",
        test_constraints: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.normal_value = normal_value
        self.min_value = min_value
        self.max_value = max_value
        # Override columns: user edits these in the CSV to control ranges
        self.override_min = min_value
        self.override_max = max_value
        self.test_constraints = test_constraints or []


def _extract_top_param_from_block(block: List[str]) -> Optional[TopParamInfo]:
    """Extract a TopParamInfo from a <Parameter> block inside <TopParameter>."""
    name = _extract_name_from_block(block, is_field=False)
    if name is None:
        return None

    min_val = "0"
    max_val = "0"
    normal_val = "0"

    for stmt in block:
        m = _PATTERN_MIN_VALUE.search(stmt)
        if m:
            min_val = m.group(1).strip()
        m = _PATTERN_MAX_VALUE.search(stmt)
        if m:
            max_val = m.group(1).strip()
        m = _PATTERN_NORMAL_VALUE.search(stmt)
        if m:
            normal_val = m.group(1).strip()

    # Extract TestConstraint bodies (reuse existing function)
    tc_body = _extract_test_constraints(block)
    # Replace $ placeholders with the field name
    tc_lines = [c.replace("$", name).strip() for c in tc_body if c.strip()]

    return TopParamInfo(
        name=name,
        normal_value=normal_val,
        min_value=min_val,
        max_value=max_val,
        test_constraints=tc_lines,
    )


def _extract_top_parameters(xml: List[str]) -> Tuple[List[TopParamInfo], List[Tuple[int, int]]]:
    """Scan the XML for <TopParameter> sections.

    Returns:
        top_params  : List of TopParamInfo objects.
        span_ranges : List of (start_line, end_line) inclusive indices for each
                      <TopParameter>…</TopParameter> block so the caller can
                      skip those lines during regular parameter collection.
    """
    top_params: List[TopParamInfo] = []
    span_ranges: List[Tuple[int, int]] = []

    i = 0
    while i < len(xml):
        stripped = xml[i].strip()
        if stripped.startswith("<TopParameter") and not stripped.startswith("</TopParameter"):
            block_start = i
            # Find matching </TopParameter>
            j = i + 1
            while j < len(xml):
                if xml[j].strip().startswith("</TopParameter"):
                    break
                j += 1
            block_end = j
            span_ranges.append((block_start, block_end))

            # Now parse individual <Parameter> blocks inside
            inner = xml[block_start + 1 : block_end]
            param_close_idx = _build_close_index(inner, "</Parameter>")
            for k, line in enumerate(inner):
                if _PATTERN_PARAM_NAME.search(line):
                    end_idx = _find_close(param_close_idx, k + 1)
                    if end_idx == -1:
                        end_idx = len(inner) - 1
                    param_block = inner[k : end_idx + 1]
                    info = _extract_top_param_from_block(param_block)
                    if info is not None:
                        top_params.append(info)

            i = block_end + 1
        else:
            i += 1

    return top_params, span_ranges


def export_top_params_csv(
    top_params: List[TopParamInfo],
    csv_path: str,
) -> None:
    """Write the TopParameter list to a CSV file.

    CSV columns:
        Name, NormalValue, MinValue, MaxValue, OverrideMin, OverrideMax, TestConstraint

    The user can edit OverrideMin / OverrideMax to narrow or shift the
    randomization ranges.  The tool reads these overrides back at runtime.
    """
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Name", "NormalValue", "MinValue", "MaxValue",
            "OverrideMin", "OverrideMax", "TestConstraint",
        ])
        for p in top_params:
            tc_str = " ; ".join(p.test_constraints) if p.test_constraints else ""
            writer.writerow([
                p.name,
                p.normal_value,
                p.min_value,
                p.max_value,
                p.override_min,
                p.override_max,
                tc_str,
            ])
    print(f"TopParameter CSV exported: {csv_path}  ({len(top_params)} entries)")


def load_top_params_csv(csv_path: str) -> List[TopParamInfo]:
    """Read a TopParameter CSV (previously exported by *export_top_params_csv*).

    Returns a list of TopParamInfo objects with *override_min* and
    *override_max* populated from the CSV's OverrideMin / OverrideMax columns.
    """
    params: List[TopParamInfo] = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", "").strip()
            if not name:
                continue
            info = TopParamInfo(
                name=name,
                normal_value=row.get("NormalValue", "0").strip(),
                min_value=row.get("MinValue", "0").strip(),
                max_value=row.get("MaxValue", "0").strip(),
            )
            info.override_min = row.get("OverrideMin", info.min_value).strip()
            info.override_max = row.get("OverrideMax", info.max_value).strip()
            tc_str = row.get("TestConstraint", "").strip()
            if tc_str:
                info.test_constraints = [c.strip() for c in tc_str.split(";") if c.strip()]
            params.append(info)
    return params


# -----------------------------------------------------------------------------
# Block processing — returns classified output directly
# (rand_decls, uvm_fields, range_constraints, test_constraints)
# This eliminates the post-hoc _classify_and_collect_lines re-scan.
# -----------------------------------------------------------------------------
def _process_block(
    block: List[str],
    idx_offset: int,
    is_field: bool,
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """
    Process a Parameter or Field block.
    Returns (rand_decls, uvm_fields, range_constraints, test_constraints).
    """
    name = _extract_name_from_block(block, is_field)
    if name is None:
        return [], [], [], []

    min_value, max_value, has_min_value = _extract_value_range(block)
    constraint_body = _extract_test_constraints(block)

    # Replace $ with variable name in constraints
    const = [c.replace("$", name) for c in constraint_body]

    # Build SystemVerilog fragments — classified at source
    rand_decls: List[str] = []
    uvm_fields: List[str] = []
    range_constraints: List[str] = []
    test_constraints: List[str] = []

    # Declare variable
    if min_value >= 0:
        rand_decls.append(f" rand bit [31:0] {name};\n")
    else:
        rand_decls.append(f" rand bit signed [31:0] {name};\n")
    uvm_fields.append(f" `uvm_field_int({name}, UVM_DEFAULT)\n")

    # Add range constraint if min/max present
    if has_min_value:
        range_constraints.extend([
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

    return rand_decls, uvm_fields, range_constraints, test_constraints


def _process_parameter_block(
    block: List[str],
    idx_offset: int,
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """Parse a <Parameter> block."""
    return _process_block(block, idx_offset, is_field=False)


def _process_field_block(
    block: List[str],
    idx_offset: int,
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """Parse a <Field> block."""
    return _process_block(block, idx_offset, is_field=True)


# -----------------------------------------------------------------------------
# Closing-tag index builder (replaces O(n²) forward scans)
# -----------------------------------------------------------------------------
def _build_close_index(xml: List[str], tag: str) -> List[int]:
    """Return sorted list of line indices containing the given closing tag."""
    return [i for i, line in enumerate(xml) if tag in line]


def _find_close(indices: List[int], start: int) -> int:
    """Return the first index in *indices* that is >= *start*, or len(xml)."""
    pos = bisect_left(indices, start)
    return indices[pos] if pos < len(indices) else -1


def generate_rand_item(xml_path: str, sv_path: str, top_csv_path: str = "") -> None:
    """Parse xml_path and write the generated UVM random-item class to sv_path.

    If *top_csv_path* is provided (or defaults to ``<sv_stem>_top_params.csv``
    next to *sv_path*), any ``<TopParameter>`` groups are extracted and
    exported to the CSV for external range control.  The TopParameter fields
    are **kept** in the SV class — they are not filtered out.
    """
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

    # --- TopParameter extraction (export to CSV, but keep in SV) ---
    top_params, _ = _extract_top_parameters(xml)
    if top_params:
        print(f"  Found {len(top_params)} TopParameter(s): "
              f"{', '.join(p.name for p in top_params)}")

        # Default CSV path: alongside SV output
        if not top_csv_path:
            sv_stem = Path(sv_path).stem
            top_csv_path = str(Path(sv_path).parent / f"{sv_stem}_top_params.csv")
        export_top_params_csv(top_params, top_csv_path)

    # Scan for IP name and collect Parameter/Field blocks
    ip_name = ""
    param_blocks: List[List[str]] = []
    field_blocks: List[List[str]] = []
    in_sim_parameter = False
    in_top_parameter = False

    # Pre-index closing tags — O(n) once instead of O(n) per match
    param_close_idx = _build_close_index(xml, "</Parameter>")
    field_close_idx = _build_close_index(xml, "</Field>")

    for i, line in enumerate(xml):
        # Extract IP name
        if 'FunctionMap IP' in line:
            ip_name = line.split('"')[1].lower()

        # Track SimParameter blocks (skip entirely)
        stripped = line.strip()
        in_sim_parameter = (
            in_sim_parameter if not stripped.startswith("<SimParameter") else True
        )
        if stripped.startswith("</SimParameter"):
            in_sim_parameter = False

        # Track TopParameter wrapper tags (but process inner Parameters)
        if stripped.startswith("<TopParameter") and not stripped.startswith("</TopParameter"):
            in_top_parameter = True
        if stripped.startswith("</TopParameter"):
            in_top_parameter = False

        # Collect Parameter blocks (skip SimParameter, include TopParameter)
        if not in_sim_parameter and _PATTERN_PARAM_NAME.search(line):
            end_idx = _find_close(param_close_idx, i + 1)
            if end_idx == -1:
                end_idx = len(xml)
            param_blocks.append(xml[i:end_idx + 1])

        # Collect Field blocks
        if 'Field name' in line:
            end_idx = _find_close(field_close_idx, i + 1)
            if end_idx == -1:
                end_idx = len(xml)
            field_blocks.append(xml[i:end_idx + 1])

    sys.stdout.write("\n")

    # Process blocks sequentially (ThreadPoolExecutor removed —
    # CPU-bound string work under GIL gains nothing from threads)
    all_rand: List[str] = []
    all_uvm: List[str] = []
    all_range: List[str] = []
    all_test: List[str] = []

    for idx, blk in enumerate(param_blocks):
        rand, uvm, rng, tc = _process_parameter_block(blk, idx)
        all_rand.extend(rand)
        all_uvm.extend(uvm)
        all_range.extend(rng)
        all_test.extend(tc)

    field_offset_start = len(param_blocks) + 1
    for idx, blk in enumerate(field_blocks):
        rand, uvm, rng, tc = _process_field_block(blk, field_offset_start + idx)
        all_rand.extend(rand)
        all_uvm.extend(uvm)
        all_range.extend(rng)
        all_test.extend(tc)

    # Assemble final SystemVerilog class
    my_file = [
        f"class {ip_name}_rand_item extends uvm_sequence_item;\n\n",
        *all_rand,
        "\n",
        f"`uvm_object_utils_begin({ip_name}_rand_item)\n",
        *all_uvm,
        "`uvm_object_utils_end\n",
        *all_range,
        *all_test,
        "endclass\n",
    ]

    # Write output file
    Path(sv_path).write_text("".join(my_file), encoding="ascii", errors="ignore")
    print(f"Generated {sv_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python XML_to_sv_Converter.py <source_xml> <dest_sv> [top_params.csv]")
    csv_out = sys.argv[3] if len(sys.argv) > 3 else ""
    generate_rand_item(sys.argv[1], sys.argv[2], csv_out)
