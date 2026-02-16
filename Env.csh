# ==============================================================================
# Env.csh - Environment Configuration for SV/XML to PyVSC Translation Tool
# ==============================================================================
#
# This file defines all path variables used by:
#   - wsl_compile_test.bat
#   - install_pyvsc.bat
#   - sv_to_pyvsc_gui.py
#
# FORMAT:  KEY = VALUE
#   - Lines starting with '#' are comments
#   - Blank lines are ignored
#   - Spaces around '=' are trimmed
#
# INSTRUCTIONS:
#   Update the values below to match your system setup.
#   Then all scripts will automatically pick up the correct paths.
# ==============================================================================

# --- Windows Script Path (where this project lives on Windows) ---
WIN_PROJECT_PATH = C:\D\Project_Files\Samsung\Design_Verification_Tool\SystemVerilogToPython

# --- WSL Project Path (same directory as seen from inside WSL) ---
WSL_PROJECT_PATH = /mnt/c/D/Project_Files/Samsung/Design_Verification_Tool/SystemVerilogToPython

# --- WSL Virtual Environment Path (relative to WSL_PROJECT_PATH) ---
WSL_VENV_PATH = .wsl_venv

# --- WSL Distro Name (the WSL distribution to use) ---
WSL_DISTRO = Ubuntu

# --- Python version for venv creation inside WSL ---
WSL_PYTHON_VERSION = 3.10
