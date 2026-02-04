@echo off
setlocal

cd /d "%~dp0"

python sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py
