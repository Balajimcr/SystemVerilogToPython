#!/usr/bin/env bash
# compile_test.sh — 3-step SV-to-PyVSC pipeline test
# Equivalent of wsl_compile_test.bat but for native Linux (no WSL, no venv)
#
# Steps:
#   1. Translate SystemVerilog to PyVSC Python
#   2. Run PyVSC randomization test
#   3. Generate 10 test vectors

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Using project directory: $SCRIPT_DIR"
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
echo "Step 3: Generating 10 test vectors"
echo "============================================"
python3 generate_test_vectors.py example_sv_classes IspYuv2rgbCfg \
    "$SCRIPT_DIR/hw_field.txt" 10 ./output --seed 12345

echo
echo "============================================"
echo "Done! Check ./output directory for results"
echo "============================================"
