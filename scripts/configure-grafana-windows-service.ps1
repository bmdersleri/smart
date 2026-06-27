param(
    [string]$GrafanaHome = "$env:ProgramFiles\GrafanaLabs\grafana",
    [string]$ServiceName = "grafana",
    [string]$PostgresHost = "localhost",
    [int]$PostgresPort = 5432,
    [string]$PostgresDatabase = "scada_reporter",
    [string]$PostgresUser = "scada",
    [string]$PostgresPassword = $(if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "scada123" }),
    [string]$PrometheusUrl = "http://localhost:9090",
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

function Set-IniValue {
    param(
        [string[]]$Lines,
        [string]$Section,
        [string]$Key,
        [string]$Value
    )

    if ($null -eq $Lines) {
        $Lines = @()
    }

    $sectionHeader = "[$Section]"
    $sectionIndex = [Array]::IndexOf($Lines, $sectionHeader)
    if ($sectionIndex -lt 0) {
        return $Lines + @("", $sectionHeader, "$Key = $Value")
    }

    $nextSectionIndex = $Lines.Length
    for ($i = $sectionIndex + 1; $i -lt $Lines.Length; $i++) {
        if ($Lines[$i] -match '^\s*\[.+\]\s*$') {
            $nextSectionIndex = $i
            break
        }
    }

    for ($i = $sectionIndex + 1; $i -lt $nextSectionIndex; $i++) {
        if ($Lines[$i] -match "^\s*;?\s*$([regex]::Escape($Key))\s*=") {
            $Lines[$i] = "$Key = $Value"
            return $Lines
        }
    }

    $before = $Lines[0..$sectionIndex]
    $after = if ($sectionIndex + 1 -lt $Lines.Length) { $Lines[($sectionIndex + 1)..($Lines.Length - 1)] } else { @() }
    return $before + @("$Key = $Value") + $after
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$sourceDashboards = Join-Path $repoRoot "scada-reporter\docker\grafana\dashboards"
$provisioning = Join-Path $GrafanaHome "conf\provisioning"
$datasources = Join-Path $provisioning "datasources"
$dashboards = Join-Path $provisioning "dashboards"
$customIni = Join-Path $GrafanaHome "conf\custom.ini"

if (-not (Test-Path $GrafanaHome)) {
    throw "GrafanaHome bulunamadı: $GrafanaHome"
}
if (-not (Test-Path $sourceDashboards)) {
    throw "Dashboard kaynak klasörü bulunamadı: $sourceDashboards"
}

New-Item -ItemType Directory -Force -Path $datasources, $dashboards | Out-Null

@"
apiVersion: 1

datasources:
  - name: TimescaleDB
    type: postgres
    access: proxy
    url: ${PostgresHost}:${PostgresPort}
    database: ${PostgresDatabase}
    user: ${PostgresUser}
    uid: timescaledb
    secureJsonData:
      password: ${PostgresPassword}
    jsonData:
      sslmode: disable
      postgresVersion: 1600
      timescaledb: true
"@ | Set-Content -Encoding UTF8 (Join-Path $datasources "timescaledb.yml")

@"
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: ${PrometheusUrl}
    isDefault: false
    uid: prometheus
    jsonData:
      timeInterval: 15s
"@ | Set-Content -Encoding UTF8 (Join-Path $datasources "prometheus.yml")

Copy-Item -Force (Join-Path $sourceDashboards "*.json") $dashboards
$dashboardPath = $dashboards.Replace("\", "/")
@"
apiVersion: 1

providers:
  - name: scada-dashboards
    orgId: 1
    type: file
    disableDeletion: false
    updateIntervalSeconds: 60
    allowUiUpdates: true
    options:
      path: ${dashboardPath}
      foldersFromFilesStructure: false
"@ | Set-Content -Encoding UTF8 (Join-Path $dashboards "dashboards.yml")

if (-not (Test-Path $customIni)) {
    New-Item -ItemType File -Force -Path $customIni | Out-Null
}

$lines = @(Get-Content $customIni)
$lines = Set-IniValue -Lines $lines -Section "server" -Key "http_port" -Value "3000"
$lines = Set-IniValue -Lines $lines -Section "security" -Key "allow_embedding" -Value "true"
$lines = Set-IniValue -Lines $lines -Section "auth.anonymous" -Key "enabled" -Value "true"
$lines = Set-IniValue -Lines $lines -Section "auth.anonymous" -Key "org_role" -Value "Viewer"
$lines | Set-Content -Encoding UTF8 $customIni

Write-Host "Grafana Windows service provisioning hazırlandı:"
Write-Host "  custom.ini: $customIni"
Write-Host "  datasources: $datasources"
Write-Host "  dashboards: $dashboards"

if ($Restart) {
    Restart-Service -Name $ServiceName -Force
    Write-Host "Servis yeniden başlatıldı: $ServiceName"
}
