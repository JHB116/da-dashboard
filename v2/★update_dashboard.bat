@echo off
rem DA dashboard v2 - update to the latest version (downloads main ZIP from GitHub, replaces da-dashboard-main)
rem Put this .bat in the folder that holds da-dashboard-main (next to the other make_*.bat), then double-click.
rem Your backups, raw files and cache inside v2 are kept.
setlocal
set "HERE=%~dp0"
if exist "%HERE%build_data.py" (
  echo This .bat is inside the v2 folder. Copy it to the folder that holds da-dashboard-main, then run it there.
  pause
  exit /b 1
)
set "PS1=%HERE%da-dashboard-main\v2\update_dashboard.ps1"
if not exist "%PS1%" (
  echo [ERROR] da-dashboard-main\v2\update_dashboard.ps1 not found next to this .bat.
  echo Download the ZIP from GitHub once by hand and unzip it here as da-dashboard-main.
  pause
  exit /b 1
)
copy /y "%PS1%" "%TEMP%\da_update_dashboard.ps1" >nul
cd /d "%HERE%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\da_update_dashboard.ps1" -Dst "%HERE%da-dashboard-main" -BatDir "%HERE%."
echo.
pause
