@echo off
setlocal

cd /d "%~dp0"

wsl -d Ubuntu -- bash -lc "cd /mnt/c/D/Project_Files/Samsung/SystemVerilogToPython && . .wsl_venv/bin/activate && python sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py && python example_sv_classes.py"
