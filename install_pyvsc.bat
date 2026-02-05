@echo off
setlocal

SET ENV_NAME=pyvsc_venv
SET PYTHON_VER=3.10

:: This script uses WSL to install PyVSC in a Linux venv.
:: Ensure WSL + a Linux distro are installed (Ubuntu recommended).

echo Creating WSL venv: %ENV_NAME% (Python %PYTHON_VER%)...

:: Run everything inside WSL bash (single line to avoid quoting EOF issues)
set "WSL_CMD=set -e; cd /mnt/c/D/Project_Files/Samsung/SystemVerilogToPython; if [ ! -d .wsl_venv ]; then python%PYTHON_VER% -m venv .wsl_venv; fi; source .wsl_venv/bin/activate; python -m pip install --force-reinstall --no-deps pip==24.0; python -m pip install setuptools wheel; echo \"Installing pyvsc (this may build pyboolector)...\"; python -m pip install pyvsc; python -c \"import vsc; print('SUCCESS: PyVSC is now working in WSL!')\""
wsl -d Ubuntu -- bash -lc "%WSL_CMD%"

if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] WSL install failed. Verify WSL is installed and the Ubuntu distro name is correct.
    echo If your distro isn't Ubuntu, replace 'Ubuntu' above with your distro name.
)

pause
