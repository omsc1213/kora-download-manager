param(
  [string]$Destination=(Join-Path $env:LOCALAPPDATA 'Programs\Kora'),
  [string]$PythonExe,
  [switch]$NoShortcuts,
  [switch]$NoLaunch,
  [switch]$SkipVideoTools
)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($Destination)
if ($target -eq $PSScriptRoot -or $target.TrimEnd('\') -eq [IO.Path]::GetPathRoot($target).TrimEnd('\')) { throw 'Choose a separate application folder, not a drive root or the extracted source folder.' }
function Test-KoraPython([string]$Candidate) {
    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }
    try {
        & $Candidate -I -c 'import sys,tkinter,sqlite3,ssl; assert sys.version_info >= (3,10); r=tkinter.Tk();r.withdraw();r.destroy()' 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
$pythonPath=$null
$candidates=@($PythonExe,(Join-Path $target 'runtime\python.exe'),$env:KORA_PYTHON)
$found=Get-Command python.exe -ErrorAction SilentlyContinue
if ($found -and $found.Source -notlike '*WindowsApps*') { $candidates+= $found.Source }
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    $candidate=& py.exe -3 -c 'import sys; print(sys.executable)' 2>$null
    if ($LASTEXITCODE -eq 0) { $candidates+= ($candidate | Select-Object -First 1) }
}
foreach ($candidate in $candidates) { if (Test-KoraPython $candidate) { $pythonPath=$candidate;break } }
if ($PythonExe -and -not $pythonPath) { throw 'The supplied Python executable must be Python 3.10+ with working Tcl/Tk, SQLite and SSL.' }
New-Item -ItemType Directory -Path $target -Force | Out-Null
if (-not $pythonPath) {
    Write-Output 'Python with Tcl/Tk is needed. Obtaining the official signed Windows installer...'
    [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
    $page=Invoke-WebRequest -Uri 'https://www.python.org/downloads/windows/' -UseBasicParsing
    $match=[regex]::Matches($page.Content,'https://www\.python\.org/ftp/python/(\d+\.\d+\.\d+)/python-\1-amd64\.exe') | Sort-Object { [version]$_.Groups[1].Value } -Descending | Select-Object -First 1
    if (-not $match) { throw 'Could not resolve the official stable Python installer. Install Python with Tcl/Tk from python.org and run Setup.cmd again.' }
    $cache=Join-Path $target 'setup-cache';New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $installer=Join-Path $cache 'python-installer.exe'
    Invoke-WebRequest -Uri $match.Value -OutFile $installer -UseBasicParsing
    $signature=Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'The Python installer signature/publisher could not be verified. Nothing was executed.' }
    $runtime=Join-Path $target 'runtime'
    $options=@('/quiet','InstallAllUsers=0',('TargetDir="'+$runtime+'"'),'Include_tcltk=1','Include_pip=0','Include_launcher=0','InstallLauncherAllUsers=0','Include_test=0','Include_doc=0','Include_dev=0','Shortcuts=0','AssociateFiles=0','PrependPath=0')
    $process=Start-Process -FilePath $installer -ArgumentList $options -PassThru -Wait -WindowStyle Hidden
    if ($process.ExitCode -notin @(0,3010)) { throw "Python setup failed with code $($process.ExitCode)." }
    $pythonPath=Join-Path $runtime 'python.exe'
    if (-not (Test-KoraPython $pythonPath)) { throw 'Python runtime verification failed. Run the official Python installer with Tcl/Tk enabled.' }
}
foreach ($entry in (Get-ChildItem -LiteralPath $PSScriptRoot -File)) {
    if ($entry.Name -in @('python-path.txt','settings.json','browser-host.json') -or $entry.Extension -in @('.db','.log','.zip')) { continue }
    Copy-Item -LiteralPath $entry.FullName -Destination $target -Force
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'browser') -Destination $target -Recurse -Force
[IO.File]::WriteAllText((Join-Path $target 'python-path.txt'),$pythonPath,(New-Object Text.UTF8Encoding($false)))
if (-not $SkipVideoTools) {
    & $pythonPath (Join-Path $target 'setup_video_tools.py')
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Kora is installed, but video-tool setup did not finish. Run Setup-Video-Tools.cmd inside the installed folder to retry.' }
}
if (-not $NoShortcuts) {
    $pythonw=Join-Path (Split-Path $pythonPath -Parent) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonw)) { $pythonw=$pythonPath }
    $shell=New-Object -ComObject WScript.Shell
    foreach ($folder in @([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('Desktop'))) {
        $shortcut=$shell.CreateShortcut((Join-Path $folder 'Kora Download Manager.lnk'))
        $shortcut.TargetPath=$pythonw;$shortcut.Arguments='"'+(Join-Path $target 'kora.py')+'"';$shortcut.WorkingDirectory=$target;$shortcut.Save()
    }
}
Write-Output "Installed Kora in $target. This public edition obtains third-party tools separately."
if (-not $NoLaunch) { Start-Process -FilePath $pythonPath -ArgumentList ('"'+(Join-Path $target 'kora.py')+'"') -WorkingDirectory $target -WindowStyle Hidden }
