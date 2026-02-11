#!/usr/bin/env bash
# compile_test.sh — 4-step SV-to-PyVSC pipeline test
# Equivalent of wsl_compile_test.bat but for native Linux (no WSL, no venv)
#
# Steps:
#   0. Convert XML to SV (exports TopParameter CSV)
#   1. Translate SystemVerilog to PyVSC Python
#   2. Run PyVSC randomization test
#   3. Generate 10 test vectors (with TopParameter companion files)
#   4. Verify TopParameter companion files

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Using project directory: $SCRIPT_DIR"
echo

echo "============================================"
echo "Step 0: XML to SV conversion (TopParam CSV)"
echo "============================================"
python3 XML_to_sv_Converter.py sample_input.xml example_sv_classes.sv \
    example_sv_classes_top_params.csv

echo
echo "============================================"
echo "Step 1: Translating SystemVerilog to PyVSC"
echo "============================================"
python3 sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py

echo
echo "============================================"
echo "Step 2: Testing PyVSC randomization"
echo "============================================"
python3 example_sv_classes.py

echo
echo "============================================"
echo "Step 3: Generating 10 test vectors (with TopParameter companion files)"
echo "============================================"
# --top-params passes the TopParameter CSV so overrides are applied and
# companion config_NNNN_top_params.txt files are generated per run
python3 generate_test_vectors.py example_sv_classes IspYuv2rgbCfg \
    "$SCRIPT_DIR/hw_field.txt" 10 ./output --seed 12345 \
    --top-params "$SCRIPT_DIR/example_sv_classes_top_params.csv"

echo
echo "============================================"
echo "Step 4: Verify TopParameter companion files"
echo "============================================"
TOP_COUNT=$(find ./output -name "config_*_top_params.txt" 2>/dev/null | wc -l)
if [ "$TOP_COUNT" -gt 0 ]; then
    echo "[OK] Found $TOP_COUNT TopParameter companion file(s)"
    echo
    echo "Sample content (config_0000_top_params.txt):"
    echo "------------------------------------------------"
    if [ -f "./output/config_0000_top_params.txt" ]; then
        cat ./output/config_0000_top_params.txt
    fi
    echo "------------------------------------------------"
else
    echo "[WARNING] No TopParameter companion files found in ./output/"
fi

echo
echo "============================================"
echo "Done! Check ./output directory for results"
echo "  - config_NNNN.txt           : hw_field values per run"
echo "  - config_NNNN_top_params.txt: TopParameter values per run"
echo "============================================"
