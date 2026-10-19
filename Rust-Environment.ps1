$ErrorActionPreference='Stop'
$toolRoot=if ($env:KORA_RUST_HOME) { $env:KORA_RUST_HOME } else { Join-Path $PSScriptRoot '.toolchain' }
if (Test-Path -LiteralPath (Join-Path $toolRoot 'cargo\bin\cargo.exe')) {
    $env:CARGO_HOME=Join-Path $toolRoot 'cargo';$env:RUSTUP_HOME=Join-Path $toolRoot 'rustup'
    $env:PATH=(Join-Path $env:CARGO_HOME 'bin')+';'+$env:PATH
}
if (-not (Get-Command cargo.exe -ErrorAction SilentlyContinue)) { throw 'Install Rust from https://rustup.rs or run Setup-Rust.ps1.' }
