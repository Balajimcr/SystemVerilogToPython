@echo off
set PATH=C:\Tools\Python39;%PATH%
set PATH=C:\Tools\Java\jdk-11.0.10\bin;%PATH%
python -m unittest discover -s tests -p "*_test.py"
echo Test complete. Please check the results.