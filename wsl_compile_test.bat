@echo off
setlocal

cd /d "%~dp0"

set "LOG=wsl_compile_test.log"

echo [START] > "%LOG%"
echo Running translation and compile in WSL Ubuntu... >> "%LOG%"

wsl -d Ubuntu -- bash -lc "set -e; cd /mnt/c/D/Project_Files/Samsung/SystemVerilogToPython; echo '[STEP] Translate SV -> Python'; python3 sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py; echo '[STEP] Compile generated Python'; python3 -m py_compile example_sv_classes.py; echo '[DONE] OK'" >> "%LOG%" 2>&1

set "RC=%ERRORLEVEL%"
echo [END] Exit code %RC% >> "%LOG%"

type "%LOG%"
exit /b %RC%
