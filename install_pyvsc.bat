@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: ============================================
:: Read environment config from Env.csh
:: ============================================
set "ENV_FILE=%~dp0Env.csh"
if not exist "%ENV_FILE%" (
    echo [ERROR] Env.csh not found at: %ENV_FILE%
    echo Please create Env.csh with your path configuration.
    pause
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    set "KEY=%%A"
    set "VAL=%%B"
    :: Skip comment lines (# prefix)
    set "FIRST=!KEY:~0,1!"
    if not "!FIRST!"=="#" (
        if defined VAL (
            :: Trim leading/trailing spaces from key and value
            for /f "tokens=*" %%K in ("!KEY!") do set "KEY=%%K"
            for /f "tokens=*" %%V in ("!VAL!") do set "VAL=%%V"
            set "!KEY!=!VAL!"
        )
    )
)

:: Verify required variables
if not defined WSL_PROJECT_PATH (
    echo [ERROR] WSL_PROJECT_PATH not set in Env.csh
    pause
    exit /b 1
)
if not defined WSL_VENV_PATH (
    echo [ERROR] WSL_VENV_PATH not set in Env.csh
    pause
    exit /b 1
)
if not defined WSL_DISTRO (
    echo [ERROR] WSL_DISTRO not set in Env.csh
    pause
    exit /b 1
)
if not defined WSL_PYTHON_VERSION (
    echo [ERROR] WSL_PYTHON_VERSION not set in Env.csh
    pause
    exit /b 1
)

:: This script uses WSL to install PyVSC in a Linux venv.
:: Ensure WSL + a Linux distro are installed (Ubuntu recommended).

echo Creating WSL venv: %WSL_VENV_PATH% (Python %WSL_PYTHON_VERSION%) in distro: %WSL_DISTRO%
echo   WSL_PROJECT_PATH = %WSL_PROJECT_PATH%
echo.

:: Run everything inside WSL bash (single line to avoid quoting EOF issues)
set "WSL_CMD=set -e; cd %WSL_PROJECT_PATH%; if [ ! -d %WSL_VENV_PATH% ]; then python%WSL_PYTHON_VERSION% -m venv %WSL_VENV_PATH%; fi; source %WSL_VENV_PATH%/bin/activate; python -m pip install --force-reinstall --no-deps pip==24.0; python -m pip install setuptools wheel; echo \"Installing pyvsc (this may build pyboolector)...\"; python -m pip install pyvsc; python -c \"import vsc; print('SUCCESS: PyVSC is now working in WSL!')\""
wsl -d %WSL_DISTRO% -- bash -lc "%WSL_CMD%"

if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] WSL install failed. Verify WSL is installed and the distro name is correct.
    echo Current distro setting: %WSL_DISTRO% (change in Env.csh if needed^)
)

pause
