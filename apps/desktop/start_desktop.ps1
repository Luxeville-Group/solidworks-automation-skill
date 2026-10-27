<#
.SYNOPSIS
Başlat CAD Automation delivery workbench desktop prototype.

.DESCRIPTION
Betik depo kökünde çalışır; önce kontrol eder:  PySide6, Eksikse kurulum komutunu gösterip başlatın:  PySide6  desktop application.
#>

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$DesktopDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $DesktopDir "..\..")
Set-Location $RepoRoot

$HasPySide = python -c "import importlib.util; print('1' if importlib.util.find_spec('PySide6') else '0')"
if ($HasPySide.Trim() -ne "1") {
    Write-Host "Eksik PySide6, Önce çalıştırın: :" -ForegroundColor Yellow
    Write-Host "python -m pip install -r apps\desktop\requirements.txt" -ForegroundColor Cyan
    exit 1
}

python apps\desktop\run.py
