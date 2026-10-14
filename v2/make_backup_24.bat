@echo off
rem DA dashboard v2 - 24 raw file (once). Drag the 24 raw file onto this .bat.
rem Only dates up to 2024-12-31 are used and kept fixed.
setlocal
set "HERE=%~dp0"
set PYTHONIOENCODING=utf-8
set PY=python
where python >nul 2>nul || set PY=py
%PY% -c "import pandas, pyxlsb, openpyxl" >nul 2>nul || %PY% -m pip install -r "%HERE%requirements.txt"
if "%~1"=="" (
  echo Drag the 24 raw file [xlsb / csv / xlsx] onto this .bat icon.
  pause
  exit /b 0
)
%PY% "%HERE%build_data.py" --y24 %*
if errorlevel 1 (
  echo.
  echo [ERROR] backup build failed. See the message above.
  pause
  exit /b 1
)
echo.
echo Done. Drag the newest file in the "backup" folder onto the dashboard (once).
start "" explorer "%HERE%backup"
pause
