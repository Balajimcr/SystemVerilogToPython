@echo off
setlocal

set "USER_WIN_PATH=%CD%"
if "%USER_WIN_PATH:~-1%"=="\" set "USER_WIN_PATH=%USER_WIN_PATH:~0,-1%"

cd /d "%~dp0"

if not exist "%~dp0update_env_csh.py" (
    echo [ERROR] update_env_csh.py not found in %~dp0
    pause
    exit /b 1
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=python"
) else (
    set "PYTHON_CMD=py -3"
)

%PYTHON_CMD% "%~dp0update_env_csh.py" --env-file "%~dp0Env.csh" --win-path "%USER_WIN_PATH%"
if errorlevel 1 (
    echo.
    echo [ERROR] Env update failed.
    pause
    exit /b 1
)

echo.
echo Env.csh updated and WSL venv check complete.
pause
