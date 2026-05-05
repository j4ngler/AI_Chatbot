# Chạy API + demo web tĩnh + /erp (sau khi npm run build trong enterprise_web) — KHÔNG cần Docker.
# Yêu cầu: Python 3.12+, pip install -r requirements.txt; Node chỉ cần khi build frontend.
# Mặc định dùng SQLite tại data/erp_demo_local.db nếu chưa đặt DATABASE_URL.
param(
    [string] $ListenHost = "127.0.0.1",
    [int] $Port = 8000
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

if (-not $env:DATABASE_URL) {
    $dbDir = Join-Path $ProjectRoot "data"
    if (-not (Test-Path $dbDir)) {
        New-Item -ItemType Directory -Path $dbDir | Out-Null
    }
    $dbPath = (Join-Path $dbDir "erp_demo_local.db").Replace("\", "/")
    $env:DATABASE_URL = "sqlite:///$dbPath"
}
if (-not $env:JWT_SECRET) {
    $env:JWT_SECRET = "local-dev-change-me"
}

Write-Host "DATABASE_URL=$($env:DATABASE_URL)" -ForegroundColor Cyan
Write-Host "Gợi ý: ERP_DEMO_AUTH_BYPASS + ODOO_DB nếu chưa có Odoo. Mở http://${ListenHost}:${Port}/erp/#/login" -ForegroundColor Gray

python -m uvicorn api.main:app --host $ListenHost --port $Port --reload
