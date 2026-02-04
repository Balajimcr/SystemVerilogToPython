# SV-to-PyVSC Translation Assistant

[![Python Tests](https://github.com/balajimcr/SystemVerilogToPython/actions/workflows/python-tests.yml/badge.svg)](https://github.com/balajimcr/SystemVerilogToPython/actions/workflows/python-tests.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python tool that assists with manual translation of SystemVerilog constraint-based randomization models to PyVSC (Python Verification Stimulus and Coverage).

## Important Notice

This is a **Translation Assistant**, not an automated converter. The generated code requires **manual review and validation** by a verification engineer to ensure semantic equivalence.

## Features

- **Parses SystemVerilog** constraint classes, enums, and hierarchies
- **Generates PyVSC code** with proper decorators and type mappings
- **Translates constraint constructs**:
  - `rand`/`randc` fields
  - `inside` range constraints → `vsc.rangelist()`
  - Range constraints (`var >= min && var <= max`) → `vsc.rangelist(vsc.rng(min, max))`
  - Implications (`->`) → `vsc.implies()`
  - Conditional constraints (`if/else`) → `vsc.if_then/else_then`
  - Weighted distributions (`dist`) → `vsc.dist()`
  - Solve order (`solve before`) → `vsc.solve_order()`
  - Unique constraints → `vsc.unique()`
  - Foreach loops → `vsc.foreach()`
  - Soft constraints → `vsc.soft()`
  - Bit slicing (`var[7:0]`) - preserved as-is
  - Signed variables (`rand bit signed [31:0]`) → `vsc.rand_int32_t()`
- **Clean output by default** - no comments or docstrings cluttering the code
- **Verbose mode (-r)** - includes original SV code and metrics in docstrings
- **Flags items requiring manual review**
- **Provides translation report** with statistics and warnings

## Installation

```bash
# Clone the repository
git clone https://github.com/balajimcr/SystemVerilogToPython.git
cd SystemVerilogToPython

# Install pyvsc (required for running generated code)
pip install pyvsc
```

## Usage

### Command Line

```bash
# Basic translation (clean output, no comments)
python sv_to_pyvsc.py input.sv -o output.py

# With translation report and verbose output (includes original SV in docstrings)
python sv_to_pyvsc.py input.sv -o output.py -r

# Output to stdout
python sv_to_pyvsc.py input.sv

# Quiet mode (suppress stdout, just save file)
python sv_to_pyvsc.py input.sv -o output.py -q
```

### Python API

```python
from sv_to_pyvsc import SVtoPyVSCTranslator

# Create translator (verbose=True to include original SV in output)
translator = SVtoPyVSCTranslator(verbose=False)

# Translate from file
result = translator.translate_file('input.sv', 'output.py')

# Or translate from string
sv_code = '''
class my_transaction;
    rand bit [7:0] addr;
    constraint c { addr inside {[0:127]}; }
endclass
'''
result = translator.translate_code(sv_code)

# Access results
print(result.pyvsc_code)           # Generated Python code
print(result.warnings)              # Translation warnings
print(result.manual_review_items)   # Items needing review
print(result.statistics)            # Translation statistics

# Print detailed report
translator.print_report(result)
```

## Translation Mapping Reference

### Data Types

| SystemVerilog | PyVSC (Random) | PyVSC (Non-Random) |
|---------------|----------------|---------------------|
| `rand bit [N-1:0]` | `vsc.rand_bit_t(N)` | `vsc.bit_t(N)` |
| `rand bit signed [N-1:0]` | `vsc.rand_int32_t()` | `vsc.int32_t()` |
| `randc bit [N-1:0]` | `vsc.randc_bit_t(N)` | N/A |
| `rand int` | `vsc.rand_int32_t()` | `vsc.int32_t()` |
| `rand enum` | `vsc.rand_enum_t(EnumType)` | `vsc.enum_t(EnumType)` |
| `rand T arr[N]` | `vsc.rand_list_t(T, sz=N)` | `vsc.list_t(T, sz=N)` |
| `rand T arr[]` | `vsc.rand_list_t(T)` | `vsc.list_t(T)` |

### Constraints

| SystemVerilog | PyVSC |
|---------------|-------|
| `var >= min && var <= max` | `var in vsc.rangelist(vsc.rng(min, max))` |
| `inside {[a:b]}` | `x.inside(vsc.rangelist(vsc.rng(a, b)))` |
| `inside {v1, v2}` | `x.inside(vsc.rangelist(v1, v2))` |
| `A -> B` | `vsc.implies(A, B)` |
| `if (c) {...}` | `with vsc.if_then(c): ...` |
| `else {...}` | `with vsc.else_then: ...` |
| `dist {v := w}` | `vsc.dist(x, [vsc.weight(v, w)])` |
| `solve a before b` | `vsc.solve_order(a, b)` |
| `unique {arr}` | `vsc.unique(arr)` |
| `foreach (a[i])` | `with vsc.foreach(a, idx=True) as i:` |
| `soft x == v` | `vsc.soft(x == v)` |
| `var[7:0]` | `var[7:0]` (preserved) |
| `&&` | `and` |
| `\|\|` | `or` |
| `&` / `\|` | `&` / `\|` (preserved) |

### Constraint Ordering

- `vsc.solve_order()` statements are automatically placed at the beginning of each constraint
- The relative order of solve_order statements is preserved from the original SV

## Example

### Input (SystemVerilog)

```systemverilog
class axi_transaction;
    rand bit [31:0] addr;
    rand bit signed [15:0] offset;
    rand bit [7:0] len;

    constraint addr_range_c {
        addr >= 0 && addr <= 4095;
    }

    constraint offset_range_c {
        offset >= -1024 && offset <= 1023;
    }

    constraint len_c {
        if (addr[3:0] == 0)
            len inside {1, 2, 4, 8};
        else
            len == 1;

        solve addr before len;
    }
endclass
```

### Output (PyVSC)

```python
@vsc.randobj
class AxiTransaction:
    def __init__(self):
        self.addr = vsc.rand_bit_t(32)
        self.offset = vsc.rand_int16_t()
        self.len = vsc.rand_bit_t(8)

    @vsc.constraint
    def addr_range_c(self):
        self.addr in vsc.rangelist(vsc.rng(0, 4095))

    @vsc.constraint
    def offset_range_c(self):
        self.offset in vsc.rangelist(vsc.rng(-1024, 1023))

    @vsc.constraint
    def len_c(self):
        vsc.solve_order(self.addr, self.len)
        with vsc.if_then(self.addr[3:0] == 0):
            self.len.inside(vsc.rangelist(1, 2, 4, 8))
        with vsc.else_then:
            self.len == 1
```

## Known Limitations

1. **Complex nested conditionals** - May need restructuring
2. **Bidirectional implications** (`<->`) - Requires two `vsc.implies()` calls
3. **Enum references in distributions** - Need proper enum class prefix
4. **Loop variables** in foreach - May get incorrect `self.` prefix

## Project Structure

```
SystemVerilogToPython/
├── sv_to_pyvsc.py           # Main translator
├── validation_utils.py       # Validation utilities
├── example_sv_classes.sv     # Example SV input
├── example_sv_classes.py     # Example translated output
├── README.md                 # This file
├── CLAUDE.md                 # Development guidelines
├── requirements.txt          # Python dependencies
└── .github/
    └── workflows/
        └── python-tests.yml  # GitHub Actions CI
```

## Development

### Running Tests

```bash
# Run the translator on example file
python sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py

# Verify syntax of generated code
python -m py_compile example_sv_classes.py

# Run with pyvsc (if installed)
python example_sv_classes.py
```

### Validation

The tool includes validation utilities:

```python
from validation_utils import PyVSCValidator

validator = PyVSCValidator(MyTransactionClass)
results = validator.validate_all(iterations=10000)
validator.print_report()
```

## Contributing

Contributions welcome! Please ensure all translations maintain semantic fidelity with the original SystemVerilog.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests to ensure nothing is broken
5. Submit a pull request

## License

MIT License
