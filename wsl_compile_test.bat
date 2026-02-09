@echo off
rem Replace hardcoded paths with relative paths using %~dp0
set REL_PATH=%~dp0..elative_directory\

rem Example of using the relative path
\path\to\your\executable.exe %REL_PATH%inputfile.txt
