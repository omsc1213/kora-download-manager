param([Parameter(Mandatory=$true)][string]$PythonExe)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$folder=Join-Path $root ('test-work/startup-'+[guid]::NewGuid().ToString('N'))
$installed=Join-Path $folder 'Installed Kora'
$shell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
New-Item -ItemType Directory -Force $folder | Out-Null
& $shell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'Install-Kora.ps1') -Destination $installed -PythonExe $PythonExe -NoShortcuts -NoLaunch -SkipVideoTools
if ($LASTEXITCODE -ne 0) { throw 'Install with explicit Python failed' }
$data=Join-Path $installed 'data'
New-Item -ItemType Directory -Force $data | Out-Null
$sentinel=Join-Path $data 'upgrade-sentinel.txt'
[IO.File]::WriteAllText($sentinel,'preserve user data')
& $shell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'Install-Kora.ps1') -Destination $installed -NoShortcuts -NoLaunch -SkipVideoTools
if ($LASTEXITCODE -ne 0) { throw 'Upgrade using saved Python failed' }
if ((Get-Content -Raw $sentinel) -ne 'preserve user data') { throw 'Upgrade changed user data' }
$version=& $shell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $installed 'Launch-Kora.ps1') --version
if ($LASTEXITCODE -ne 0 -or $version -ne 'Kora 0.4.2') { throw 'Installed launcher failed' }
$result=& $shell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $installed 'Launch-Kora.ps1') doctor
if ($LASTEXITCODE -ne 0 -or -not ($result | ConvertFrom-Json).startup_ready) { throw 'Installed desktop readiness failed' }
# Exercise the failure path without a desktop message box or network access.
$empty=Join-Path $folder 'No Python'
New-Item -ItemType Directory -Force $empty | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'Launch-Kora.ps1') -Destination $empty
$savedPath=$env:PATH;$savedPython=$env:KORA_PYTHON;$savedData=$env:KORA_DATA_DIR
try {
    $env:PATH='';$env:KORA_PYTHON='';$env:KORA_DATA_DIR=Join-Path $empty 'data'
    $ErrorActionPreference='Continue'
    & $shell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $empty 'Launch-Kora.ps1') --version 2>$null
    $failed=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    if ($failed -eq 0) { throw 'Missing Python should fail' }
    if ((Get-Content -Raw (Join-Path $empty 'data/startup.log')) -notmatch 'Run Setup.cmd') { throw 'Missing actionable startup log' }
} finally { $env:PATH=$savedPath;$env:KORA_PYTHON=$savedPython;$env:KORA_DATA_DIR=$savedData }
Write-Output 'Startup checks passed: install, upgrade, saved Python, paths with spaces, preserved data, readiness and missing-Python log.'
