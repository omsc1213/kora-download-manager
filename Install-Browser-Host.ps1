param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-p]{32}$')][string]$ExtensionId,
  [ValidateSet('Chrome','Edge')][string]$Browser='Chrome'
)
$ErrorActionPreference='Stop'
$exe=Join-Path $PSScriptRoot 'kora.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Build kora.exe first with Build-Rust.cmd. Browser registration has not been changed.' }
$manifest=Join-Path $PSScriptRoot 'browser-host.json'
$origins=@("chrome-extension://$ExtensionId/")
if (Test-Path -LiteralPath $manifest) {
    try { $previous=Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json; $origins+=@($previous.allowed_origins | Where-Object { $_ -match '^chrome-extension://[a-p]{32}/$' }) } catch { }
}
$json=@{name='com.kora.downloads';description='Kora download queue';path=$exe;type='stdio';allowed_origins=@($origins | Select-Object -Unique)} | ConvertTo-Json
[IO.File]::WriteAllText($manifest,$json,(New-Object Text.UTF8Encoding($false)))
$vendor=if ($Browser -eq 'Chrome') {'Google\Chrome'} else {'Microsoft\Edge'}
$registry="HKCU:\Software\$vendor\NativeMessagingHosts\com.kora.downloads"
New-Item -Path $registry -Force | Out-Null
Set-Item -LiteralPath $registry -Value $manifest
Write-Output "Registered Kora for $Browser and extension $ExtensionId. Open Kora before queuing browser links."
