@echo off
setlocal
cd /d "%~dp0"
where py.exe >nul 2>nul
if errorlevel 1 goto python_fallback
py.exe -3.12 -c "import sys; sys.exit(0)" >nul 2>nul
if errorlevel 1 goto python_fallback
py.exe -3.12 -X utf8 "%~dp0bootstrap.py"
if errorlevel 1 goto failed
exit /b 0
:python_fallback
where python.exe >nul 2>nul
if errorlevel 1 goto missing_python
python.exe -X utf8 "%~dp0bootstrap.py"
if errorlevel 1 goto failed
exit /b 0
:missing_python
echo Can cai Python 3.12 Windows 64-bit, bao gom Tcl/Tk.
:failed
pause
exit /b 1
