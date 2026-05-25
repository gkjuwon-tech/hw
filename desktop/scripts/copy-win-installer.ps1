$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "release\\Conet-Tactile-0.1.0-win-x64.exe"
$targetDir = Join-Path $root "artifacts"
$target = Join-Path $targetDir "Conet-Tactile-0.1.0-win-x64-setup.exe"

if (-not (Test-Path $source)) {
  throw "Installer not found: $source"
}

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Force
Write-Host "Copied installer to $target"
