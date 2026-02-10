#!/usr/bin/env bash
# run_example.sh — Translate the example SV file to PyVSC
# Equivalent of run_example.bat (no venv, native Linux)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

python3 sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py
