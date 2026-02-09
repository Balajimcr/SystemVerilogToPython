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

:: Robust parser using PowerShell (handles spaces and comments)
for /f "usebackq delims=" %%L in (`
    powershell -NoProfile -Command ^
    "Get-Content -LiteralPath '%ENV_FILE%' |" ^
    "ForEach-Object { $_.Trim() } |" ^
    "Where-Object { $_ -and -not $_.StartsWith('#') } |" ^
    "ForEach-Object { $k,$v = $_ -split '=',2; if($v){ $k.Trim() + '=' + $v.Trim() } }"
`) do set "%%L"

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

echo Using paths from Env.csh:
echo   WSL_PROJECT_PATH = %WSL_PROJECT_PATH%
echo   WSL_VENV_PATH    = %WSL_VENV_PATH%
echo   WSL_DISTRO       = %WSL_DISTRO%
echo.

echo ============================================
echo Step 1: Translating SystemVerilog to PyVSC
echo ============================================
wsl -d %WSL_DISTRO% -- bash -lc "cd %WSL_PROJECT_PATH% && . %WSL_VENV_PATH%/bin/activate && python sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py"

echo.
echo ============================================
echo Step 2: Testing PyVSC randomization
echo ============================================
wsl -d %WSL_DISTRO% -- bash -lc "cd %WSL_PROJECT_PATH% && . %WSL_VENV_PATH%/bin/activate && python example_sv_classes.py"

echo.
echo ============================================
echo Step 3: Generating 10 test vectors
echo ============================================
:: Use full HW field path so WSL can find it regardless of cwd
wsl -d %WSL_DISTRO% -- bash -lc "cd %WSL_PROJECT_PATH% && . %WSL_VENV_PATH%/bin/activate && python generate_test_vectors.py example_sv_classes IspYuv2rgbCfg %WSL_PROJECT_PATH%/hw_field.txt 10 ./output --seed 12345"

echo.
echo ============================================
echo Done! Check ./output directory for results
echo ============================================
pause
