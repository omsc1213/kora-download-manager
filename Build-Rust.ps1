$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Rust-Environment.ps1')
Push-Location -LiteralPath $PSScriptRoot
try {
    & rustc --version
    if ($LASTEXITCODE -ne 0) { throw 'Rust compiler startup failed' }
    & cargo test --offline
    if ($LASTEXITCODE -ne 0) { throw 'Rust tests failed' }
    & cargo build --release --offline
    if ($LASTEXITCODE -ne 0) { throw 'Rust release build failed' }
    $candidate=Join-Path $PSScriptRoot 'target\release\kora.exe'
    & $candidate --version
    if ($LASTEXITCODE -ne 0) { throw 'Built executable did not start' }
    Copy-Item -LiteralPath $candidate -Destination (Join-Path $PSScriptRoot 'kora.exe') -Force
    Write-Output 'Built and verified kora.exe. The desktop and downloader still use the Python backend.'
} finally { Pop-Location }
