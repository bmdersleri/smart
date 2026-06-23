# EkontFrontend NSSM Windows servisi kurulumu (Vite dev server, :5173)
# Administrator PowerShell ile çalıştır:
#   powershell -ExecutionPolicy Bypass -File scripts\configure-frontend-windows-service.ps1
param(
    [string]$ServiceName = "EkontFrontend",
    [string]$Nssm        = "C:\Users\aa\Tools\nssm\nssm.exe",
    [string]$Pnpm        = "C:\ProgramData\scoop\shims\pnpm.exe",
    [string]$FrontendDir = "C:\project\smart\scada-reporter\frontend",
    [string]$LogDir      = "C:\Users\aa\Tools\monitoring\service-logs"
)

$ErrorActionPreference = "Stop"

# Admin kontrolü
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw "Administrator olarak çalıştır. (Servis kurulumu yükseltilmiş yetki ister.)" }

foreach ($p in @($Nssm, $Pnpm, $FrontendDir)) {
    if (-not (Test-Path $p)) { throw "Bulunamadı: $p" }
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Varsa eski servisi kaldır (idempotent)
& $Nssm stop $ServiceName 2>$null | Out-Null
& $Nssm remove $ServiceName confirm 2>$null | Out-Null

& $Nssm install $ServiceName $Pnpm dev
& $Nssm set $ServiceName AppDirectory $FrontendDir
& $Nssm set $ServiceName AppStdout "$LogDir\$ServiceName.out.log"
& $Nssm set $ServiceName AppStderr "$LogDir\$ServiceName.err.log"
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm set $ServiceName AppStopMethodSkip 6
& $Nssm set $ServiceName DisplayName "Ekont Smart Frontend (Vite dev)"
& $Nssm set $ServiceName Description "EKONT SMART REPORT frontend - Vite dev server (port 5173)"

& $Nssm start $ServiceName

Start-Sleep -Seconds 6
Write-Host "`n=== Durum ==="
Get-Service $ServiceName | Select-Object Name, Status, StartType | Format-List
try {
    $r = Invoke-WebRequest "http://localhost:5173/" -UseBasicParsing -TimeoutSec 8
    Write-Host "Health: HTTP $($r.StatusCode) (frontend ayakta)"
} catch {
    Write-Host "Health: henüz cevap yok - log: $LogDir\$ServiceName.err.log"
}
