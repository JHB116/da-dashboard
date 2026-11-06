@echo off
rem DA dashboard v2 - 24 raw file (once). Drag the 24 raw file onto this .bat.
rem Only dates up to 2024-12-31 are used and kept fixed.
setlocal
set "HERE=%~dp0"
rem If this .bat was moved out of the v2 folder, look for v2 in the folders next to it
if not exist "%HERE%build_data.py" for /d %%D in ("%HERE%*") do if exist "%%~fD\v2\build_data.py" set "HERE=%%~fD\v2\"
if not exist "%HERE%build_data.py" for /d %%D in ("%HERE%*") do if exist "%%~fD\build_data.py" set "HERE=%%~fD\"
rem ZIP unzipped one level deeper (da-dashboard-main\da-dashboard-main\v2)
if not exist "%HERE%build_data.py" for /d %%D in ("%HERE%*") do for /d %%E in ("%%~fD\*") do if exist "%%~fE\v2\build_data.py" set "HERE=%%~fE\v2\"
if not exist "%HERE%build_data.py" (
  echo [ERROR] build_data.py not found. Keep this .bat in the v2 folder, or in the folder that holds da-dashboard-main.
  pause
  exit /b 1
)
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
