@echo off
SET ENV_NAME=PyVSC_Conda
SET PYTHON_VER=3.10

:: 1. Find Anaconda Path
set CONDA_PATH=%UserProfile%\anaconda3
if not exist "%CONDA_PATH%" set CONDA_PATH=%ProgramData%\anaconda3
if not exist "%CONDA_PATH%" set CONDA_PATH=%UserProfile%\Miniconda3

:: 2. Create Environment
echo Creating environment %ENV_NAME%...
call "%CONDA_PATH%\Scripts\activate.bat"
call conda create -n %ENV_NAME% python=%PYTHON_VER% -y

:: 3. Activation
echo Activating %ENV_NAME%...
call conda activate %ENV_NAME%

:: 4. Downgrade Pip & Install Build Helpers
echo Preparing installation environment...
python -m pip install "pip<24.1"
pip install setuptools wheel

:: 5. Install pyvsc 
:: Using --use-pep517 can sometimes help with the newer compiler versions
echo Installing pyvsc (This may take a few minutes as it compiles pyboolector)...
pip install pyvsc --use-deprecated=legacy-resolver

:: 6. Verification
echo.
python -c "import vsc; print('SUCCESS: PyVSC is now working!')"
if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] If the error is still 'build failed', ensure you restarted after installing Visual Studio Build Tools.
)

pause
