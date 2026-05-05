# Copy full Odoo source to Chatbot_LuatMaiTrang\vendor\odoo
# so .\scripts\run_odoo.ps1 can run without external odoo folder.
#
# Default source: sibling folder "..\odoo".
# Override: $env:ODOO_SOURCE="D:\path\to\odoo"
# or .\sync_odoo_from_source.ps1 -Source "D:\odoo"
#
# Requires Windows + robocopy. Folder can be large (GBs); vendor\odoo is gitignored.
param(
    [string] $Source = ""
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Dest = Join-Path $ProjectRoot "vendor\odoo"

if (-not $Source) {
    $Source = if ($env:ODOO_SOURCE) { $env:ODOO_SOURCE } else { Join-Path (Split-Path $ProjectRoot -Parent) "odoo" }
}

if (-not (Test-Path (Join-Path $Source "odoo-bin"))) {
    Write-Error "odoo-bin not found in: $Source"
}

Write-Host "Source: $Source" -ForegroundColor Cyan
Write-Host "Dest:   $Dest" -ForegroundColor Cyan
New-Item -ItemType Directory -Path (Split-Path $Dest -Parent) -Force | Out-Null

# /MIR mirrors source to destination.
# /XD excludes heavy top-level directories but keeps addons + odoo/.
$xdDirs = @(
    ".git", ".github", "__pycache__", ".pytest_cache", ".ruff_cache",
    "node_modules", "doc", "setup", "debian"
)
$robocopyArgs = @($Source, $Dest, "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS", "/R:2", "/W:2")
foreach ($d in $xdDirs) {
    $robocopyArgs += @("/XD", $d)
}
& robocopy.exe @robocopyArgs
$code = $LASTEXITCODE
# robocopy exit codes 0-7 are successful.
if ($code -ge 8) {
    Write-Error "robocopy failed (exit $code)"
}
Write-Host "Done. If first run, install Python deps in vendor\odoo per Odoo README." -ForegroundColor Green
