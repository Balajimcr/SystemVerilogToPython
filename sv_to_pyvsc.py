#!/usr/bin/env python3
"""
SystemVerilog to pyvsc Translation Assistant Tool

Assists with manual SV-to-pyvsc translation by parsing SystemVerilog constraint
classes and generating suggested pyvsc equivalents.

IMPORTANT: This is a translation ASSISTANT, not an automated converter.
All generated code should be reviewed and validated by a verification engineer.

Author: Algorithm Architect
Version: 1.1.0
"""

import re
import argparse
import sys
import textwrap
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from enum import Enum, auto


# =============================================================================
# ENUMS AND DATA STRUCTURES
# =============================================================================

class FieldType(Enum):
    """Type of random field."""
    RAND = auto()
    RANDC = auto()
    NON_RAND = auto()


class ConstraintType(Enum):
    """Type of constraint construct."""
    EQUALITY = auto()
    INEQUALITY = auto()
    RELATIONAL = auto()
    INSIDE = auto()
    IMPLICATION = auto()
    CONDITIONAL = auto()
    DISTRIBUTION = auto()
    SOLVE_ORDER = auto()
    UNIQUE = auto()
    FOREACH = auto()
    SOFT = auto()
    ARITHMETIC = auto()
    LOGICAL = auto()
    UNKNOWN = auto()


@dataclass
class SVField:
    """Represents a SystemVerilog field."""
    name: str
    width: int
    field_type: FieldType
    is_array: bool = False
    array_size: Optional[int] = None
    is_dynamic: bool = False
    is_enum: bool = False
    enum_type: Optional[str] = None
    original_line: str = ""
    data_type: str = "bit"
    is_signed: bool = False


@dataclass
class SVConstraint:
    """Represents a SystemVerilog constraint block."""
    name: str
    body: str
    original_lines: List[str] = field(default_factory=list)
    constructs: List[Tuple[ConstraintType, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class SVEnum:
    """Represents a SystemVerilog enum type."""
    name: str
    values: List[Tuple[str, Optional[int]]]
    width: int = 32
    original_lines: List[str] = field(default_factory=list)


@dataclass
class SVClass:
    """Represents a SystemVerilog class."""
    name: str
    parent_class: Optional[str]
    fields: List[SVField]
    constraints: List[SVConstraint]
    enums: List[SVEnum]
    original_code: str
    pre_randomize: Optional[str] = None
    post_randomize: Optional[str] = None


@dataclass
class TranslationResult:
    """Result of translation with metadata."""
    pyvsc_code: str
    warnings: List[str]
    manual_review_items: List[str]
    mapping_notes: List[str]
    statistics: Dict[str, int]


# =============================================================================
# CONSTANTS
# =============================================================================

# Data type width mappings
WIDTH_MAP = {
    'byte': 8,
    'shortint': 16,
    'int': 32,
    'longint': 64
}

# Python keywords to avoid prefixing with self.
PYTHON_KEYWORDS = frozenset({
    'if', 'else', 'for', 'while', 'in', 'not', 'and', 'or',
    'True', 'False', 'None', 'pass', 'break', 'continue', 'return',
    # SV keywords that should not get self. prefix
    'inside', 'dist', 'solve', 'before', 'soft', 'unique', 'foreach',
    'vsc', 'self', 'with', 'as',
    # SV block keywords
    'begin', 'end'
})

# Constraint analysis patterns
CONSTRAINT_PATTERNS = [
    (ConstraintType.SOLVE_ORDER, r'solve\s+\w+\s+before\s+\w+'),
    (ConstraintType.SOFT, r'soft\s+'),
    (ConstraintType.UNIQUE, r'unique\s*\{'),
    (ConstraintType.FOREACH, r'foreach\s*\('),
    (ConstraintType.DISTRIBUTION, r'\bdist\s*\{'),
    (ConstraintType.INSIDE, r'\binside\s*\{'),
    (ConstraintType.IMPLICATION, r'->'),
    (ConstraintType.CONDITIONAL, r'\bif\s*\('),
    (ConstraintType.EQUALITY, r'[^!<>=]==[^=]'),
    (ConstraintType.INEQUALITY, r'!='),
    (ConstraintType.RELATIONAL, r'[<>]=?'),
]


# =============================================================================
# SV PARSER
# =============================================================================

class SVParser:
    """Parses SystemVerilog constraint classes."""

    def __init__(self):
        self.enums: List[SVEnum] = []
        self.classes: List[SVClass] = []

    def parse(self, sv_code: str) -> List[SVClass]:
        """Parse SystemVerilog code and extract classes."""
        sv_code = self._remove_comments(sv_code)
        self.enums = self._extract_enums(sv_code)
        self.classes = self._extract_classes(sv_code)
        return self.classes

    @staticmethod
    def _remove_comments(code: str) -> str:
        """Remove single-line and multi-line comments."""
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        return code

    def _extract_enums(self, code: str) -> List[SVEnum]:
        """Extract enum definitions."""
        enums = []
        pattern = r'typedef\s+enum(?:\s+\w+\s*(?:\[(\d+):0\])?)?\s*\{([^}]+)\}\s*(\w+)\s*;'

        for match in re.finditer(pattern, code, re.DOTALL):
            width_str, values_str, name = match.groups()
            width = int(width_str) + 1 if width_str else 32
            values = self._parse_enum_values(values_str)

            enums.append(SVEnum(
                name=name,
                values=values,
                width=width,
                original_lines=[match.group(0)]
            ))

        return enums

    def _parse_enum_values(self, values_str: str) -> List[Tuple[str, Optional[int]]]:
        """Parse enum value declarations."""
        values = []
        for val in values_str.split(','):
            val = val.strip()
            if not val:
                continue
            if '=' in val:
                val_name, val_num = val.split('=', 1)
                values.append((val_name.strip(), self._parse_number(val_num.strip())))
            else:
                values.append((val, None))
        return values

    def _extract_classes(self, code: str) -> List[SVClass]:
        """Extract class definitions."""
        classes = []
        pattern = r'class\s+(\w+)(?:\s+extends\s+(\w+))?\s*;(.*?)endclass'

        for match in re.finditer(pattern, code, re.DOTALL):
            class_name, parent_class, class_body = match.groups()

            classes.append(SVClass(
                name=class_name,
                parent_class=parent_class,
                fields=self._extract_fields(class_body),
                constraints=self._extract_constraints(class_body),
                enums=self.enums,
                original_code=match.group(0),
                pre_randomize=self._extract_function(class_body, 'pre_randomize'),
                post_randomize=self._extract_function(class_body, 'post_randomize')
            ))

        return classes

    def _extract_fields(self, class_body: str) -> List[SVField]:
        """Extract field declarations from class body."""
        fields = []
        patterns = [
            # rand/randc bit/logic [signed] [N:0] name [array]
            r'^\s*(rand|randc)?\s*(bit|logic)\b\s*(signed)?\s*(?:\[(\d+):0\])?\s*(\w+)\s*(?:\[(\d+)\]|\[\])?\s*$',
            # rand/randc int/byte/shortint/longint [signed|unsigned] name
            r'^\s*(rand|randc)?\s*(int|byte|shortint|longint)\b(?:\s+(signed|unsigned))?\s+(\w+)\s*$',
            # rand/randc enum_type name
            r'^\s*(rand|randc)?\s*(\w+_[et])\s+(\w+)\s*$',
        ]

        # Remove constraint blocks, function blocks from class body before parsing fields
        cleaned_body = self._remove_blocks_for_field_extraction(class_body)

        for line in cleaned_body.split(';'):
            # Remove line comments before any checks/matching
            line = re.sub(r'//.*', '', line).strip()
            if not line:
                continue
            
            # Skip lines that look like constraint internals or other non-field content
            skip_keywords = ['solve ', 'inside ', 'dist ', ' before ', 'foreach', 
                           'unique', 'constraint ', 'function ', 'endfunction',
                           'if ', 'else', 'return', '==', '!=', '<=', '>=', '->']
            if any(kw in line for kw in skip_keywords):
                continue
            
            # Skip lines that are just braces or comments
            if line in ['}', '{', '} else {'] or line.startswith('//'):
                continue

            # Handle comma-separated field declarations: rand bit [signed] [7:0] a, b, c;
            comma_match = re.match(r'^\s*(rand|randc)?\s*(bit|logic)\b\s*(signed)?\s*(?:\[(\d+):0\])?\s+(\w+(?:\s*,\s*\w+)+)\s*$', line)
            if comma_match:
                rand_type, data_type, signed_str, width_str, names_str = comma_match.groups()
                width = int(width_str) + 1 if width_str else 1
                is_signed = signed_str == 'signed'
                field_type = {'rand': FieldType.RAND, 'randc': FieldType.RANDC}.get(rand_type, FieldType.NON_RAND)

                for name in names_str.split(','):
                    name = name.strip()
                    if name and self._is_valid_field_name(name):
                        fields.append(SVField(
                            name=name, width=width, field_type=field_type,
                            original_line=f"{rand_type or ''} {data_type} {'signed ' if is_signed else ''}[{width-1}:0] {name};".strip(),
                            data_type=data_type,
                            is_signed=is_signed
                        ))
                continue

            # Handle comma-separated int declarations: rand int signed a, b, c;
            int_comma_match = re.match(r'^\s*(rand|randc)?\s*(int|byte|shortint|longint)\b\s*(signed|unsigned)?\s+(\w+(?:\s*,\s*\w+)+)\s*$', line)
            if int_comma_match:
                rand_type, data_type, sign_spec, names_str = int_comma_match.groups()
                width = WIDTH_MAP[data_type]
                is_signed = sign_spec != 'unsigned'  # Default is signed for int types
                field_type = {'rand': FieldType.RAND, 'randc': FieldType.RANDC}.get(rand_type, FieldType.NON_RAND)

                for name in names_str.split(','):
                    name = name.strip()
                    if name and self._is_valid_field_name(name):
                        fields.append(SVField(
                            name=name, width=width, field_type=field_type,
                            original_line=f"{rand_type or ''} {data_type} {sign_spec or 'signed'} {name};".strip(),
                            data_type=data_type,
                            is_signed=is_signed
                        ))
                continue

            # Try each standard pattern
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    parsed = self._parse_field_match(match.groups(), line + ';')
                    if parsed and self._is_valid_field_name(parsed.name):
                        fields.append(parsed)
                    break

        return fields

    def _remove_blocks_for_field_extraction(self, class_body: str) -> str:
        """Remove constraint and function blocks from class body for field extraction."""
        result = []
        i = 0
        in_block = False
        brace_depth = 0
        block_keywords = ['constraint', 'function', 'task']
        
        lines = class_body.split('\n')
        for line in lines:
            stripped = line.strip()
            
            # Check if entering a block
            if not in_block:
                if any(re.match(rf'\s*{kw}\s+\w+', stripped) for kw in block_keywords):
                    in_block = True
                    brace_depth = 0
            
            if in_block:
                brace_depth += stripped.count('{') - stripped.count('}')
                if brace_depth <= 0 and ('}' in stripped or 'endfunction' in stripped or 'endtask' in stripped):
                    in_block = False
                    brace_depth = 0
            else:
                result.append(line)
        
        return '\n'.join(result)

    def _is_valid_field_name(self, name: str) -> bool:
        """Check if name is a valid field name (not a keyword or garbage)."""
        if not name:
            return False
        # Must be a valid identifier
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            return False
        # Must not be a reserved word or look like garbage
        invalid_names = {'format', 'before', 'inside', 'solve', 'if', 'else',
                        'constraint', 'function', 'endfunction', 'return', 'this',
                        'begin', 'end'}
        if name in invalid_names:
            return False
        # Must not start with underscore (often indicates internal/garbage)
        if name.startswith('_'):
            return False
        return True

    def _parse_field_match(self, groups: tuple, original: str) -> Optional[SVField]:
        """Parse matched field groups into SVField."""
        if len(groups) < 3:
            return None

        try:
            rand_type, data_type = groups[0], groups[1]

            # Determine field type
            field_type = {
                'rand': FieldType.RAND,
                'randc': FieldType.RANDC
            }.get(rand_type, FieldType.NON_RAND)

            # Parse based on data type
            if data_type in ('bit', 'logic'):
                return self._parse_bit_field(groups, original, field_type, data_type)
            elif data_type in WIDTH_MAP:
                return self._parse_int_field(groups, original, field_type, data_type)
            elif data_type.endswith(('_e', '_t')):
                return self._parse_enum_field(groups, original, field_type, data_type)

        except (IndexError, ValueError, TypeError):
            pass
        return None

    def _parse_bit_field(self, groups: tuple, original: str,
                         field_type: FieldType, data_type: str) -> SVField:
        """Parse bit/logic field declaration."""
        # Groups: (rand|randc, bit|logic, signed?, width?, name, array_size?)
        is_signed = groups[2] == 'signed' if len(groups) > 2 else False
        width = int(groups[3]) + 1 if len(groups) > 3 and groups[3] else 1
        name = groups[4] if len(groups) > 4 else groups[3]
        array_size = int(groups[5]) if len(groups) > 5 and groups[5] else None
        is_dynamic = array_size is None and '[]' in original

        return SVField(
            name=name, width=width, field_type=field_type,
            is_array=array_size is not None or is_dynamic,
            array_size=array_size, is_dynamic=is_dynamic,
            original_line=original, data_type=data_type,
            is_signed=is_signed
        )

    def _parse_int_field(self, groups: tuple, original: str,
                         field_type: FieldType, data_type: str) -> SVField:
        """Parse integer type field declaration.

        Integer types are signed by default in SystemVerilog.
        - 'signed' keyword: explicitly signed (default behavior)
        - 'unsigned' keyword: explicitly unsigned
        - no keyword: signed by default
        """
        sign_spec = groups[2] if len(groups) > 2 else None
        # Default is signed for int types, unless 'unsigned' is specified
        is_signed = sign_spec != 'unsigned'

        return SVField(
            name=groups[3],
            width=WIDTH_MAP[data_type],
            field_type=field_type,
            is_signed=is_signed,
            original_line=original,
            data_type=data_type
        )

    def _parse_enum_field(self, groups: tuple, original: str,
                          field_type: FieldType, data_type: str) -> SVField:
        """Parse enum type field declaration."""
        return SVField(
            name=groups[2] if len(groups) > 2 else groups[1],
            width=32, field_type=field_type,
            is_enum=True, enum_type=data_type,
            original_line=original, data_type=data_type
        )

    def _extract_constraints(self, class_body: str) -> List[SVConstraint]:
        """Extract constraint blocks from class body."""
        constraints = []
        pattern = r'constraint\s+(\w+)\s*\{'

        pos = 0
        while pos < len(class_body):
            match = re.search(pattern, class_body[pos:])
            if not match:
                break

            start_pos = pos + match.start()
            name = match.group(1)
            brace_start = pos + match.end() - 1
            body_start = brace_start + 1

            # Find matching closing brace
            brace_count, i = 1, body_start
            while i < len(class_body) and brace_count > 0:
                if class_body[i] == '{':
                    brace_count += 1
                elif class_body[i] == '}':
                    brace_count -= 1
                i += 1

            if brace_count == 0:
                body = class_body[body_start:i-1].strip()
                constraints.append(SVConstraint(
                    name=name,
                    body=body,
                    original_lines=[class_body[start_pos:i]],
                    constructs=self._analyze_constraint_body(body),
                    warnings=self._check_constraint_warnings(body)
                ))
                pos = i
            else:
                pos = brace_start + 1

        return constraints

    @staticmethod
    def _analyze_constraint_body(body: str) -> List[Tuple[ConstraintType, str]]:
        """Analyze constraint body and identify constructs."""
        constructs = []
        for ctype, pattern in CONSTRAINT_PATTERNS:
            match = re.search(pattern, body)
            if match:
                constructs.append((ctype, match.group(0)))
        return constructs

    @staticmethod
    def _check_constraint_warnings(body: str) -> List[str]:
        """Check for constructs that may need manual review."""
        warnings = []
        checks = [
            (r'\w+\[\d+:\d+\]', "Bit slicing detected - requires manual conversion to shifts/masks"),
            (r'<->', "Bidirectional implication detected - needs two vsc.implies() calls"),
            (r'\$urandom', "$urandom detected - use Python random module in post_randomize"),
            (r'\$\w+', "System function detected - may need manual handling"),
        ]
        for pattern, msg in checks:
            if re.search(pattern, body):
                warnings.append(msg)
        return warnings

    @staticmethod
    def _extract_function(class_body: str, func_name: str) -> Optional[str]:
        """Extract function body."""
        pattern = rf'function\s+(?:void\s+)?{func_name}\s*\(\s*\)\s*;(.*?)endfunction'
        match = re.search(pattern, class_body, re.DOTALL)
        return match.group(1).strip() if match else None

    @staticmethod
    def _parse_number(num_str: str) -> int:
        """Parse SystemVerilog number format."""
        num_str = re.sub(r"^\d+'", '', num_str.strip())

        base_map = {
            'h': 16, 'H': 16,
            'b': 2, 'B': 2,
            'o': 8, 'O': 8,
            'd': 10, 'D': 10
        }

        if num_str and num_str[0] in base_map:
            return int(num_str[1:], base_map[num_str[0]])
        return int(num_str)


# =============================================================================
# PYVSC CODE GENERATOR
# =============================================================================

class PyVSCGenerator:
    """Generates pyvsc code from parsed SV structures."""

    INDENT = "    "

    def __init__(self, verbose: bool = False):
        self.verbose = verbose  # When True, include original SV code and metrics in output
        self.warnings: List[str] = []
        self.manual_review_items: List[str] = []
        self.mapping_notes: List[str] = []
        self.statistics: Dict[str, int] = {}

    def generate(self, sv_classes: List[SVClass]) -> TranslationResult:
        """Generate pyvsc code for all classes."""
        self._reset_state()
        
        # Analyze source SV code for metrics
        self._analyze_sv_source(sv_classes)

        # Build enum value -> enum class name map for expression translation
        for sv_class in sv_classes:
            for enum in sv_class.enums:
                class_name = self._to_python_class_name(enum.name)
                self.enum_class_names.add(class_name)
                for value_name, _ in enum.values:
                    if value_name in self.enum_value_map and self.enum_value_map[value_name] != class_name:
                        self._add_warning(
                            f"Enum value '{value_name}' appears in multiple enums; using '{self.enum_value_map[value_name]}'"
                        )
                        continue
                    self.enum_value_map[value_name] = class_name
        
        code_parts = [
            self._generate_header(),
            self._generate_imports(),
        ]

        # Generate unique enums
        seen_enums = set()
        for sv_class in sv_classes:
            for enum in sv_class.enums:
                if enum.name not in seen_enums:
                    seen_enums.add(enum.name)
                    code_parts.append(self._generate_enum(enum))
                    self.statistics['enums'] += 1

        # Collect all defined class names and parent classes
        defined_classes = {sv_class.name for sv_class in sv_classes}
        parent_classes = set()
        for sv_class in sv_classes:
            if sv_class.parent_class and sv_class.parent_class not in defined_classes:
                parent_classes.add(sv_class.parent_class)
        
        # Generate stub base classes for undefined parent classes
        if parent_classes:
            stub_code = self._generate_base_class_stubs(parent_classes)
            if stub_code:
                code_parts.append(stub_code)

        # Generate classes
        for sv_class in sv_classes:
            class_code = self._generate_class(sv_class)
            
            # Validate the generated code
            validation_issues = self._validate_generated_code(sv_class, class_code)
            for issue in validation_issues:
                self._add_warning(issue)
            
            code_parts.append(class_code)
            self.statistics['classes'] += 1

        code_parts.append(self._generate_usage_example(sv_classes))
        
        final_code = '\n\n'.join(filter(None, code_parts))
        
        # Analyze output Python code for metrics
        self._analyze_py_output(final_code)
        
        # Final validation - check for SV syntax leaks
        leak_issues = self._check_sv_syntax_leaks(final_code)
        for issue in leak_issues:
            self._add_warning(issue)

        return TranslationResult(
            pyvsc_code=final_code,
            warnings=self.warnings,
            manual_review_items=self.manual_review_items,
            mapping_notes=self.mapping_notes,
            statistics=self.statistics
        )

    def _generate_base_class_stubs(self, parent_classes: Set[str]) -> str:
        """Generate stub classes for undefined parent classes (like UVM base classes)."""
        lines = [
            "# =============================================================================",
            "# BASE CLASS STUBS (from UVM or other libraries)",
            "# Replace these with actual implementations or imports as needed",
            "# =============================================================================",
            "",
        ]
        
        for parent in sorted(parent_classes):
            py_name = self._to_python_class_name(parent)
            lines.extend([
                "@vsc.randobj",
                f"class {py_name}:",
                f'{self.INDENT}"""',
                f'{self.INDENT}Stub for {parent} base class.',
                f'{self.INDENT}Replace with actual implementation or import from your UVM library.',
                f'{self.INDENT}"""',
                f"{self.INDENT}def __init__(self):",
                f"{self.INDENT}{self.INDENT}pass  # TODO: Add base class fields if needed",
                "",
            ])
            self._add_review_item(f"Base class '{parent}' stub generated - replace with actual implementation")
            self.mapping_notes.append(f"Generated stub for base class '{parent}' -> '{py_name}'")
        
        return '\n'.join(lines)

    def _validate_generated_code(self, sv_class: SVClass, generated_code: str) -> List[str]:
        """Validate that generated code contains all expected elements."""
        issues = []
        
        # Extract all variable names from SV class fields
        sv_field_names = {field.name for field in sv_class.fields}
        
        # Check if all field variables appear in __init__
        for var in sv_field_names:
            if f'self.{var} = vsc.' not in generated_code:
                issues.append(f"Field '{var}' may be missing from __init__")
        
        # Check constraint names are present
        for constraint in sv_class.constraints:
            if f'def {constraint.name}(self):' not in generated_code:
                issues.append(f"Constraint '{constraint.name}' missing from generated code")
            
            # Validate constraint content
            constraint_issues = self._validate_constraint_translation(
                constraint, generated_code, sv_field_names
            )
            issues.extend(constraint_issues)
        
        return issues

    def _validate_constraint_translation(self, constraint: SVConstraint, 
                                          generated_code: str, field_names: Set[str]) -> List[str]:
        """Validate that a constraint was fully translated."""
        issues = []
        body = constraint.body
        
        # Count solve_order statements in original
        solve_matches = re.findall(r'solve\s+(\w+)\s+before\s+(\w+)', body)
        expected_solves = len(solve_matches)
        actual_solves = generated_code.count('vsc.solve_order(')
        
        if actual_solves < expected_solves:
            missing = expected_solves - actual_solves
            issues.append(f"Constraint '{constraint.name}': {missing} solve_order statement(s) may be missing")
            # List which ones might be missing
            for first, second in solve_matches:
                if f'vsc.solve_order(self.{first}' not in generated_code:
                    issues.append(f"  - Missing: solve {first} before {second}")
        
        # Count inside constraints in original
        inside_matches = re.findall(r'(\w+)\s+inside\s*\{([^}]+)\}', body)
        for var, values in inside_matches:
            # Check if this inside was translated (using 'in vsc.rangelist')
            if f'self.{var} in vsc.rangelist(' not in generated_code:
                # Could be in an if block, check more carefully
                pattern = f'self\\.{var}\\s+in\\s+vsc\\.rangelist'
                if not re.search(pattern, generated_code):
                    issues.append(f"Constraint '{constraint.name}': 'inside' for '{var}' may be missing")
        
        # Count implications in original
        impl_count = body.count('->')
        actual_impl = generated_code.count('vsc.implies(')
        # Note: implications inside if/else are converted to if_then, so this is just informational
        
        # Check all referenced variables from constraint body appear in output
        # Extract identifiers from constraint body
        identifiers = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', body))
        sv_keywords = {'if', 'else', 'inside', 'dist', 'solve', 'before', 
                      'foreach', 'unique', 'soft', 'constraint', 'rand',
                      'randc', 'bit', 'logic', 'int', 'byte', 'size'}
        
        for ident in identifiers:
            if ident in sv_keywords:
                continue
            if ident in field_names:
                # This is a field - check it appears with self. prefix in constraint method
                # Find the constraint method section
                constraint_start = generated_code.find(f'def {constraint.name}(self):')
                if constraint_start != -1:
                    # Find the next method or end
                    next_def = generated_code.find('\n    def ', constraint_start + 1)
                    if next_def == -1:
                        next_def = generated_code.find('\n# ===', constraint_start + 1)
                    if next_def == -1:
                        next_def = len(generated_code)
                    
                    constraint_section = generated_code[constraint_start:next_def]
                    
                    # Check if variable appears (excluding docstring)
                    docstring_end = constraint_section.find('"""', constraint_section.find('"""') + 3)
                    if docstring_end != -1:
                        code_section = constraint_section[docstring_end + 3:]
                        if f'self.{ident}' not in code_section:
                            # Check if it's in a with statement or expression
                            if ident not in code_section:
                                issues.append(f"Constraint '{constraint.name}': variable '{ident}' may be missing from translated code")
        
        return issues

    def _check_sv_syntax_leaks(self, code: str) -> List[str]:
        """Check for SystemVerilog syntax that leaked into Python code."""
        issues = []
        
        # Check each line (skip comments and docstrings)
        in_docstring = False
        docstring_delimiter = None
        
        for line_num, line in enumerate(code.split('\n'), 1):
            stripped = line.strip()
            
            # Track docstrings properly
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_delimiter = stripped[:3]
                    if stripped.count(docstring_delimiter) == 1:
                        in_docstring = True
                    continue
            else:
                if docstring_delimiter in stripped:
                    in_docstring = False
                    docstring_delimiter = None
                continue
            
            # Skip comment lines
            if stripped.startswith('#'):
                continue
            
            # Remove inline comments before checking
            code_part = line.split('#')[0] if '#' in line else line
            code_part = code_part.strip()
            
            # Skip empty lines
            if not code_part:
                continue
            
            # Check for SV patterns only in code part
            if 'inside {' in code_part and 'vsc.rangelist' not in code_part:
                issues.append(f"Line {line_num}: SV 'inside' syntax found in code")
            elif 'dist {' in code_part and 'vsc.dist' not in code_part:
                issues.append(f"Line {line_num}: SV 'dist' syntax found in code")
            elif re.search(r"\d+'[hHbBdD]", code_part):
                issues.append(f"Line {line_num}: SV number format found in code")
            elif ' && ' in code_part:
                issues.append(f"Line {line_num}: SV '&&' operator - should be 'and'")
            elif ' || ' in code_part:
                issues.append(f"Line {line_num}: SV '||' operator - should be 'or'")
        
        return issues

    def _reset_state(self):
        """Reset generator state for new translation."""
        self._warnings_set = set()
        self._review_set = set()
        self.warnings = []
        self.manual_review_items = []
        self.mapping_notes = []
        self.statistics = {'classes': 0, 'fields': 0, 'constraints': 0, 'enums': 0}
        self.enum_value_map = {}
        self.enum_class_names = set()
        
        # Detailed conversion metrics
        self.metrics = {
            # Source metrics (detected in SV)
            'sv_lines': 0,
            'sv_variables': set(),
            'sv_conditionals': 0,
            'sv_logical_and': 0,
            'sv_logical_or': 0,
            'sv_logical_not': 0,
            'sv_inside': 0,
            'sv_implies': 0,
            'sv_dist': 0,
            'sv_solve_order': 0,
            'sv_foreach': 0,
            'sv_unique': 0,
            'sv_soft': 0,
            'sv_bit_slices': 0,
            'sv_number_formats': 0,
            
            # Output metrics (generated in Python)
            'py_lines': 0,
            'py_variables': set(),
            'py_if_then': 0,
            'py_else_if': 0,
            'py_else_then': 0,
            'py_rangelist': 0,
            'py_implies': 0,
            'py_dist': 0,
            'py_solve_order': 0,
            'py_foreach': 0,
            'py_unique': 0,
            'py_soft': 0,
        }

    def _analyze_sv_source(self, sv_classes: List[SVClass]):
        """Analyze source SV code to collect metrics."""
        for sv_class in sv_classes:
            # Count source lines
            self.metrics['sv_lines'] += sv_class.original_code.count('\n') + 1
            
            # Collect variables
            for field in sv_class.fields:
                self.metrics['sv_variables'].add(field.name)
            
            # Analyze constraints
            for constraint in sv_class.constraints:
                body = constraint.body
                
                # Count conditionals
                self.metrics['sv_conditionals'] += len(re.findall(r'\bif\s*\(', body))
                self.metrics['sv_conditionals'] += len(re.findall(r'\belse\s+if\s*\(', body))
                
                # Count logical operators
                self.metrics['sv_logical_and'] += body.count('&&')
                self.metrics['sv_logical_or'] += body.count('||')
                self.metrics['sv_logical_not'] += len(re.findall(r'!\s*\(', body))
                self.metrics['sv_logical_not'] += len(re.findall(r'!\s*\w', body))
                
                # Count constraint constructs
                self.metrics['sv_inside'] += len(re.findall(r'\binside\s*\{', body))
                self.metrics['sv_implies'] += body.count('->')
                self.metrics['sv_dist'] += len(re.findall(r'\bdist\s*\{', body))
                self.metrics['sv_solve_order'] += len(re.findall(r'\bsolve\s+\w+\s+before\b', body))
                self.metrics['sv_foreach'] += len(re.findall(r'\bforeach\s*\(', body))
                self.metrics['sv_unique'] += len(re.findall(r'\bunique\s*\{', body))
                self.metrics['sv_soft'] += len(re.findall(r'\bsoft\s+', body))
                
                # Count bit slices and number formats
                self.metrics['sv_bit_slices'] += len(re.findall(r'\w+\[\d+:\d+\]', body))
                self.metrics['sv_number_formats'] += len(re.findall(r"\d+'[hHbBdDoO]", body))
                
                # Collect variables used in constraints
                identifiers = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', body))
                sv_keywords = {'if', 'else', 'inside', 'dist', 'solve', 'before', 
                              'foreach', 'unique', 'soft', 'constraint', 'rand',
                              'randc', 'bit', 'logic', 'int', 'byte', 'size'}
                for ident in identifiers:
                    if ident not in sv_keywords:
                        self.metrics['sv_variables'].add(ident)

    def _analyze_py_output(self, code: str):
        """Analyze generated Python code to collect metrics."""
        self.metrics['py_lines'] = code.count('\n') + 1
        
        # Count Python constructs
        self.metrics['py_if_then'] = code.count('vsc.if_then(')
        self.metrics['py_else_if'] = code.count('vsc.else_if(')
        self.metrics['py_else_then'] = code.count('vsc.else_then')
        self.metrics['py_rangelist'] = code.count('vsc.rangelist(')
        self.metrics['py_implies'] = code.count('vsc.implies(')
        self.metrics['py_dist'] = code.count('vsc.dist(')
        self.metrics['py_solve_order'] = code.count('vsc.solve_order(')
        self.metrics['py_foreach'] = code.count('vsc.foreach(')
        self.metrics['py_unique'] = code.count('vsc.unique(')
        self.metrics['py_soft'] = code.count('vsc.soft(')
        
        # Count logical operators converted to Python
        self.metrics['py_logical_and'] = len(re.findall(r'\band\b', code))
        self.metrics['py_logical_or'] = len(re.findall(r'\bor\b', code))
        self.metrics['py_logical_not'] = len(re.findall(r'\bnot\b', code))
        
        # Collect variables (self.var patterns)
        self.metrics['py_variables'] = set(re.findall(r'self\.([a-zA-Z_][a-zA-Z0-9_]*)', code))

    def _add_warning(self, warning: str):
        """Add a warning if not already present."""
        if warning not in self._warnings_set:
            self._warnings_set.add(warning)
            self.warnings.append(warning)

    def _add_review_item(self, item: str):
        """Add a manual review item if not already present."""
        if item not in self._review_set:
            self._review_set.add(item)
            self.manual_review_items.append(item)

    @staticmethod
    def _generate_header() -> str:
        """Generate file header."""
        return '''#!/usr/bin/env python3
"""
Auto-generated pyvsc translation from SystemVerilog

IMPORTANT: This is a SUGGESTED translation that requires manual review.
Please verify:
1. All constraint semantics are preserved
2. Data type mappings are correct
3. Distribution weights match original intent
4. Solve order effects are equivalent

Generated by: SV-to-pyvsc Translation Assistant
"""'''

    @staticmethod
    def _generate_imports() -> str:
        """Generate import statements."""
        return '''import vsc
from enum import IntEnum
import random
from typing import Optional'''

    def _generate_enum(self, enum: SVEnum) -> str:
        """Generate Python IntEnum from SV enum."""
        class_name = self._to_python_class_name(enum.name)
        lines = [
            f"class {class_name}(IntEnum):",
            f'{self.INDENT}"""Translated from SV enum: {enum.name}"""'
        ]

        current_val = 0
        for name, val in enum.values:
            if val is not None:
                current_val = val
            lines.append(f"{self.INDENT}{name} = {current_val}")
            current_val += 1

        self.mapping_notes.append(f"Enum '{enum.name}' -> IntEnum '{class_name}'")
        return '\n'.join(lines)

    def _generate_class(self, sv_class: SVClass) -> str:
        """Generate pyvsc class from SV class."""
        class_name = self._to_python_class_name(sv_class.name)
        parent = f"({self._to_python_class_name(sv_class.parent_class)})" if sv_class.parent_class else ""

        if sv_class.parent_class:
            self.mapping_notes.append(f"Class '{sv_class.name}' extends '{sv_class.parent_class}'")

        lines = [
            "@vsc.randobj",
            f"class {class_name}{parent}:",
            f'{self.INDENT}"""Translated from SV class: {sv_class.name}"""',
            "",
            f"{self.INDENT}def __init__(self):",
        ]

        if sv_class.parent_class:
            lines.append(f"{self.INDENT}{self.INDENT}super().__init__()")

        # Generate fields
        if sv_class.fields:
            for fld in sv_class.fields:
                lines.append(f"{self.INDENT}{self.INDENT}{self._generate_field(fld)}")
                self.statistics['fields'] += 1
        else:
            lines.append(f"{self.INDENT}{self.INDENT}pass  # No fields found")

        # Separate simple range constraints from other constraints
        range_constraints = []
        other_constraints = []
        for constraint in sv_class.constraints:
            range_line = self._extract_simple_range_constraint(constraint)
            if range_line:
                range_constraints.append(range_line)
            else:
                other_constraints.append(constraint)

        # Generate grouped parameter_range constraint if there are range constraints
        if range_constraints:
            lines.append("")
            lines.append(f"{self.INDENT}@vsc.constraint")
            lines.append(f"{self.INDENT}def parameter_range(self):")
            for range_line in range_constraints:
                lines.append(f"{self.INDENT}{self.INDENT}{range_line}")
            self.statistics['constraints'] += 1

        # Generate other constraints
        for constraint in other_constraints:
            lines.append("")
            lines.extend(self._generate_constraint(constraint))
            self.statistics['constraints'] += 1
            for warning in constraint.warnings:
                self._add_warning(warning)

        # Generate pre/post randomize
        if sv_class.pre_randomize:
            lines.append("")
            lines.extend(self._generate_hook('pre_randomize', sv_class.pre_randomize))

        if sv_class.post_randomize:
            lines.append("")
            lines.extend(self._generate_hook('post_randomize', sv_class.post_randomize))

        return '\n'.join(lines)

    def _extract_simple_range_constraint(self, constraint: SVConstraint) -> Optional[str]:
        """
        Check if constraint is a simple range constraint (var >= min && var <= max).
        Returns the translated rangelist line if it is, None otherwise.
        """
        body = constraint.body.strip()
        # Remove trailing semicolon
        body = body.rstrip(';').strip()

        # Check for parenthesized form
        while body.startswith('(') and body.endswith(')'):
            inner = body[1:-1]
            depth = 0
            valid = True
            for ch in inner:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth < 0:
                        valid = False
                        break
            if valid and depth == 0:
                body = inner.strip()
            else:
                break

        # Pattern: var >= min && var <= max  OR  var >= min & var <= max
        pattern1 = r'^(\w+)\s*>=\s*(-?\d+)\s*(?:&&|&)\s*\1\s*<=\s*(-?\d+)$'
        # Pattern: var <= max && var >= min  OR  var <= max & var >= min
        pattern2 = r'^(\w+)\s*<=\s*(-?\d+)\s*(?:&&|&)\s*\1\s*>=\s*(-?\d+)$'

        match = re.match(pattern1, body)
        if match:
            var_name, min_val, max_val = match.groups()
            return f"self.{var_name} in vsc.rangelist(vsc.rng({min_val}, {max_val}))"

        match = re.match(pattern2, body)
        if match:
            var_name, max_val, min_val = match.groups()
            return f"self.{var_name} in vsc.rangelist(vsc.rng({min_val}, {max_val}))"

        return None

    def _generate_field(self, fld: SVField) -> str:
        """Generate pyvsc field declaration."""
        # Only include inline comments with original SV code when verbose mode is enabled
        comment = f"  # {fld.original_line.strip()}" if self.verbose and fld.original_line else ""

        if fld.is_enum:
            enum_class = self._to_python_class_name(fld.enum_type or "UnknownEnum")
            prefix = "vsc.rand_enum_t" if fld.field_type == FieldType.RAND else "vsc.enum_t"
            return f"self.{fld.name} = {prefix}({enum_class}){comment}"

        if fld.is_array:
            inner = self._get_inner_type(fld)
            prefix = "vsc.rand_list_t" if fld.field_type == FieldType.RAND else "vsc.list_t"
            size_arg = f", sz={fld.array_size}" if fld.array_size else ""
            return f"self.{fld.name} = {prefix}({inner}{size_arg}){comment}"

        return f"self.{fld.name} = {self._get_pyvsc_type(fld)}{comment}"

    def _get_pyvsc_type(self, fld: SVField) -> str:
        """Get pyvsc type string for a field.

        Type mapping follows PyVSC conventions:
        - Unsigned bit/logic vectors -> bit_t(N)
        - Signed bit/logic vectors -> int_t(N) (PyVSC doesn't support signed bit_t)
        - Standard integer types -> use standard width types (int8_t, int16_t, etc.)
        - randc -> randc_bit_t(N)
        """
        if fld.field_type == FieldType.RANDC:
            # randc only supports bit_t in PyVSC
            return f"vsc.randc_bit_t({fld.width})"

        prefix = "vsc.rand_" if fld.field_type == FieldType.RAND else "vsc."

        # Handle signed bit/logic types - map to int_t (PyVSC doesn't support signed bit_t)
        if fld.data_type in ('bit', 'logic') and fld.is_signed:
            return f"{prefix}int_t({fld.width})"

        # Handle unsigned bit/logic types
        if fld.data_type in ('bit', 'logic'):
            return f"{prefix}bit_t({fld.width})"

        # Handle standard integer types with proper signed/unsigned mapping
        # byte (8-bit), shortint (16-bit), int (32-bit), longint (64-bit)
        if fld.data_type == 'byte':
            return f"{prefix}int8_t()" if fld.is_signed else f"{prefix}uint8_t()"
        elif fld.data_type == 'shortint':
            return f"{prefix}int16_t()" if fld.is_signed else f"{prefix}uint16_t()"
        elif fld.data_type == 'int':
            return f"{prefix}int32_t()" if fld.is_signed else f"{prefix}uint32_t()"
        elif fld.data_type == 'longint':
            return f"{prefix}int64_t()" if fld.is_signed else f"{prefix}uint64_t()"

        # Default fallback
        return f"{prefix}bit_t({fld.width})"

    @staticmethod
    def _get_inner_type(fld: SVField) -> str:
        """Get inner type for array elements (non-random types)."""
        # Signed bit/logic -> int_t (PyVSC doesn't support signed bit_t)
        if fld.data_type in ('bit', 'logic') and fld.is_signed:
            return f"vsc.int_t({fld.width})"

        # Unsigned bit/logic -> bit_t
        if fld.data_type in ('bit', 'logic'):
            return f"vsc.bit_t({fld.width})"

        # Standard integer types with proper signed/unsigned mapping
        if fld.data_type == 'byte':
            return "vsc.int8_t()" if fld.is_signed else "vsc.uint8_t()"
        elif fld.data_type == 'shortint':
            return "vsc.int16_t()" if fld.is_signed else "vsc.uint16_t()"
        elif fld.data_type == 'int':
            return "vsc.int32_t()" if fld.is_signed else "vsc.uint32_t()"
        elif fld.data_type == 'longint':
            return "vsc.int64_t()" if fld.is_signed else "vsc.uint64_t()"

        # Default fallback
        return f"vsc.bit_t({fld.width})"

    def _generate_constraint(self, constraint: SVConstraint) -> List[str]:
        """Generate pyvsc constraint from SV constraint."""
        # Calculate per-constraint metrics from source
        metrics = self._calculate_constraint_metrics(constraint.body)

        # First translate the body to get output
        body_lines = self._translate_constraint_body(constraint.body)
        body_code = '\n'.join(body_lines)

        # Calculate output metrics
        output_metrics = self._calculate_output_metrics(body_code, metrics['variable_names'])

        lines = [
            f"{self.INDENT}@vsc.constraint",
            f"{self.INDENT}def {constraint.name}(self):",
        ]

        # Only include docstring with original SV code and metrics when verbose mode is enabled
        if self.verbose:
            lines.append(f'{self.INDENT}{self.INDENT}"""')
            lines.append(f'{self.INDENT}{self.INDENT}Original SV constraint:')

            for orig_line in constraint.body.split('\n'):
                if orig_line.strip():
                    lines.append(f'{self.INDENT}{self.INDENT}{orig_line.strip()}')

            # Add metrics section to docstring
            lines.append(f'{self.INDENT}{self.INDENT}')
            lines.append(f'{self.INDENT}{self.INDENT}--- Constraint Metrics ---')
            lines.append(f'{self.INDENT}{self.INDENT}Lines: {metrics["lines"]} | Variables: {metrics["variables"]}')

            # Conditionals with output comparison
            if metrics['conditionals'] > 0 or metrics['else_count'] > 0:
                cond_str = f'Conditionals: {metrics["conditionals"]} (if: {metrics["if_count"]}, else-if: {metrics["else_if_count"]}, else: {metrics["else_count"]})'
                out_cond = f' -> Output: if_then: {output_metrics["if_then"]}, else_if: {output_metrics["else_if"]}, else_then: {output_metrics["else_then"]}'
                lines.append(f'{self.INDENT}{self.INDENT}{cond_str}{out_cond}')

            # Logical operators
            if metrics['logical_total'] > 0:
                lines.append(f'{self.INDENT}{self.INDENT}Logical Ops: {metrics["logical_total"]} (&&: {metrics["and_count"]}, ||: {metrics["or_count"]}, !: {metrics["not_count"]}) -> Output: and: {output_metrics["and"]}, or: {output_metrics["or"]}, not: {output_metrics["not"]}')

            # Constraint constructs with output comparison
            constructs = []
            if metrics['inside_count'] > 0:
                constructs.append(f'inside: {metrics["inside_count"]}->{output_metrics["rangelist"]}')
            if metrics['implies_count'] > 0:
                constructs.append(f'implies: {metrics["implies_count"]}->{output_metrics["implies"]}')
            if metrics['dist_count'] > 0:
                constructs.append(f'dist: {metrics["dist_count"]}->{output_metrics["dist"]}')
            if metrics['solve_count'] > 0:
                constructs.append(f'solve: {metrics["solve_count"]}->{output_metrics["solve_order"]}')
            if metrics['foreach_count'] > 0:
                constructs.append(f'foreach: {metrics["foreach_count"]}->{output_metrics["foreach"]}')
            if metrics['unique_count'] > 0:
                constructs.append(f'unique: {metrics["unique_count"]}->{output_metrics["unique"]}')
            if metrics['soft_count'] > 0:
                constructs.append(f'soft: {metrics["soft_count"]}->{output_metrics["soft"]}')

            if constructs:
                lines.append(f'{self.INDENT}{self.INDENT}Constructs (SV->Py): {", ".join(constructs)}')

            # Special items
            specials = []
            if metrics['bit_slices'] > 0:
                specials.append(f'bit_slices: {metrics["bit_slices"]}')
            if metrics['number_formats'] > 0:
                specials.append(f'number_formats: {metrics["number_formats"]}')

            if specials:
                lines.append(f'{self.INDENT}{self.INDENT}Special: {", ".join(specials)}')

            # Variable validation
            if output_metrics['missing_vars']:
                lines.append(f'{self.INDENT}{self.INDENT}MISSING VARS: {", ".join(sorted(output_metrics["missing_vars"]))}')

            if output_metrics['name_mismatches']:
                lines.append(f'{self.INDENT}{self.INDENT}NAME CHANGES: {output_metrics["name_mismatches"]}')

            lines.append(f'{self.INDENT}{self.INDENT}"""')

        # Always track warnings internally regardless of verbose mode
        if output_metrics['missing_vars']:
            self._add_warning(f"Constraint '{constraint.name}': Variables missing in output: {', '.join(sorted(output_metrics['missing_vars']))}")

        if output_metrics['name_mismatches']:
            self._add_warning(f"Constraint '{constraint.name}': Variable names may have changed")

        if body_lines:
            for line in body_lines:
                lines.append(f"{self.INDENT}{self.INDENT}{line}")
        else:
            lines.append(f"{self.INDENT}{self.INDENT}pass  # TODO: Manual translation required")
            self._add_review_item(f"Constraint '{constraint.name}' requires manual translation")

        return lines

    def _calculate_output_metrics(self, body_code: str, sv_var_names: Set[str]) -> Dict:
        """Calculate metrics from generated Python code and validate variables."""
        metrics = {
            'if_then': body_code.count('vsc.if_then('),
            'else_if': body_code.count('vsc.else_if('),
            'else_then': body_code.count('vsc.else_then'),
            'rangelist': body_code.count('vsc.rangelist('),
            'implies': body_code.count('vsc.implies('),
            'dist': body_code.count('vsc.dist('),
            'solve_order': body_code.count('vsc.solve_order('),
            'foreach': body_code.count('vsc.foreach('),
            'unique': body_code.count('vsc.unique('),
            'soft': body_code.count('vsc.soft('),
            'and': len(re.findall(r'\band\b', body_code)),
            'or': len(re.findall(r'\bor\b', body_code)),
            'not': len(re.findall(r'\bnot\b', body_code)),
            'missing_vars': set(),
            'name_mismatches': [],
        }
        
        # Extract variables from output (self.var patterns)
        output_vars = set(re.findall(r'self\.([a-zA-Z_][a-zA-Z0-9_]*)', body_code))
        
        # Also extract loop index variables (they don't have self. prefix)
        loop_vars = set(re.findall(r'as\s+(\w+):', body_code))
        
        # Check for missing variables
        for sv_var in sv_var_names:
            # Skip SV number literal patterns (hXX, bXX, dXX)
            if re.match(r'^[hbdHBD][0-9a-fA-F]+$', sv_var):
                continue
            
            # Skip common loop index variables
            if sv_var in {'i', 'j', 'k', 'idx', 'index'}:
                continue
                
            # Skip if it's used as loop variable
            if sv_var in loop_vars:
                continue
            
            # Skip enum-like values (ALL_CAPS)
            if sv_var.isupper():
                continue
            
            # Skip if it's in output
            if sv_var in output_vars:
                continue
                
            # Check if it might be a modified name (underscore issues)
            found = False
            for out_var in output_vars:
                # Check if names are similar (ignoring underscores near numbers)
                sv_normalized = re.sub(r'_(\d)', r'\1', sv_var)
                out_normalized = re.sub(r'_(\d)', r'\1', out_var)
                if sv_normalized == out_normalized and sv_var != out_var:
                    metrics['name_mismatches'].append(f'{sv_var}->{out_var}')
                    found = True
                    break
            
            if not found:
                # Only add to missing if it looks like a real variable (not a literal)
                if not re.match(r'^\d', sv_var):  # Doesn't start with digit
                    metrics['missing_vars'].add(sv_var)
        
        return metrics

    def _calculate_constraint_metrics(self, body: str) -> Dict[str, int]:
        """Calculate metrics for a single constraint body."""
        metrics = {
            'lines': len([l for l in body.split('\n') if l.strip()]),
            'variables': 0,
            'variable_names': set(),  # Track actual variable names
            'conditionals': 0,
            'if_count': 0,
            'else_if_count': 0,
            'else_count': 0,  # Track else blocks
            'and_count': 0,
            'or_count': 0,
            'not_count': 0,
            'logical_total': 0,
            'inside_count': 0,
            'implies_count': 0,
            'dist_count': 0,
            'solve_count': 0,
            'foreach_count': 0,
            'unique_count': 0,
            'soft_count': 0,
            'bit_slices': 0,
            'number_formats': 0,
        }
        
        # Count conditionals
        metrics['if_count'] = len(re.findall(r'\bif\s*\(', body))
        metrics['else_if_count'] = len(re.findall(r'\belse\s+if\s*\(', body))
        # Count else blocks - both braced and inline
        else_with_brace = len(re.findall(r'\}\s*else\s*\{', body))
        else_inline = len(re.findall(r';\s*else\b(?!\s*if)', body))  # ; else (not else if)
        else_newline = len(re.findall(r'\n\s*else\b(?!\s*if)', body))  # newline else
        metrics['else_count'] = else_with_brace + else_inline + else_newline
        metrics['conditionals'] = metrics['if_count'] + metrics['else_if_count']
        
        # Count logical operators
        metrics['and_count'] = body.count('&&')
        metrics['or_count'] = body.count('||')
        metrics['not_count'] = len(re.findall(r'!\s*[\(\w]', body))
        metrics['logical_total'] = metrics['and_count'] + metrics['or_count'] + metrics['not_count']
        
        # Count constraint constructs
        metrics['inside_count'] = len(re.findall(r'\binside\s*\{', body))
        metrics['implies_count'] = body.count('->')
        metrics['dist_count'] = len(re.findall(r'\bdist\s*\{', body))
        metrics['solve_count'] = len(re.findall(r'\bsolve\s+\w+\s+before\b', body))
        metrics['foreach_count'] = len(re.findall(r'\bforeach\s*\(', body))
        metrics['unique_count'] = len(re.findall(r'\bunique\s*\{', body))
        metrics['soft_count'] = len(re.findall(r'\bsoft\s+', body))
        
        # Count special items
        metrics['bit_slices'] = len(re.findall(r'\w+\[\d+:\d+\]', body))
        metrics['number_formats'] = len(re.findall(r"\d+'[hHbBdDoO]", body))
        
        # Count variables (unique identifiers excluding keywords)
        sv_keywords = {'if', 'else', 'inside', 'dist', 'solve', 'before', 
                      'foreach', 'unique', 'soft', 'constraint', 'rand',
                      'randc', 'bit', 'logic', 'int', 'byte', 'size', 'this'}
        identifiers = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', body))
        var_names = identifiers - sv_keywords
        metrics['variables'] = len(var_names)
        metrics['variable_names'] = var_names
        
        return metrics

    def _translate_constraint_body(self, body: str) -> List[str]:
        """Translate constraint body to pyvsc."""
        solve_order_lines = []
        other_lines = []

        for stmt in self._split_statements(body):
            if stmt.strip():
                translated = self._translate_statement(stmt.strip())
                for line in translated:
                    if 'vsc.solve_order(' in line:
                        solve_order_lines.append(line)
                    else:
                        other_lines.append(line)

        # solve_order statements must come first, before conditionals
        return solve_order_lines + other_lines

    @staticmethod
    def _split_statements(body: str) -> List[str]:
        """Split constraint body into individual statements."""
        statements = []
        current = ""
        brace_depth = 0
        paren_depth = 0
        begin_depth = 0
        i = 0

        while i < len(body):
            char = body[i]

            # Check for 'begin' keyword
            if body[i:i+5] == 'begin' and (i == 0 or not body[i-1].isalnum()):
                if i + 5 >= len(body) or not body[i+5].isalnum():
                    begin_depth += 1
                    current += body[i:i+5]
                    i += 5
                    continue

            # Check for 'end' keyword (but not endclass, endfunction, etc.)
            if body[i:i+3] == 'end' and (i == 0 or not body[i-1].isalnum()):
                if i + 3 >= len(body) or not body[i+3].isalnum():
                    begin_depth -= 1
                    current += body[i:i+3]
                    i += 3
                    # If we closed the outermost begin/end, check for else
                    if begin_depth == 0 and brace_depth == 0 and paren_depth == 0:
                        remaining = body[i:].lstrip()
                        if not remaining.startswith('else'):
                            if current.strip():
                                statements.append(current.strip())
                            current = ""
                    continue

            if char == '{':
                brace_depth += 1
                current += char
            elif char == '}':
                brace_depth -= 1
                current += char

                # If we just closed the outermost brace, this might be end of a block statement
                if brace_depth == 0 and paren_depth == 0 and begin_depth == 0:
                    # Check if this is an if/else block by looking for else after
                    # Skip whitespace and semicolons to find else
                    remaining = body[i+1:].lstrip()
                    if remaining.startswith(';'):
                        remaining = remaining[1:].lstrip()
                    if not remaining.startswith('else'):
                        # End of block statement - save it
                        if current.strip():
                            statements.append(current.strip())
                        current = ""
            elif char == '(':
                paren_depth += 1
                current += char
            elif char == ')':
                paren_depth -= 1
                current += char
            elif char == ';' and brace_depth == 0 and paren_depth == 0 and begin_depth == 0:
                # Check if next non-whitespace is else or else if
                remaining = body[i+1:].lstrip()
                if remaining.startswith('else'):
                    # Include the semicolon and keep collecting for the else/else if
                    current += char
                else:
                    # Normal statement end - include semicolon
                    current += char
                    if current.strip():
                        statements.append(current.strip())
                    current = ""
            else:
                current += char

            i += 1

        # Don't forget any remaining content
        if current.strip():
            statements.append(current.strip())

        return statements

    def _translate_statement(self, stmt: str) -> List[str]:
        """Translate a single constraint statement."""
        if not stmt:
            return []

        # Remove trailing semicolon for Python
        stmt = stmt.rstrip(';').strip()
        if not stmt:
            return []

        # Try each pattern matcher in order
        translators = [
            self._try_solve_order,
            self._try_soft,
            self._try_unique,
            self._try_foreach,
            self._try_distribution,
            self._try_inside,
            self._try_negated_inside,
            self._try_impl_inside,
            self._try_implication,
            self._try_conditional,
            self._try_array_size,
            self._try_range_constraint,  # Convert var >= min && var <= max to rangelist
            self._try_simple_expression,
        ]

        for translator in translators:
            result = translator(stmt)
            if result is not None:
                # Clean up any remaining semicolons
                return [line.rstrip(';').rstrip() for line in result if line.strip() and line.strip() != ';']

        return []

    def _try_solve_order(self, stmt: str) -> Optional[List[str]]:
        """Try to translate solve order constraint."""
        match = re.match(r'solve\s+(\w+)\s+before\s+(\w+)', stmt)
        if match:
            return [f"vsc.solve_order(self.{match.group(1)}, self.{match.group(2)})"]
        return None

    def _try_soft(self, stmt: str) -> Optional[List[str]]:
        """Try to translate soft constraint."""
        match = re.match(r'soft\s+(.+)', stmt)
        if match:
            inner = self._translate_expression(match.group(1))
            return [f"vsc.soft({inner})"]
        return None

    def _try_unique(self, stmt: str) -> Optional[List[str]]:
        """Try to translate unique constraint."""
        match = re.match(r'unique\s*\{([^}]+)\}', stmt)
        if match:
            items = match.group(1).strip()
            if ',' in items:
                vars_list = ', '.join(f"self.{v.strip()}" for v in items.split(','))
                return [f"vsc.unique({vars_list})"]
            return [f"vsc.unique(self.{items.strip()})"]
        return None

    def _try_foreach(self, stmt: str) -> Optional[List[str]]:
        """Try to translate foreach constraint."""
        match = re.match(r'foreach\s*\((\w+)\s*\[(\w+)\]\)\s*\{(.+)\}', stmt, re.DOTALL)
        if match:
            arr_name, idx_name, foreach_body = match.groups()
            lines = [f"with vsc.foreach(self.{arr_name}, idx=True) as {idx_name}:"]

            # Store the loop variable so we don't add self. to it
            self._current_loop_vars = getattr(self, '_current_loop_vars', set())
            self._current_loop_vars.add(idx_name)

            inner_stmts = self._split_statements(foreach_body)
            has_content = False
            if inner_stmts:
                for inner in inner_stmts:
                    inner = inner.strip().rstrip(';').strip()
                    if not inner:
                        continue
                    # Handle inside with array index: arr[i] inside {...}
                    arr_inside_match = re.match(rf'(\w+)\[{idx_name}\]\s+inside\s*\{{([^}}]+)\}}', inner)
                    if arr_inside_match:
                        arr, inside_body = arr_inside_match.groups()
                        rangelist = self._translate_inside(inside_body)
                        lines.append(f"    self.{arr}[{idx_name}] in vsc.rangelist({rangelist})")
                        has_content = True
                    else:
                        for line in self._translate_statement(inner):
                            # Fix any self.{idx_name} that got added incorrectly
                            line = re.sub(rf'\bself\.{idx_name}\b', idx_name, line)
                            lines.append(f"    {line}")
                            has_content = True
            
            if not has_content:
                lines.append("    pass")
            
            # Remove loop variable from tracking
            self._current_loop_vars.discard(idx_name)
            
            return lines
        return None

    def _try_distribution(self, stmt: str) -> Optional[List[str]]:
        """Try to translate distribution constraint."""
        match = re.match(r'(\w+)\s+dist\s*\{(.+)\}', stmt, re.DOTALL)
        if match:
            var_name, dist_body = match.groups()
            return self._translate_distribution(var_name, dist_body)
        return None

    def _try_inside(self, stmt: str) -> Optional[List[str]]:
        """Try to translate inside constraint."""
        # Handle bit-sliced variable: var[high:low] inside {...}
        bit_slice_inside = re.match(r'(\w+)\[(\d+):(\d+)\]\s+inside\s*\{([^}]+)\}', stmt)
        if bit_slice_inside:
            var, high, low, inside_body = bit_slice_inside.groups()
            rangelist = self._translate_inside(inside_body)
            # Preserve bit slice syntax - PyVSC supports it
            return [f"self.{var}[{high}:{low}] in vsc.rangelist({rangelist})"]

        # Standard inside: var inside {...} or var.size() inside {...}
        match = re.match(r'(\w+(?:\.\w+\(\))?)\s+inside\s*\{([^}]+)\}', stmt)
        if match:
            var_expr, inside_body = match.groups()
            var_expr = var_expr.replace('.size()', '.size')
            rangelist = self._translate_inside(inside_body)
            return [f"self.{var_expr} in vsc.rangelist({rangelist})"]
        return None

    def _try_negated_inside(self, stmt: str) -> Optional[List[str]]:
        """Try to translate negated inside constraint."""
        match = re.match(r'!\s*\(?\s*(\w+)\s+inside\s*\{([^}]+)\}\s*\)?', stmt)
        if match:
            var_name, inside_body = match.groups()
            rangelist = self._translate_inside(inside_body)
            return [f"vsc.not_inside(self.{var_name}, vsc.rangelist({rangelist}))"]
        return None

    def _try_impl_inside(self, stmt: str) -> Optional[List[str]]:
        """Try to translate implication with inside in consequent."""
        # Handle bit-sliced variable in consequent
        bit_slice_match = re.match(r'(.+?)\s*->\s*\(?\s*(\w+)\[(\d+):(\d+)\]\s+inside\s*\{([^}]+)\}\s*\)?', stmt)
        if bit_slice_match:
            antecedent, var, high, low, inside_body = bit_slice_match.groups()
            ant_expr = self._translate_expression(antecedent.strip())
            rangelist = self._translate_inside(inside_body)
            # Preserve bit slice syntax - PyVSC supports it
            return [
                f"with vsc.implies({ant_expr}):",
                f"{self.INDENT}self.{var}[{high}:{low}] in vsc.rangelist({rangelist})"
            ]

        # Standard implication with inside
        match = re.match(r'(.+?)\s*->\s*\(?\s*(\w+)\s+inside\s*\{([^}]+)\}\s*\)?', stmt)
        if match:
            antecedent, var_name, inside_body = match.groups()
            ant_expr = self._translate_expression(antecedent.strip())
            rangelist = self._translate_inside(inside_body)
            return [
                f"with vsc.implies({ant_expr}):",
                f"{self.INDENT}self.{var_name} in vsc.rangelist({rangelist})"
            ]
        return None

    def _try_implication(self, stmt: str) -> Optional[List[str]]:
        """Try to translate simple implication."""
        match = re.match(r'(.+?)\s*->\s*(.+)', stmt)
        if match:
            ant_expr = self._translate_expression(match.group(1).strip())
            cons_expr = self._translate_expression(match.group(2).strip())
            return [
                f"with vsc.implies({ant_expr}):",
                f"{self.INDENT}{cons_expr}"
            ]
        return None

    def _try_conditional(self, stmt: str) -> Optional[List[str]]:
        """Try to translate conditional constraint."""
        if not re.match(r'\s*if\s*\(', stmt):
            return None

        self._add_review_item(
            "Conditional constraint detected - verify if/else_if/else_then structure"
        )

        try:
            return self._parse_full_conditional(stmt, 0)
        except Exception as e:
            self._add_review_item(f"Conditional parsing error: {str(e)[:50]}")
            # Fallback: return as comment
            lines = ["# TODO: Complex conditional - manual translation needed"]
            for line in stmt.split('\n'):
                if line.strip():
                    lines.append(f"# {line.strip()}")
            lines.append("pass")
            return lines

    def _parse_full_conditional(self, stmt: str, base_indent: int) -> List[str]:
        """Parse complete if/else-if/else chain."""
        lines = []
        remaining = stmt.strip()
        indent = "    " * base_indent
        
        # Parse if block
        if_result = self._parse_if_block(remaining)
        if not if_result:
            return []
        
        condition, body, remaining = if_result
        cond_expr = self._translate_expression(condition)
        lines.append(f"{indent}with vsc.if_then({cond_expr}):")
        body_lines = self._parse_block_body(body, base_indent + 1)
        lines.extend(body_lines if body_lines else [f"{indent}    pass"])
        
        remaining = remaining.strip()
        
        # Parse else-if and else blocks
        while remaining:
            # Try else-if
            elif_result = self._parse_else_if_block(remaining)
            if elif_result:
                condition, body, remaining = elif_result
                cond_expr = self._translate_expression(condition)
                lines.append(f"{indent}with vsc.else_if({cond_expr}):")
                body_lines = self._parse_block_body(body, base_indent + 1)
                lines.extend(body_lines if body_lines else [f"{indent}    pass"])
                remaining = remaining.strip()
                continue
            
            # Try else
            else_result = self._parse_else_block(remaining)
            if else_result:
                body, remaining = else_result
                lines.append(f"{indent}with vsc.else_then:")
                body_lines = self._parse_block_body(body, base_indent + 1)
                lines.extend(body_lines if body_lines else [f"{indent}    pass"])
                remaining = remaining.strip()
                continue
            
            break
        
        return lines

    def _find_matching_begin_end(self, text: str, start: int) -> int:
        """Find matching 'end' for 'begin' at position start."""
        depth = 1
        i = start + 5  # Skip past 'begin'
        while i < len(text) and depth > 0:
            # Check for 'begin' keyword
            if text[i:i+5] == 'begin' and (i == 0 or not text[i-1].isalnum()):
                if i + 5 >= len(text) or not text[i+5].isalnum():
                    depth += 1
            # Check for 'end' keyword (but not 'endclass', 'endfunction', etc.)
            elif text[i:i+3] == 'end' and (i == 0 or not text[i-1].isalnum()):
                if i + 3 >= len(text) or not text[i+3].isalnum():
                    depth -= 1
                    if depth == 0:
                        return i + 2  # Return position of last char of 'end'
            i += 1
        return -1

    def _parse_if_block(self, stmt: str) -> Optional[Tuple[str, str, str]]:
        """Parse if block - handles braced, begin/end, and inline forms."""
        stmt = stmt.strip()
        match = re.match(r'if\s*\(', stmt)
        if not match:
            return None

        # Find condition (matching parentheses)
        cond_start = match.end() - 1
        cond_end = self._find_matching_paren(stmt, cond_start)
        if cond_end == -1:
            return None

        condition = stmt[cond_start + 1:cond_end].strip()
        after_cond = stmt[cond_end + 1:].strip()

        # Check for braced body
        if after_cond.startswith('{'):
            # Braced body
            body_end = self._find_matching_brace(stmt, cond_end + 1 + (len(stmt[cond_end+1:]) - len(after_cond)))
            if body_end == -1:
                return None
            brace_pos = stmt.index('{', cond_end)
            body = stmt[brace_pos + 1:body_end].strip()
            remainder = stmt[body_end + 1:].strip()
        # Check for begin...end body
        elif after_cond.startswith('begin'):
            begin_pos = stmt.index('begin', cond_end)
            end_pos = self._find_matching_begin_end(stmt, begin_pos)
            if end_pos == -1:
                return None
            body = stmt[begin_pos + 5:end_pos - 2].strip()  # Skip 'begin' and 'end'
            remainder = stmt[end_pos + 1:].strip()
        else:
            # Inline statement (no braces) - find the semicolon or next else
            body, remainder = self._extract_inline_statement(after_cond)
        
        return condition, body, remainder

    def _parse_else_if_block(self, stmt: str) -> Optional[Tuple[str, str, str]]:
        """Parse else-if block."""
        stmt = stmt.strip()
        match = re.match(r'else\s+if\s*\(', stmt)
        if not match:
            # Also handle "else if(" without space
            match = re.match(r'else\s*if\s*\(', stmt)
            if not match:
                return None

        # Find condition
        cond_start = stmt.index('(')
        cond_end = self._find_matching_paren(stmt, cond_start)
        if cond_end == -1:
            return None

        condition = stmt[cond_start + 1:cond_end].strip()
        after_cond = stmt[cond_end + 1:].strip()

        # Check for braced body
        if after_cond.startswith('{'):
            brace_pos = stmt.index('{', cond_end)
            body_end = self._find_matching_brace(stmt, brace_pos)
            if body_end == -1:
                return None
            body = stmt[brace_pos + 1:body_end].strip()
            remainder = stmt[body_end + 1:].strip()
        # Check for begin...end body
        elif after_cond.startswith('begin'):
            begin_pos = stmt.index('begin', cond_end)
            end_pos = self._find_matching_begin_end(stmt, begin_pos)
            if end_pos == -1:
                return None
            body = stmt[begin_pos + 5:end_pos - 2].strip()
            remainder = stmt[end_pos + 1:].strip()
        else:
            body, remainder = self._extract_inline_statement(after_cond)

        return condition, body, remainder

    def _parse_else_block(self, stmt: str) -> Optional[Tuple[str, str]]:
        """Parse else block."""
        stmt = stmt.strip()
        match = re.match(r'else\s*(?!\s*if)', stmt)
        if not match:
            return None

        after_else = stmt[match.end():].strip()

        if after_else.startswith('{'):
            brace_pos = stmt.index('{')
            body_end = self._find_matching_brace(stmt, brace_pos)
            if body_end == -1:
                return None
            body = stmt[brace_pos + 1:body_end].strip()
            remainder = stmt[body_end + 1:].strip()
        # Check for begin...end body
        elif after_else.startswith('begin'):
            begin_pos = stmt.index('begin')
            end_pos = self._find_matching_begin_end(stmt, begin_pos)
            if end_pos == -1:
                return None
            body = stmt[begin_pos + 5:end_pos - 2].strip()
            remainder = stmt[end_pos + 1:].strip()
        else:
            body, remainder = self._extract_inline_statement(after_else)

        return body, remainder

    def _extract_inline_statement(self, stmt: str) -> Tuple[str, str]:
        """Extract inline statement (without braces) and find remainder."""
        stmt = stmt.strip()
        
        # Check if this is a nested if (inline if)
        if re.match(r'if\s*\(', stmt):
            # Find the end of this complete if/else chain
            end_pos = self._find_conditional_end(stmt)
            return stmt[:end_pos].strip(), stmt[end_pos:].strip()
        
        # Simple statement ending with semicolon
        semi_pos = stmt.find(';')
        if semi_pos != -1:
            # Check if there's an else after this
            after_semi = stmt[semi_pos + 1:].strip()
            # Return statement without the semicolon
            return stmt[:semi_pos].strip(), after_semi
        
        return stmt, ""

    def _find_conditional_end(self, stmt: str) -> int:
        """Find the end of a complete if/else-if/else chain."""
        pos = 0
        
        while pos < len(stmt):
            # Skip whitespace
            while pos < len(stmt) and stmt[pos].isspace():
                pos += 1
            
            if pos >= len(stmt):
                break
            
            # Check for if
            if stmt[pos:].startswith('if'):
                match = re.match(r'if\s*\(', stmt[pos:])
                if match:
                    # Find condition end
                    cond_start = pos + stmt[pos:].index('(')
                    cond_end = self._find_matching_paren(stmt, cond_start)
                    if cond_end == -1:
                        return len(stmt)
                    
                    pos = cond_end + 1
                    # Skip whitespace
                    while pos < len(stmt) and stmt[pos].isspace():
                        pos += 1
                    
                    # Find body
                    if pos < len(stmt) and stmt[pos] == '{':
                        body_end = self._find_matching_brace(stmt, pos)
                        if body_end == -1:
                            return len(stmt)
                        pos = body_end + 1
                    else:
                        # Inline - find semicolon or nested if end
                        inner_end = self._find_statement_end(stmt[pos:])
                        pos += inner_end
                    continue
            
            # Check for else if
            elif_match = re.match(r'else\s+if\s*\(', stmt[pos:])
            if elif_match:
                cond_start = pos + stmt[pos:].index('(')
                cond_end = self._find_matching_paren(stmt, cond_start)
                if cond_end == -1:
                    return len(stmt)
                
                pos = cond_end + 1
                while pos < len(stmt) and stmt[pos].isspace():
                    pos += 1
                
                if pos < len(stmt) and stmt[pos] == '{':
                    body_end = self._find_matching_brace(stmt, pos)
                    if body_end == -1:
                        return len(stmt)
                    pos = body_end + 1
                else:
                    inner_end = self._find_statement_end(stmt[pos:])
                    pos += inner_end
                continue
            
            # Check for else (not else if)
            else_match = re.match(r'else\s*(?!if)', stmt[pos:])
            if else_match:
                pos += else_match.end()
                while pos < len(stmt) and stmt[pos].isspace():
                    pos += 1
                
                if pos < len(stmt) and stmt[pos] == '{':
                    body_end = self._find_matching_brace(stmt, pos)
                    if body_end == -1:
                        return len(stmt)
                    pos = body_end + 1
                else:
                    inner_end = self._find_statement_end(stmt[pos:])
                    pos += inner_end
                # else is the end of the chain
                break
            
            # Not part of the if chain anymore
            break
        
        return pos

    def _find_statement_end(self, stmt: str) -> int:
        """Find end of a single statement (semicolon or nested conditional)."""
        if re.match(r'\s*if\s*\(', stmt):
            return self._find_conditional_end(stmt)
        
        semi_pos = stmt.find(';')
        return semi_pos + 1 if semi_pos != -1 else len(stmt)

    def _parse_block_body(self, body: str, indent_level: int) -> List[str]:
        """Parse the body of a conditional block."""
        lines = []
        indent = "    " * indent_level
        body = body.strip()
        
        if not body:
            return []
        
        # Check if body starts with if (nested conditional)
        if re.match(r'if\s*\(', body):
            # Find where the conditional ends
            cond_end = self._find_conditional_end(body)
            cond_part = body[:cond_end].strip()
            remaining_part = body[cond_end:].strip()
            
            # Parse the conditional part
            nested_lines = self._parse_full_conditional(cond_part, indent_level)
            lines.extend(nested_lines)
            
            # Parse any remaining statements after the conditional
            if remaining_part:
                for stmt in self._split_statements(remaining_part):
                    stmt = stmt.strip().rstrip(';').strip()
                    if not stmt:
                        continue
                    if re.match(r'if\s*\(', stmt):
                        nested_lines = self._parse_full_conditional(stmt, indent_level)
                        lines.extend(nested_lines)
                    else:
                        translated = self._translate_statement(stmt)
                        for line in translated:
                            cleaned = line.rstrip(';').strip()
                            if cleaned:
                                lines.append(f"{indent}{cleaned}")
            
            return lines
        
        # Process statements normally
        for stmt in self._split_statements(body):
            stmt = stmt.strip().rstrip(';').strip()
            if not stmt:
                continue
            
            if re.match(r'if\s*\(', stmt):
                # Nested conditional
                nested_lines = self._parse_full_conditional(stmt, indent_level)
                lines.extend(nested_lines)
            else:
                # Regular statement
                translated = self._translate_statement(stmt)
                for line in translated:
                    # Skip empty lines and lines that are just semicolons
                    cleaned = line.rstrip(';').strip()
                    if cleaned:
                        lines.append(f"{indent}{cleaned}")
        
        return lines

    def _try_array_size(self, stmt: str) -> Optional[List[str]]:
        """Try to translate array size constraint."""
        match = re.match(r'(\w+)\.size\(\)\s*(==|!=|<|>|<=|>=)\s*(.+)', stmt)
        if match:
            arr_name, op, value = match.groups()
            value_expr = self._translate_expression(value.strip())
            return [f"self.{arr_name}.size {op} {value_expr}"]
        return None

    def _find_matching_paren(self, text: str, start: int) -> int:
        """Find matching closing parenthesis."""
        if start >= len(text) or text[start] != '(':
            return -1
        
        depth = 1
        i = start + 1
        while i < len(text) and depth > 0:
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
            i += 1
        
        return i - 1 if depth == 0 else -1

    def _find_matching_brace(self, text: str, start: int) -> int:
        """Find matching closing brace."""
        if start >= len(text) or text[start] != '{':
            return -1
        
        depth = 1
        i = start + 1
        while i < len(text) and depth > 0:
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
            i += 1
        
        return i - 1 if depth == 0 else -1

    def _try_range_constraint(self, stmt: str) -> Optional[List[str]]:
        """Try to translate range constraint: var >= min && var <= max -> var in vsc.rangelist(vsc.rng(min, max))"""
        # Strip outer parentheses if present
        stripped = stmt.strip()
        while stripped.startswith('(') and stripped.endswith(')'):
            # Check if these are matching outer parentheses
            depth = 0
            is_outer = True
            for i, c in enumerate(stripped):
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                if depth == 0 and i < len(stripped) - 1:
                    is_outer = False
                    break
            if is_outer:
                stripped = stripped[1:-1].strip()
            else:
                break

        # Pattern: var >= min && var <= max or var >= min & var <= max (same variable on both sides)
        # Also handles: var <= max && var >= min
        pattern1 = r'(\w+)\s*>=\s*(-?\d+)\s*(?:&&|&)\s*(\w+)\s*<=\s*(-?\d+)'
        pattern2 = r'(\w+)\s*<=\s*(-?\d+)\s*(?:&&|&)\s*(\w+)\s*>=\s*(-?\d+)'

        match = re.match(pattern1, stripped)
        if match:
            var1, min_val, var2, max_val = match.groups()
            if var1 == var2:
                return [f"self.{var1} in vsc.rangelist(vsc.rng({min_val}, {max_val}))"]

        match = re.match(pattern2, stripped)
        if match:
            var1, max_val, var2, min_val = match.groups()
            if var1 == var2:
                return [f"self.{var1} in vsc.rangelist(vsc.rng({min_val}, {max_val}))"]

        return None

    def _try_simple_expression(self, stmt: str) -> Optional[List[str]]:
        """Try to translate simple expression."""
        expr = self._translate_expression(stmt)
        return [expr] if expr and expr.strip() else []

    def _translate_expression(self, expr: str) -> str:
        """Translate a constraint expression."""
        if not expr:
            return ""

        expr = self._convert_numbers(expr)
        expr = self._convert_logical_operators(expr)
        expr = self._convert_inside_expression(expr)
        expr = self._convert_bit_slicing(expr)
        expr = self._qualify_enum_values(expr)
        expr = self._add_self_prefix(expr)
        expr = self._convert_bare_conditions(expr)
        return expr

    def _convert_logical_operators(self, expr: str) -> str:
        """Convert SystemVerilog logical operators to PyVSC equivalents.

        Conversions:
        - && -> &
        - || -> |
        - !expr -> ~expr
        - !(a && b) -> ~(a & b)
        - !(a || b) -> ~(a | b)
        """
        # First convert && to & and || to |
        expr = re.sub(r'&&', '&', expr)
        expr = re.sub(r'\|\|', '|', expr)

        # Convert ! to ~ for logical NOT
        # Handle !( patterns first (negation of grouped expressions)
        expr = re.sub(r'!\s*\(', '~(', expr)

        # Handle !var patterns (negation of single variables)
        # But don't convert != (not equal)
        expr = re.sub(r'!(?!=)(\w)', r'~\1', expr)

        return expr

    def _qualify_enum_values(self, expr: str) -> str:
        """Qualify enum value literals with their enum class name."""
        if not self.enum_value_map:
            return expr

        def replace_enum(match):
            name = match.group(0)
            if name not in self.enum_value_map:
                return name
            start = match.start()
            if start > 0 and expr[start - 1] == '.':
                return name
            return f"{self.enum_value_map[name]}.{name}"

        return re.sub(r'\b[A-Z][A-Z0-9_]*\b', replace_enum, expr)

    def _convert_bare_conditions(self, expr: str) -> str:
        """Convert bare variable conditions to PyVSC-compatible comparisons.

        PyVSC doesn't support True/False or bare variables in conditions.
        Convert: self.var -> (self.var != 0)
        Convert: ~self.var -> (self.var == 0)
        """
        # Don't convert if it already has a comparison operator
        if any(op in expr for op in ['==', '!=', '<', '>', '<=', '>=']):
            return expr

        # Don't convert if it's a rangelist or other vsc construct
        if 'vsc.' in expr and ' in vsc.rangelist' not in expr:
            return expr

        # Handle 'in vsc.rangelist' - this is already a valid constraint
        if ' in vsc.rangelist' in expr:
            return expr

        # Handle '~self.var' -> '(self.var == 0)'
        not_match = re.match(r'^~\s*(self\.\w+)$', expr.strip())
        if not_match:
            return f'({not_match.group(1)} == 0)'

        # Handle bare 'self.var' -> '(self.var != 0)'
        bare_var_match = re.match(r'^(self\.\w+)$', expr.strip())
        if bare_var_match:
            return f'({bare_var_match.group(1)} != 0)'

        return expr

    def _convert_inside_expression(self, expr: str) -> str:
        """Convert 'var inside {values}' to 'var in vsc.rangelist(values)'."""
        # Pattern: identifier inside {values}
        pattern = r'(\w+)\s+inside\s*\{([^}]+)\}'

        def replace_inside(match):
            var_name = match.group(1)
            values_str = match.group(2)
            rangelist = self._translate_inside(values_str)
            return f'{var_name} in vsc.rangelist({rangelist})'

        return re.sub(pattern, replace_inside, expr)

    def _add_self_prefix(self, expr: str) -> str:
        """Add self. prefix to variable names."""
        def replace_var(match):
            word = match.group(0)
            if word in PYTHON_KEYWORDS:
                return word
            start = match.start()
            if start > 0 and expr[start-1] == '.':
                return word
            if word in self.enum_class_names:
                end = match.end()
                if end < len(expr) and expr[end] == '.':
                    return word
                return f"self.{word}"
            return f"self.{word}"

        result = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', replace_var, expr)
        result = result.replace('self.self.', 'self.')
        result = re.sub(r'self\.(vsc)\b', r'\1', result)
        return result

    def _convert_bit_slicing(self, expr: str) -> str:
        """Preserve bit slicing syntax - PyVSC supports var[high:low] directly."""
        # PyVSC supports bit slicing with [] syntax, so we just preserve it as-is
        # The only change needed is to ensure the variable gets self. prefix (handled elsewhere)
        return expr

    @staticmethod
    def _convert_numbers(expr: str) -> str:
        """Convert SV number formats to Python."""
        def replace_num(match):
            base_char = match.group(2).lower()
            value = match.group(3)
            prefix_map = {'h': '0x', 'b': '0b', 'o': '0o', 'd': ''}
            # Remove underscores from the number value only
            value = value.replace('_', '')
            return f"{prefix_map.get(base_char, '')}{value}"

        # Only convert SV number literals (N'hXX format)
        expr = re.sub(r"(\d+)'([hHbBdDoO])([0-9a-fA-F_]+)", replace_num, expr)
        # Don't remove underscores globally - they're valid in variable names!
        return expr

    def _translate_inside(self, inside_body: str) -> str:
        """Translate inside body to rangelist arguments."""
        parts = []
        for item in self._parse_inside_items(inside_body):
            item = item.strip()
            range_match = re.match(r'\[(.+?):(.+?)\]', item)
            if range_match:
                low = self._convert_numbers(range_match.group(1).strip())
                high = self._convert_numbers(range_match.group(2).strip())
                parts.append(f"vsc.rng({low}, {high})")
            else:
                parts.append(self._convert_numbers(item))
        return ', '.join(parts)

    @staticmethod
    def _parse_inside_items(body: str) -> List[str]:
        """Parse inside body into individual items."""
        items, current, bracket_depth = [], "", 0

        for char in body:
            if char == '[':
                bracket_depth += 1
            elif char == ']':
                bracket_depth -= 1
            elif char == ',' and bracket_depth == 0:
                items.append(current.strip())
                current = ""
                continue
            current += char

        if current.strip():
            items.append(current.strip())
        return items

    def _translate_distribution(self, var_name: str, dist_body: str) -> List[str]:
        """Translate distribution constraint."""
        weights = []

        for item in dist_body.split(','):
            item = item.strip()
            if not item:
                continue

            # Per-item weight (:=) or range weight (:/)
            for pattern, range_mode in [(r'(.+?)\s*:=\s*(\d+)', False), 
                                         (r'(.+?)\s*:/\s*(\d+)', True)]:
                match = re.match(pattern, item)
                if match:
                    val_part, weight = match.groups()
                    rng_match = re.match(r'\[(.+?):(.+?)\]', val_part.strip())

                    if rng_match:
                        low = self._convert_numbers(rng_match.group(1).strip())
                        high = self._convert_numbers(rng_match.group(2).strip())
                        range_arg = ", 'range'" if range_mode else ""
                        weights.append(f"vsc.weight(vsc.rng({low}, {high}), {weight}{range_arg})")
                    else:
                        val = self._convert_numbers(val_part.strip())
                        weights.append(f"vsc.weight({val}, {weight})")
                    break

        lines = [f"vsc.dist(self.{var_name}, ["]
        for w in weights:
            lines.append(f"    {w},")
        lines.append("])")
        return lines

    def _generate_hook(self, name: str, body: str) -> List[str]:
        """Generate pre/post randomize hook."""
        self._add_review_item(f"{name} function requires manual translation")
        desc = "before" if name == "pre_randomize" else "after successful"
        return [
            f"{self.INDENT}def {name}(self):",
            f'{self.INDENT}{self.INDENT}"""Called {desc} randomization"""',
            f'{self.INDENT}{self.INDENT}# Original SV: {body[:80]}...' if len(body) > 80 else f'{self.INDENT}{self.INDENT}# Original SV: {body}',
            f'{self.INDENT}{self.INDENT}pass  # TODO: Translate {name} logic',
        ]

    def _generate_usage_example(self, sv_classes: List[SVClass]) -> str:
        """Generate usage example code."""
        if not sv_classes:
            return ""

        lines = [
            "# " + "=" * 77,
            "# USAGE EXAMPLE",
            "# " + "=" * 77,
            "",
            "if __name__ == '__main__':",
            "    # Set seed for reproducibility (optional)",
            "    # vsc.set_randstate(12345)",
            ""
        ]

        for sv_class in sv_classes:
            class_name = self._to_python_class_name(sv_class.name)
            var_name = sv_class.name.lower()

            lines.extend([
                f"    # Create and randomize {class_name}",
                f"    {var_name} = {class_name}()",
                f"    {var_name}_randomized = False",
                f"    try:",
                f"        {var_name}.randomize()",
                f"        {var_name}_randomized = True",
                f"        print(f'{class_name} randomized successfully')",
                f"    except Exception as e:",
                f"        print(f'{class_name} randomize failed: {{e}}')",
                ""
            ])

            if sv_class.fields:
                lines.append(f"    if {var_name}_randomized:")
                lines.append("        # Print field values")
                for fld in sv_class.fields[:5]:
                    lines.append(f"        print(f'  {fld.name} = {{{var_name}.{fld.name}}}')")
                lines.append("")

        return '\n'.join(lines)

    @staticmethod
    def _to_python_class_name(sv_name: str) -> str:
        """Convert SV name to Python class name (PascalCase)."""
        name = re.sub(r'_[te]$', '', sv_name)
        return ''.join(part.capitalize() for part in name.split('_'))


# =============================================================================
# MAIN TRANSLATOR CLASS
# =============================================================================

class SVtoPyVSCTranslator:
    """Main translator class that orchestrates the translation process."""

    def __init__(self, verbose: bool = False):
        self.parser = SVParser()
        self.generator = PyVSCGenerator(verbose=verbose)

    def translate_file(self, input_path: str, output_path: Optional[str] = None) -> TranslationResult:
        """Translate a SystemVerilog file to pyvsc."""
        with open(input_path, 'r') as f:
            sv_code = f.read()

        result = self.translate_code(sv_code)

        if output_path:
            with open(output_path, 'w') as f:
                f.write(result.pyvsc_code)
            print(f"Output written to: {output_path}")

        return result

    def translate_code(self, sv_code: str) -> TranslationResult:
        """Translate SystemVerilog code string to pyvsc."""
        sv_classes = self.parser.parse(sv_code)

        if not sv_classes:
            return TranslationResult(
                pyvsc_code="# No classes found in input",
                warnings=["No SystemVerilog classes found in input"],
                manual_review_items=[],
                mapping_notes=[],
                statistics={'classes': 0, 'fields': 0, 'constraints': 0, 'enums': 0}
            )

        return self.generator.generate(sv_classes)

    def print_report(self, result: TranslationResult):
        """Print translation report with comprehensive metrics."""
        print("\n" + "=" * 80)
        print("SV TO PYVSC TRANSLATION REPORT")
        print("=" * 80)
        
        # Source and Output Metrics Summary
        print("\n" + "-" * 80)
        print("CONVERSION METRICS")
        print("-" * 80)
        
        m = self.generator.metrics
        
        # Line counts
        print(f"\n  Lines:")
        print(f"     Source SV:     {m['sv_lines']:>6}")
        print(f"     Output Python: {m['py_lines']:>6}")
        
        # Variable counts
        print(f"\n  Variables:")
        print(f"     Detected in SV:     {len(m['sv_variables']):>6}")
        print(f"     Present in Python:  {len(m['py_variables']):>6}")
        
        # Conditionals
        sv_cond = m['sv_conditionals']
        py_cond = m['py_if_then'] + m['py_else_if']
        print(f"\n  Conditionals:")
        print(f"     Detected (if/else if): {sv_cond:>6}")
        print(f"     Converted (if_then/else_if): {py_cond:>6}")
        
        # Logical operators
        sv_logical = m['sv_logical_and'] + m['sv_logical_or'] + m['sv_logical_not']
        py_logical = m.get('py_logical_and', 0) + m.get('py_logical_or', 0) + m.get('py_logical_not', 0)
        print(f"\n  Logical Operators:")
        print(f"     && detected:  {m['sv_logical_and']:>4}  ->  'and' converted: {m.get('py_logical_and', 0):>4}")
        print(f"     || detected:  {m['sv_logical_or']:>4}  ->  'or' converted:  {m.get('py_logical_or', 0):>4}")
        print(f"     !  detected:  {m['sv_logical_not']:>4}  ->  'not' converted: {m.get('py_logical_not', 0):>4}")
        print(f"     Total:        {sv_logical:>4}  ->  Total:           {py_logical:>4}")
        
        # Constraint constructs comparison
        print(f"\n  Constraint Constructs:")
        print(f"     {'Construct':<20} {'SV Detected':>12} {'Python Generated':>18}")
        print(f"     {'-'*20} {'-'*12} {'-'*18}")
        print(f"     {'inside':<20} {m['sv_inside']:>12} {m['py_rangelist']:>18}")
        print(f"     {'implication (->)':<20} {m['sv_implies']:>12} {m['py_implies']:>18}")
        print(f"     {'dist':<20} {m['sv_dist']:>12} {m['py_dist']:>18}")
        print(f"     {'solve_order':<20} {m['sv_solve_order']:>12} {m['py_solve_order']:>18}")
        print(f"     {'foreach':<20} {m['sv_foreach']:>12} {m['py_foreach']:>18}")
        print(f"     {'unique':<20} {m['sv_unique']:>12} {m['py_unique']:>18}")
        print(f"     {'soft':<20} {m['sv_soft']:>12} {m['py_soft']:>18}")
        
        # Special conversions
        print(f"\n  Special Conversions:")
        print(f"     Bit slices detected:   {m['sv_bit_slices']:>6}")
        print(f"     Number formats (N'h):  {m['sv_number_formats']:>6}")
        
        # Basic statistics
        print("\n" + "-" * 80)
        print("TRANSLATION STATISTICS")
        print("-" * 80)
        for key, value in result.statistics.items():
            print(f"   * {key.capitalize()}: {value}")

        if result.mapping_notes:
            print("\n" + "-" * 80)
            print("MAPPING NOTES")
            print("-" * 80)
            for note in result.mapping_notes:
                print(f"   * {note}")

        if result.warnings:
            print("\n" + "-" * 80)
            print("WARNINGS")
            print("-" * 80)
            for warning in result.warnings:
                print(f"   * {warning}")

        if result.manual_review_items:
            print("\n" + "-" * 80)
            print("MANUAL REVIEW REQUIRED")
            print("-" * 80)
            for item in result.manual_review_items:
                print(f"   * {item}")
        
        # Validation summary
        print("\n" + "-" * 80)
        print("OUTPUT VALIDATION")
        print("-" * 80)
        print(f"   * if_then blocks:      {m['py_if_then']:>6}")
        print(f"   * else_if blocks:      {m['py_else_if']:>6}")
        print(f"   * else_then blocks:    {m['py_else_then']:>6}")
        print(f"   * rangelist (inside):  {m['py_rangelist']:>6}")
        print(f"   * implies:             {m['py_implies']:>6}")
        print(f"   * dist:                {m['py_dist']:>6}")
        print(f"   * solve_order:         {m['py_solve_order']:>6}")
        print(f"   * foreach:             {m['py_foreach']:>6}")
        print(f"   * unique:              {m['py_unique']:>6}")
        print(f"   * soft:                {m['py_soft']:>6}")

        print("\n" + "=" * 80)


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description='SystemVerilog to pyvsc Translation Assistant',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent('''
            Default behavior:
              %(prog)s                     -> input.sv -> output.py

            Examples:
              %(prog)s input.sv
              %(prog)s input.sv -o out.py
              %(prog)s -r
        ''')
    )

    parser.add_argument(
        'input',
        nargs='?',
        default='example_sv_classes.sv',
        help='Input SystemVerilog file (default: example_sv_classes.sv)'
    )

    parser.add_argument(
        '-o', '--output',
        default='example_sv_classes.py',
        help='Output Python file (default: example_sv_classes.py)'
    )


    parser.add_argument('-r', '--report', action='store_true', help='Print translation report')

    args = parser.parse_args()

    translator = SVtoPyVSCTranslator(verbose=args.report)

    try:
        result = translator.translate_file(args.input, args.output)
    except FileNotFoundError:
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error during translation: {e}", file=sys.stderr)
        sys.exit(1)

    if args.report:
        translator.print_report(result)


if __name__ == '__main__':
    main()
