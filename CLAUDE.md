# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **SystemVerilog to PyVSC Translation Assistant** - a manual translation tool (not an automated converter) that helps hardware verification engineers convert SystemVerilog constraint-based randomization models to PyVSC (Python Verification Stimulus and Coverage).

**Critical Philosophy**: All generated code requires manual review and validation by a verification engineer. This tool assists translation but doesn't guarantee semantic equivalence.

## Commands

### Basic Translation
```bash
# Translate SV file to stdout
python sv_to_pyvsc.py input.sv

# Translate and save to file
python sv_to_pyvsc.py input.sv -o output.py

# With translation report (includes metrics and warnings)
python sv_to_pyvsc.py input.sv -o output.py -r

# Quiet mode (suppress stdout)
python sv_to_pyvsc.py input.sv -o output.py -q
```

### Testing Generated Code
```bash
# Run example output to test pyvsc translation
python example_sv_classes.py

# Run any translated output
python translated_output.py
```

### Installing Dependencies
```bash
# Install pyvsc (required for running generated code)
pip install pyvsc

# Or use the batch script (Windows)
install_pyvsc.bat
```

## Architecture

### Three-Stage Pipeline

1. **SVParser** (sv_to_pyvsc.py:152) - Parses SystemVerilog source code
   - Removes comments
   - Extracts enums with `_extract_enums()`
   - Extracts classes with `_extract_classes()` including fields and constraints
   - Handles class hierarchies (extends)
   - Identifies pre_randomize/post_randomize functions

2. **PyVSCGenerator** (sv_to_pyvsc.py:487) - Generates Python/PyVSC code
   - Maps SV data types to PyVSC types
   - Translates constraint constructs (inside, dist, implications, etc.)
   - Generates @vsc.randobj decorated classes
   - Creates @vsc.constraint decorated methods
   - Preserves original SV code in docstrings
   - Tracks detailed metrics during generation

3. **SVtoPyVSCTranslator** (sv_to_pyvsc.py:2118) - Orchestrates the process
   - Combines parser and generator
   - Provides `translate_file()` and `translate_code()` APIs
   - Generates translation reports with metrics

### Key Data Structures

- **SVField** (line 54): Represents a field with type, width, array info
- **SVConstraint** (line 70): Represents a constraint block with body and analysis
- **SVEnum** (line 80): Represents enum types
- **SVClass** (line 89): Complete class representation with fields, constraints, enums
- **TranslationResult** (line 102): Output with code, warnings, review items, statistics

### Constraint Translation Logic

The generator handles complex constraint patterns:
- **Conditionals**: `if/else if/else` → `vsc.if_then/else_if/else_then` context managers
- **Inside constraints**: `inside {values}` → `vsc.rangelist()`
- **Distributions**: `dist {...}` → `vsc.dist()` with `vsc.weight()`
- **Implications**: `A -> B` → `vsc.implies(A, B)`
- **Solve order**: `solve A before B` → `vsc.solve_order(A, B)`
- **Logical ops**: `&&/||/!` → `and/or/not`
- **Foreach loops**: `foreach (arr[i])` → `vsc.foreach(arr, idx=True)`
- **Soft constraints**: `soft X` → `vsc.soft(X)`
- **Unique constraints**: `unique {arr}` → `vsc.unique(arr)`

### Validation Utilities (validation_utils.py)

**PyVSCValidator** class provides semantic validation:
- `test_basic_randomization()` - Checks randomization succeeds
- `test_value_distribution()` - Analyzes field value distributions
- `test_boundary_values()` - Verifies boundary reachability
- `test_constraint_invariant()` - Custom invariant checking
- `test_distribution_weights()` - Distribution weight verification

## Translation Mapping Reference

### Data Types
- `rand bit [N-1:0]` → `vsc.rand_bit_t(N)`
- `randc bit [N-1:0]` → `vsc.randc_bit_t(N)`
- `rand int` → `vsc.rand_int32_t()`
- `rand enum E` → `vsc.rand_enum_t(E)`
- `rand T arr[N]` → `vsc.rand_list_t(T, sz=N)`
- `rand T arr[]` → `vsc.rand_list_t(T)` (dynamic)

### Class Naming Convention
- SystemVerilog snake_case → Python PascalCase
- `my_transaction_class` → `MyTransactionClass`
- Strips `_t` and `_e` suffixes from enum types

## Known Limitations

When modifying the translator, be aware of these edge cases:

1. **Bit slicing** (`x[7:4]`) - Converted to shifts/masks, may need verification
2. **Complex nested conditionals** - May require manual restructuring
3. **Bidirectional implications** (`A <-> B`) - Requires two `vsc.implies()` calls
4. **Enum references in distributions** - Need proper enum class prefixes
5. **Loop variables in foreach** - May incorrectly get `self.` prefix
6. **Logical operators in expressions** - Require `vsc.and_()`, `vsc.or_()` for some contexts

## Code Modification Guidelines

### When Adding New Constraint Support

1. Add pattern to `CONSTRAINT_PATTERNS` (sv_to_pyvsc.py:133)
2. Implement parsing in `_extract_constraints()` (line 394)
3. Add translation logic in `_translate_constraint_body()` (generator class)
4. Update metrics tracking in `_analyze_sv_source()`
5. Add test case in example_sv_classes.sv

### When Modifying Type Mappings

1. Update `_map_type_to_pyvsc()` in PyVSCGenerator
2. Check WIDTH_MAP constant (line 116) for width mappings
3. Ensure both rand and non-rand variants are handled
4. Update README.md translation table

### Adding Validation Tests

Extend `validation_utils.py`:
- Add new test method to `PyVSCValidator` class
- Follow naming pattern: `test_<feature_name>()`
- Append results to `self.results`
- Return `ValidationResult` with pass/fail status

## Metrics System

The generator tracks comprehensive metrics during translation:
- Line counts (SV vs Python)
- Variable detection and conversion
- Conditional count (if/else-if → if_then/else_if)
- Logical operator conversion (&&/||/! → and/or/not)
- Constraint construct conversion (inside, dist, implies, solve_order)

Access via `generator.metrics` dictionary after translation.

## Output Structure

Generated Python files contain:
1. File header with manual review instructions
2. Enum definitions as Python IntEnum classes
3. Base class stubs (if needed for inheritance)
4. @vsc.randobj decorated classes with:
   - `__init__()` with field declarations
   - @vsc.constraint methods preserving SV constraint names
   - Original SV code in constraint docstrings
   - Constraint metrics in docstrings
5. Usage example at bottom demonstrating randomization

## Development Notes

- The tool preserves original SV code in docstrings for reference
- Warnings are generated for constructs requiring manual review
- Python keywords (PYTHON_KEYWORDS constant) are never prefixed with `self.`
- Constraint bodies are analyzed to detect logical operators and translate them
- Comments are stripped from SV input before parsing to avoid confusion
