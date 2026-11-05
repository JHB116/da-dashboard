@echo off
rem DA dashboard v2 - target file (report xlsx). Drag the target xlsx onto this .bat when targets change.
setlocal
set "HERE=%~dp0"
set PYTHONIOENCODING=utf-8
set PY=python
where python >nul 2>nul || set PY=py
%PY% -c "import pandas, openpyxl" >nul 2>nul || %PY% -m pip install -r "%HERE%requirements.txt"
if "%~1"=="" (
  echo Drag the target file [report .xlsx] onto this .bat icon.
  pause
  exit /b 0
)
%PY% "%HERE%build_data.py" --targets "%~1"
if errorlevel 1 (
  echo.
  echo [ERROR] target file could not be read. See the message above.
  pause
  exit /b 1
)
echo.
echo Done. Drag the newest file in the "backup" folder onto the dashboard.
start "" explorer "%HERE%backup"
pause
