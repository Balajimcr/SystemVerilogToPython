@echo off
setlocal

cd /d "%~dp0"

rem --------------------------------------------------------------------
rem Convert this script directory (Windows path) to the corresponding
rem WSL path (e.g. C:\path -> /mnt/c/path) and store in WSL_PROJECT_DIR.
rem This avoids hard-coded project paths.
rem --------------------------------------------------------------------
set "WIN_DIR=%~dp0"
if "%WIN_DIR:~-1%"=="\" set "WIN_DIR=%WIN_DIR:~0,-1%"

rem Basic validation: ensure the Windows directory exists
if not exist "%WIN_DIR%\" (
    echo Error: script directory does not exist: "%WIN_DIR%"
    exit /b 1
)

set "DRIVE_LETTER=%WIN_DIR:~0,1%"
set "PATH_NO_DRIVE=%WIN_DIR:~3%"
set "UNIX_PATH=%PATH_NO_DRIVE:\=/=%"
set "WSL_PROJECT_DIR=/mnt/%DRIVE_LETTER%/%UNIX_PATH%"

echo Computed WSL project directory: %WSL_PROJECT_DIR%

rem Verify the WSL path exists by asking WSL to test it. If it does not exist,
rem print a helpful error and exit early.
wsl -d Ubuntu -- bash -lc "if [ ! -d '%WSL_PROJECT_DIR%' ]; then echo 'Error: WSL project directory not found: %WSL_PROJECT_DIR%'; exit 2; fi"
if ERRORLEVEL 1 (
    echo Aborting: WSL project directory validation failed.
    exit /b 1
)

echo ============================================
echo Step 1: Translating SystemVerilog to PyVSC
echo ============================================
wsl -d Ubuntu -- bash -lc "cd '%WSL_PROJECT_DIR%' && . .wsl_venv/bin/activate && python sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py"

echo.
echo ============================================
echo Step 2: Testing PyVSC randomization
echo ============================================
wsl -d Ubuntu -- bash -lc "cd '%WSL_PROJECT_DIR%' && . .wsl_venv/bin/activate && python example_sv_classes.py"

echo.
echo ============================================
echo Step 3: Generating 10 test vectors
echo ============================================
wsl -d Ubuntu -- bash -lc "cd '%WSL_PROJECT_DIR%' && . .wsl_venv/bin/activate && python generate_test_vectors.py example_sv_classes IspYuv2rgbCfg hw_field.txt 10 ./output --seed 12345"

echo.
echo ============================================
echo Done! Check ./output directory for results
echo ============================================
pause
