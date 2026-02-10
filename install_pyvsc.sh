#!/usr/bin/env bash
# install_pyvsc.sh — Install PyVSC system-wide (no venv)
# Equivalent of install_pyvsc.bat but for native Linux
#
# Prerequisites: Python 3.x with pip installed

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo " Installing PyVSC (native Linux, no venv)"
echo "============================================"
echo

# Ensure pip is up to date
python3 -m pip install --upgrade pip setuptools wheel

echo
echo "Installing pyvsc (this may build pyboolector)..."
python3 -m pip install pyvsc

echo
echo "============================================"
echo " Verifying installation"
echo "============================================"
python3 -c "import vsc; print('SUCCESS: PyVSC is installed and working!')"
