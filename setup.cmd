@echo off
setlocal
set PYTHONUTF8=1
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 "%~dp0bootstrap.py"
exit /b %errorlevel%
:use_python
python "%~dp0bootstrap.py"
exit /b %errorlevel%
