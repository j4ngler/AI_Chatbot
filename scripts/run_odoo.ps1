# Chạy Odoo bằng Python — mọi thứ nằm trong Chatbot_LuatMaiTrang khi đã đồng bộ source vào vendor/odoo.
# Thứ tự tìm odoo-bin:
#   1) .\vendor\odoo\odoo-bin  (chạy scripts\sync_odoo_from_source.ps1 để copy từ bản Odoo đầy đủ)
#   2) thư mục odoo cạnh Intern (..\odoo) nếu vẫn giữ layout cũ
# Nếu không có source: dùng Docker — docker compose --profile erp up -d
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$OdooArgs
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$VendorRoot = Join-Path $ProjectRoot "vendor\odoo"
$InternParent = Split-Path $ProjectRoot -Parent
$LegacySibling = Join-Path $InternParent "odoo"

$OdooRoot = $null
if (Test-Path (Join-Path $VendorRoot "odoo-bin")) {
    $OdooRoot = $VendorRoot
}
elseif (Test-Path (Join-Path $LegacySibling "odoo-bin")) {
    $OdooRoot = $LegacySibling
}

if (-not $OdooRoot) {
    Write-Host "Không tìm thấy odoo-bin." -ForegroundColor Yellow
    Write-Host "  - Copy source vào dự án: .\scripts\sync_odoo_from_source.ps1" -ForegroundColor Gray
    Write-Host "  - Hoặc chạy Odoo bằng Docker: docker compose --profile erp up -d" -ForegroundColor Gray
    exit 1
}

$AddonsPath = @(
    (Join-Path $OdooRoot "addons")
    (Join-Path $OdooRoot "odoo\addons")
    (Join-Path $ProjectRoot "odoo_addons")
) -join ","
$DataDir = Join-Path $ProjectRoot ".odoo_data"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir | Out-Null
}
$python = $null
if ($env:ODOO_PYTHON) {
    $python = $env:ODOO_PYTHON
}
else {
    $venvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    $dotVenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $python = $venvPython
    }
    elseif (Test-Path $dotVenvPython) {
        $python = $dotVenvPython
    }
    else {
        $python = "python"
    }
}
$odooBin = Join-Path $OdooRoot "odoo-bin"
& $python $odooBin --addons-path=$AddonsPath --data-dir=$DataDir @OdooArgs
