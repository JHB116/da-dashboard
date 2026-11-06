# DA dashboard v2 - update: download the latest main ZIP from GitHub and replace the da-dashboard-main folder.
# Keeps v2\backup, v2\raw, v2\data (cache) and v2\.streamlit\secrets.toml. Copies the new make_*.bat next to the updater.
param([Parameter(Mandatory = $true)][string]$Dst, [string]$OldV2 = '', [string]$BatDir = '')
$ErrorActionPreference = 'Stop'
$url = 'https://github.com/JHB116/da-dashboard/archive/refs/heads/main.zip'
$zip = Join-Path $env:TEMP 'da-dashboard-main.zip'
$tmp = Join-Path $env:TEMP 'da-dashboard-update'
$Dst = [IO.Path]::GetFullPath($Dst.TrimEnd('\'))
$old = $Dst + '_old'
if (-not $OldV2) { $OldV2 = Join-Path $Dst 'v2' }   # where the current v2 is (may be one level deeper if the ZIP was unzipped twice)
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Write-Host "[1/4] Downloading the latest version from GitHub..."
  $ProgressPreference = 'SilentlyContinue'
  Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
  Write-Host "[2/4] Unzipping..."
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
  Expand-Archive -Path $zip -DestinationPath $tmp -Force
  $new = Join-Path $tmp 'da-dashboard-main'
  if (-not (Test-Path (Join-Path $new 'v2\build_data.py'))) { throw 'The downloaded ZIP does not contain v2\build_data.py' }
  Write-Host "[3/4] Keeping your backups / raw files / cache..."
  foreach ($k in @('backup', 'raw', 'data', '.streamlit\secrets.toml')) {
    $src = Join-Path $OldV2 $k
    if (Test-Path $src) {
      $to = Join-Path (Join-Path $new 'v2') $k
      $parent = Split-Path $to -Parent
      if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
      if (Test-Path $to) { Remove-Item $to -Recurse -Force }
      Copy-Item -Path $src -Destination $to -Recurse -Force
    }
  }
  Write-Host "[4/4] Replacing the folder..."
  if (Test-Path $old) { Remove-Item $old -Recurse -Force }
  if (Test-Path $Dst) { Rename-Item -Path $Dst -NewName (Split-Path $old -Leaf) }
  try { Move-Item -Path $new -Destination $Dst }
  catch { if (Test-Path $old) { Rename-Item -Path $old -NewName (Split-Path $Dst -Leaf) }; throw }
  if (Test-Path $old) { Remove-Item $old -Recurse -Force -ErrorAction SilentlyContinue }
  if ($BatDir) {
    # new backup .bat files next to the updater (the updater itself is left as is while it runs)
    Get-ChildItem -Path (Join-Path $Dst 'v2') -Filter '*make_*.bat' | ForEach-Object { Copy-Item $_.FullName -Destination $BatDir -Force }
  }
  Remove-Item $zip -Force -ErrorAction SilentlyContinue
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  Write-Host ""
  Write-Host "Done. Updated: $Dst"
  exit 0
}
catch {
  Write-Host ""
  Write-Host "[ERROR] update failed: $($_.Exception.Message)"
  Write-Host "Your current folder was not removed. Close any open file in da-dashboard-main (Excel, Explorer preview) and try again,"
  Write-Host "or download the ZIP from GitHub by hand."
  exit 1
}
