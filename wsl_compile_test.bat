@echo off
setlocal

cd /d "%~dp0"

wsl -d Ubuntu -- bash -lc "cd /mnt/c/D/Project_Files/Samsung/SystemVerilogToPython && python3 sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py && python3 -m py_compile example_sv_classes.py"
