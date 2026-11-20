param([Parameter(ValueFromRemainingArguments=$true)][string[]]$KoraArguments)
$ErrorActionPreference='Stop'
$guiLaunch=($KoraArguments.Count -eq 0 -or $KoraArguments[0] -eq 'gui')
$logRoot=if ($env:KORA_DATA_DIR) { $env:KORA_DATA_DIR } else { Join-Path $PSScriptRoot 'data' }
$log=Join-Path $logRoot 'startup.log'
try {
    $candidates=@($env:KORA_PYTHON,(Join-Path $PSScriptRoot 'runtime\python.exe'))
    $pointer=Join-Path $PSScriptRoot 'python-path.txt'
    if (Test-Path -LiteralPath $pointer) { $candidates+= (Get-Content -LiteralPath $pointer -Raw).Trim() }
    $found=Get-Command python.exe -ErrorAction SilentlyContinue
    if ($found -and $found.Source -notlike '*WindowsApps*') { $candidates+= $found.Source }
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        try { $candidate=& py.exe -3 -c 'import sys;print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0) { $candidates+= ($candidate | Select-Object -First 1) }
        } catch { }
    }
    $pythonPath=$null
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not $candidate -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        try {
            & $candidate -I -c 'import sys,tkinter,sqlite3,ssl;assert sys.version_info >= (3,10)' 2>$null
            if ($LASTEXITCODE -eq 0) { $pythonPath=$candidate;break }
        } catch { }
    }
    if (-not $pythonPath) { throw 'A working Python 3.10+ with Tcl/Tk was not found. Run Setup.cmd from the extracted Kora folder.' }
    $env:PYTHONUTF8='1'
    if ($guiLaunch) {
        New-Item -ItemType Directory -Force $logRoot | Out-Null
        $oldPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
        & $pythonPath (Join-Path $PSScriptRoot 'kora.py') @KoraArguments *> $log
        $code=$LASTEXITCODE;$ErrorActionPreference=$oldPreference
        if ($code -ne 0) { throw "Kora could not start. Details were saved to $log. Run Setup.cmd to repair the installation." }
    } else {
        & $pythonPath (Join-Path $PSScriptRoot 'kora.py') @KoraArguments
        $code=$LASTEXITCODE
    }
    exit $code
} catch {
    $message=$_.Exception.Message
    try { New-Item -ItemType Directory -Force $logRoot | Out-Null;Add-Content -LiteralPath $log -Value $message } catch { }
    if ($guiLaunch) {
        try { Add-Type -AssemblyName PresentationFramework;[System.Windows.MessageBox]::Show($message,'Kora startup problem') | Out-Null } catch { }
    }
    [Console]::Error.WriteLine($message)
    exit 1
}