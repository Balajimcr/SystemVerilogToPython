#!/usr/bin/env bash
# run_gui.sh — Launch the SV/XML to PyVSC Translation GUI
# Equivalent of run_gui.bat (no venv, native Linux)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

python3 sv_to_pyvsc_gui.py
