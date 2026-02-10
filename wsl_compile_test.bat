@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: ============================================
:: Derive WIN_PROJECT_PATH from script location
:: ============================================
:: %~dp0 has a trailing backslash, remove it
set "WIN_PROJECT_PATH=%~dp0"
if "%WIN_PROJECT_PATH:~-1%"=="\" set "WIN_PROJECT_PATH=%WIN_PROJECT_PATH:~0,-1%"

:: ============================================
:: Derive WSL_PROJECT_PATH from WIN_PROJECT_PATH
:: Convert  C:\Foo\Bar  ->  /mnt/c/Foo/Bar
:: ============================================
:: Extract drive letter, lowercase it
set "DRIVE_LETTER=%WIN_PROJECT_PATH:~0,1%"
:: Lowercase the drive letter using a for trick
for %%A in (a b c d e f g h i j k l m n o p q r s t u v w x y z) do (
    if /i "%DRIVE_LETTER%"=="%%A" set "DRIVE_LETTER=%%A"
)
:: Build the WSL path: /mnt/<drive>/<rest with forward slashes>
set "REST_PATH=%WIN_PROJECT_PATH:~3%"
set "REST_PATH=%REST_PATH:\=/%"
set "WSL_PROJECT_PATH=/mnt/%DRIVE_LETTER%/%REST_PATH%"

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

:: Verify required variables from Env.csh
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

:: ============================================
:: Auto-update Env.csh paths to match current directory
:: ============================================
:: Update WIN_PROJECT_PATH in Env.csh to current script location
powershell -NoProfile -Command ^
    "$f = '%ENV_FILE%';" ^
    "$lines = Get-Content -LiteralPath $f;" ^
    "$newWin = '%WIN_PROJECT_PATH%';" ^
    "$newWsl = '%WSL_PROJECT_PATH%';" ^
    "$lines = $lines -replace '^(WIN_PROJECT_PATH\s*=\s*).*$', \"$('$1')$newWin\";" ^
    "$lines = $lines -replace '^(WSL_PROJECT_PATH\s*=\s*).*$', \"$('$1')$newWsl\";" ^
    "Set-Content -LiteralPath $f -Value $lines"

echo Using configuration:
echo   WIN_PROJECT_PATH = %WIN_PROJECT_PATH%  (auto-detected)
echo   WSL_PROJECT_PATH = %WSL_PROJECT_PATH%  (derived from Windows path)
echo   WSL_VENV_PATH    = %WSL_VENV_PATH%     (from Env.csh)
echo   WSL_DISTRO       = %WSL_DISTRO%        (from Env.csh)
echo.

echo ============================================
echo Step 1: Translating SystemVerilog to PyVSC
echo ============================================
wsl -d %WSL_DISTRO% -- bash -lc "cd %WSL_PROJECT_PATH% && . %WSL_VENV_PATH%/bin/activate && python sv_to_pyvsc.py isp_yuv2rgb.sv -o isp_yuv2rgb.py"

echo.
echo ============================================
echo Step 2: Testing PyVSC randomization
echo ============================================
wsl -d %WSL_DISTRO% -- bash -lc "cd %WSL_PROJECT_PATH% && . %WSL_VENV_PATH%/bin/activate && python isp_yuv2rgb.py"

echo.
echo ============================================
echo Step 3: Generating 10 test vectors
echo ============================================
:: Use full HW field path so WSL can find it regardless of cwd
wsl -d %WSL_DISTRO% -- bash -lc "cd %WSL_PROJECT_PATH% && . %WSL_VENV_PATH%/bin/activate && python generate_test_vectors.py isp_yuv2rgb IspYuv2rgbCfg %WSL_PROJECT_PATH%/hw_field.txt 10 ./output --seed 12345"

echo.
echo ============================================
echo Done! Check ./output directory for results
echo ============================================
pause
