# EKONT SMART REPORT - Manuel Kurulum Scripti
# Çalıştırmak için: powershell -ExecutionPolicy Bypass -File setup-manual.ps1

Write-Host "=== EKONT SMART REPORT - Manuel Kurulum ===" -ForegroundColor Cyan
Write-Host ""

# ---- 1. Docker Desktop ----
Write-Host "[1/2] Docker Desktop" -ForegroundColor Yellow
Write-Host "  PostgreSQL (TimescaleDB) + Redis icin gerekli." -ForegroundColor Gray

# WSL kontrol
$wsl = Get-Command wsl.exe -ErrorAction SilentlyComplete
$hv = (Get-CimInstance -Query "SELECT * FROM Win32_OptionalFeature WHERE Name = 'Microsoft-Hyper-V'" -ErrorAction SilentlyComplete).InstallState

if (-not $wsl -and $hv -ne 1) {
    Write-Host "  [!] Ne WSL ne de Hyper-V etkin." -ForegroundColor Red
    Write-Host "  Secenek 1 - Docker Desktop (WSL2 ile):" -ForegroundColor Green
    Write-Host "    1. WSL2'yi etkinlestir: wsl --install -d Ubuntu" -ForegroundColor White
    Write-Host "    2. https://docs.docker.com/desktop/setup/install/windows-install/ adresinden indir" -ForegroundColor White
    Write-Host "    3. Kurulumu tamamla" -ForegroundColor White
    Write-Host "  Secenek 2 - Docker Toolbox (eski Windows icin):" -ForegroundColor Green
    Write-Host "    https://github.com/docker-archive/toolbox/releases adresinden indir" -ForegroundColor White
} else {
    Write-Host "  [OK] WSL/Hyper-V hazir" -ForegroundColor Green
    Write-Host "  Indir: https://docs.docker.com/desktop/setup/install/windows-install/" -ForegroundColor White
}

Write-Host ""

# ---- 2. GTK Runtime (WeasyPrint icin) ----
Write-Host "[2/2] GTK Runtime (WeasyPrint PDF)" -ForegroundColor Yellow
Write-Host "  PDF raporlari icin gerekli." -ForegroundColor Gray

$gtkCheck = Test-Path "$env:ProgramFiles\GTK3-Runtime Win64\bin\libgobject-2.0-0.dll" -ErrorAction SilentlyComplete
if (-not $gtkCheck) {
    Write-Host "  [!] GTK Runtime bulunamadi" -ForegroundColor Red
    Write-Host "  Indir ve kur:" -ForegroundColor Green
    Write-Host "    1. https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases" -ForegroundColor White
    Write-Host "    2. 'gtk3-runtime-*-ts-win64.exe' dosyasini indir" -ForegroundColor White
    Write-Host "    3. Calistir ve kurulumu tamamla" -ForegroundColor White
    Write-Host "    4. Bilgisayari yeniden baslat" -ForegroundColor White
} else {
    Write-Host "  [OK] GTK Runtime kurulu" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Kurulum sonrasi ===" -ForegroundColor Cyan
Write-Host "  1. Docker kurulunca: cd docker && docker compose up -d" -ForegroundColor White
Write-Host "  2. Backend baslat: cd ..\backend && .venv\Scripts\uvicorn app.main:app --reload" -ForegroundColor White
Write-Host "  3. PDF icin GTK kurulunca WeasyPrint calisir" -ForegroundColor White
