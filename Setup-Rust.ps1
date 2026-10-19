param([string]$ToolchainRoot=(Join-Path $PSScriptRoot '.toolchain'))
$ErrorActionPreference='Stop'
$ToolchainRoot=[IO.Path]::GetFullPath($ToolchainRoot)
New-Item -ItemType Directory -Force -Path $ToolchainRoot | Out-Null
$env:CARGO_HOME=Join-Path $ToolchainRoot 'cargo'
$env:RUSTUP_HOME=Join-Path $ToolchainRoot 'rustup'
$env:KORA_RUST_HOME=$ToolchainRoot
$localTemp=Join-Path $ToolchainRoot 'temp'
New-Item -ItemType Directory -Force -Path $localTemp,(Join-Path $env:CARGO_HOME 'bin') | Out-Null
$env:TEMP=$localTemp;$env:TMP=$localTemp
$env:RUSTUP_DOWNLOAD_TIMEOUT='900'
$env:RUSTUP_CONCURRENT_DOWNLOADS='1'
$bootstrap=Join-Path $ToolchainRoot 'rustup-init.exe'
$checksum=Join-Path $ToolchainRoot 'rustup-init.exe.sha256'
$url='https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-gnu/rustup-init.exe'
& curl.exe --fail --silent --show-error --location --connect-timeout 30 --max-time 180 --output $checksum "$url.sha256"
if ($LASTEXITCODE -ne 0) { throw 'Could not download the official Rust checksum' }
$expected=(Get-Content -LiteralPath $checksum -Raw).Trim().Split(' ')[0]
if ($expected -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid official checksum format' }
$valid=(Test-Path -LiteralPath $bootstrap) -and ((Get-FileHash -LiteralPath $bootstrap -Algorithm SHA256).Hash -ieq $expected)
if (-not $valid) {
    & curl.exe --fail --silent --show-error --location --connect-timeout 30 --max-time 180 --output $bootstrap $url
    if ($LASTEXITCODE -ne 0) { throw 'Rust installer download failed' }
}
if ((Get-FileHash -LiteralPath $bootstrap -Algorithm SHA256).Hash -ine $expected) { throw 'Rust installer checksum mismatch' }
$rustup=Join-Path $env:CARGO_HOME 'bin\rustup.exe'
Copy-Item -LiteralPath $bootstrap -Destination $rustup -Force
& $rustup toolchain install stable-x86_64-pc-windows-gnu --profile minimal --no-self-update --default
if ($LASTEXITCODE -ne 0) { throw 'Rust component installation failed; rerunning this script reuses downloaded components' }
foreach ($name in @('cargo.exe','rustc.exe','rustdoc.exe')) {
    # Rustup proxies dispatch by executable name. Regular copies avoid filesystem
    # hard-link restrictions while leaving all commands inside this directory.
    Copy-Item -LiteralPath $rustup -Destination (Join-Path $env:CARGO_HOME "bin\$name") -Force
}
& (Join-Path $PSScriptRoot 'Build-Rust.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Kora build failed' }
