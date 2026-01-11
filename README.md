# SV-to-pyvsc Translation Assistant

A Python tool that assists with manual translation of SystemVerilog constraint-based randomization models to pyvsc (Python Verification Stimulus and Coverage).

## ⚠️ Important Notice

This is a **Translation Assistant**, not an automated converter. The generated code requires **manual review and validation** by a verification engineer to ensure semantic equivalence.

## Features

- **Parses SystemVerilog** constraint classes, enums, and hierarchies
- **Generates pyvsc code** with proper decorators and type mappings
- **Translates constraint constructs**:
  - `rand`/`randc` fields
  - `inside` range constraints
  - Implications (`->`)
  - Conditional constraints (`if/else`)
  - Weighted distributions (`dist`)
  - Solve order (`solve before`)
  - Unique constraints
  - Foreach loops
  - Soft constraints
  - Array constraints
- **Preserves original SV** as documentation in generated code
- **Flags items requiring manual review**
- **Provides translation report** with statistics and warnings

## Installation

```bash
# Clone or download the tool
cd sv_to_pyvsc_translator

# Install pyvsc (required for running generated code)
pip install pyvsc
```

## Usage

### Command Line

```bash
# Basic translation (output to stdout)
python sv_to_pyvsc.py input.sv

# Save to file
python sv_to_pyvsc.py input.sv -o output.py

# With translation report
python sv_to_pyvsc.py input.sv -o output.py -r

# Quiet mode (suppress stdout, just save file)
python sv_to_pyvsc.py input.sv -o output.py -q
```

### Python API

```python
from sv_to_pyvsc import SVtoPyVSCTranslator

# Create translator
translator = SVtoPyVSCTranslator()

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
print(result.pyvsc_code)       # Generated Python code
print(result.warnings)          # Translation warnings
print(result.manual_review_items)  # Items needing review
print(result.statistics)        # Translation statistics

# Print detailed report
translator.print_report(result)
```

## Translation Mapping Reference

### Data Types

| SystemVerilog | pyvsc (Random) | pyvsc (Non-Random) |
|---------------|----------------|---------------------|
| `rand bit [N-1:0]` | `vsc.rand_bit_t(N)` | `vsc.bit_t(N)` |
| `randc bit [N-1:0]` | `vsc.randc_bit_t(N)` | N/A |
| `rand int` | `vsc.rand_int32_t()` | `vsc.int32_t()` |
| `rand enum` | `vsc.rand_enum_t(EnumType)` | `vsc.enum_t(EnumType)` |
| `rand T arr[N]` | `vsc.rand_list_t(T, sz=N)` | `vsc.list_t(T, sz=N)` |
| `rand T arr[]` | `vsc.rand_list_t(T)` | `vsc.list_t(T)` |

### Constraints

| SystemVerilog | pyvsc |
|---------------|-------|
| `inside {[a:b]}` | `x in vsc.rangelist(vsc.rng(a, b))` |
| `inside {v1, v2}` | `x in vsc.rangelist(v1, v2)` |
| `A -> B` | `vsc.implies(A, B)` |
| `if (c) {...}` | `with vsc.if_then(c): ...` |
| `else {...}` | `with vsc.else_then: ...` |
| `dist {v := w}` | `vsc.dist(x, [vsc.weight(v, w)])` |
| `solve a before b` | `vsc.solve_order(a, b)` |
| `unique {arr}` | `vsc.unique(arr)` |
| `foreach (a[i])` | `with vsc.foreach(a, idx=True) as i:` |
| `soft x == v` | `vsc.soft(x == v)` |

## Known Limitations

The tool handles most common SV constructs but has limitations:

1. **Bit slicing** (`x[7:4]`) - Converted to shifts/masks, requires verification
2. **Complex nested conditionals** - May need restructuring
3. **Bidirectional implications** (`<->`) - Requires two `vsc.implies()` calls
4. **Enum references in distributions** - Need proper enum class prefix
5. **Logical operators** (`&&`, `||`) - Need `vsc.and_()`, `vsc.or_()`
6. **Loop variables** in foreach - May get incorrect `self.` prefix

## Output Structure

Generated files include:

1. **File header** with review instructions
2. **Enum definitions** as Python IntEnum classes
3. **Class definitions** with `@vsc.randobj` decorator
4. **Field declarations** in `__init__`
5. **Constraint methods** with `@vsc.constraint` decorator
6. **Original SV code** preserved in docstrings
7. **Usage example** at the bottom

## Validation

The tool includes validation utilities:

```python
from validation_utils import PyVSCValidator

validator = PyVSCValidator(MyTransactionClass)
results = validator.validate_all(iterations=10000)
validator.print_report()
```

### Available Validation Tests

- Basic randomization correctness
- Value distribution analysis
- Boundary value testing
- Custom constraint invariants
- Distribution weight verification
- Seed reproducibility

## Project Structure

```
sv_to_pyvsc_translator/
├── sv_to_pyvsc.py          # Main translator
├── validation_utils.py      # Validation utilities
├── run_demo.py             # Demo runner
├── README.md               # This file
└── examples/
    ├── example_sv_classes.sv    # Example SV input
    └── translated_output.py     # Example output
```

## Best Practices

1. **Always review generated code** - Don't assume it's correct
2. **Verify constraint semantics** - Run statistical tests
3. **Check enum references** - Ensure proper class prefixes
4. **Test boundary conditions** - Validate edge cases
5. **Compare distributions** - Match SV simulation results
6. **Use seed control** - Ensure reproducibility

## Example

### Input (SystemVerilog)

```systemverilog
class axi_transaction;
    rand bit [31:0] addr;
    rand bit [7:0]  len;
    
    constraint addr_align_c {
        (addr % 4) == 0;  // 4-byte aligned
    }
    
    constraint len_dist_c {
        len dist {
            [0:3]   := 60,
            [4:15]  := 40
        };
    }
endclass
```

### Output (pyvsc)

```python
@vsc.randobj
class AxiTransaction:
    def __init__(self):
        self.addr = vsc.rand_bit_t(32)
        self.len = vsc.rand_bit_t(8)
    
    @vsc.constraint
    def addr_align_c(self):
        (self.addr % 4) == 0
    
    @vsc.constraint
    def len_dist_c(self):
        vsc.dist(self.len, [
            vsc.weight(vsc.rng(0, 3), 60),
            vsc.weight(vsc.rng(4, 15), 40),
        ])
```

## License

MIT License

## Contributing

Contributions welcome! Please ensure all translations maintain semantic fidelity with the original SystemVerilog.
