@echo off
setlocal

cd /d "%~dp0"

echo ============================================
echo Step 1: Translating SystemVerilog to PyVSC
echo ============================================
wsl -d Ubuntu -- bash -lc "cd /mnt/c/D/Project_Files/Samsung/SystemVerilogToPython && . .wsl_venv/bin/activate && python sv_to_pyvsc.py example_sv_classes.sv -o example_sv_classes.py"

echo.
echo ============================================
echo Step 2: Testing PyVSC randomization
echo ============================================
wsl -d Ubuntu -- bash -lc "cd /mnt/c/D/Project_Files/Samsung/SystemVerilogToPython && . .wsl_venv/bin/activate && python example_sv_classes.py"

echo.
echo ============================================
echo Step 3: Generating 10 test vectors
echo ============================================
wsl -d Ubuntu -- bash -lc "cd /mnt/c/D/Project_Files/Samsung/SystemVerilogToPython && . .wsl_venv/bin/activate && python generate_test_vectors.py example_sv_classes IspYuv2rgbCfg hw_field.txt 10 ./output --seed 12345"

echo.
echo ============================================
echo Done! Check ./output directory for results
echo ============================================
pause
