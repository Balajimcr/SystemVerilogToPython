@echo off
setlocal

cd /d "%~dp0"

set "DEFAULT_WIN_PATH=%~dp0"
if "%DEFAULT_WIN_PATH:~-1%"=="\" set "DEFAULT_WIN_PATH=%DEFAULT_WIN_PATH:~0,-1%"

set /p USER_WIN_PATH=Enter Windows project path [%DEFAULT_WIN_PATH%]: 
if "%USER_WIN_PATH%"=="" set "USER_WIN_PATH=%DEFAULT_WIN_PATH%"

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
