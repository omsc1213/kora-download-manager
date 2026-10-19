param([Parameter(ValueFromRemainingArguments=$true)][string[]]$KoraArguments)
$ErrorActionPreference='Stop'
$candidates=@($env:KORA_PYTHON,(Join-Path $PSScriptRoot 'runtime\python.exe'))
$pointer=Join-Path $PSScriptRoot 'python-path.txt'
if (Test-Path -LiteralPath $pointer) { $candidates+= (Get-Content -LiteralPath $pointer -Raw).Trim() }
$pythonPath=$candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (-not $pythonPath) {
    $found=Get-Command python.exe -ErrorAction SilentlyContinue
    if ($found -and $found.Source -notlike '*WindowsApps*') { $pythonPath=$found.Source }
}
if (-not $pythonPath -and (Get-Command py.exe -ErrorAction SilentlyContinue)) {
    $pythonPath=(& py.exe -3 -c 'import sys;print(sys.executable)' 2>$null | Select-Object -First 1)
}
if (-not $pythonPath) { throw 'Run Setup.cmd, or install Python 3.10+ with Tcl/Tk support.' }
& $pythonPath (Join-Path $PSScriptRoot 'kora.py') @KoraArguments
exit $LASTEXITCODE
