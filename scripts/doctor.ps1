$ErrorActionPreference = "Continue"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendPython = Join-Path $RepoRoot "scada-reporter\backend\.venv\Scripts\python.exe"
$ScadaExe = Join-Path $RepoRoot "scada-reporter\backend\.venv\Scripts\scada.exe"
$BackendEnv = Join-Path $RepoRoot "scada-reporter\backend\.env"
$FrontendNodeModules = Join-Path $RepoRoot "scada-reporter\frontend\node_modules"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

function Write-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [string]$Detail = ""
    )
    $Status = if ($Ok) { "OK" } else { "WARN" }
    if ($Detail) {
        Write-Host ("[{0}] {1}: {2}" -f $Status, $Name, $Detail)
    } else {
        Write-Host ("[{0}] {1}" -f $Status, $Name)
    }
}

function Get-FirstLine {
    param(
        [string]$Command,
        [string[]]$Arguments = @()
    )
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        return $null
    }
    try {
        $Output = & $Command @Arguments 2>&1
        return ($Output | Select-Object -First 1) -as [string]
    } catch {
        return "error: $($_.Exception.Message)"
    }
}

function Test-PortListening {
    param([int]$Port)
    try {
        $Conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return $null -ne $Conn
    } catch {
        try {
            $Client = [System.Net.Sockets.TcpClient]::new()
            $Async = $Client.BeginConnect("127.0.0.1", $Port, $null, $null)
            $Ok = $Async.AsyncWaitHandle.WaitOne(200)
            if ($Ok) {
                $Client.EndConnect($Async)
            }
            $Client.Close()
            return $Ok
        } catch {
            return $false
        }
    }
}

Set-Location $RepoRoot

Write-Section "Toolchain"
foreach ($Tool in @(
    @{ Name = "python"; Args = @("--version") },
    @{ Name = "uv"; Args = @("--version") },
    @{ Name = "node"; Args = @("--version") },
    @{ Name = "pnpm"; Args = @("--version") },
    @{ Name = "just"; Args = @("--version") },
    @{ Name = "git"; Args = @("--version") }
)) {
    $Line = Get-FirstLine -Command $Tool.Name -Arguments $Tool.Args
    Write-Check $Tool.Name ($null -ne $Line) ($(if ($Line) { $Line } else { "not found on PATH" }))
}

Write-Section "Project Installs"
if (Test-Path $BackendPython) {
    $Line = & $BackendPython --version 2>&1
    Write-Check "backend venv python" $true ($Line -as [string])
} else {
    Write-Check "backend venv python" $false "missing: $BackendPython"
}

Write-Check "frontend node_modules" (Test-Path $FrontendNodeModules) $FrontendNodeModules
Write-Check "backend .env" (Test-Path $BackendEnv) ($(if (Test-Path $BackendEnv) { $BackendEnv } else { "missing; copy .env.example if needed" }))

if (Test-Path $ScadaExe) {
    try {
        $Help = & $ScadaExe --help 2>&1 | Select-Object -First 1
        Write-Check "scada CLI" $true ($Help -as [string])
    } catch {
        Write-Check "scada CLI" $false $_.Exception.Message
    }
} else {
    Write-Check "scada CLI" $false "missing: $ScadaExe"
}

Write-Section "Docker"
$Docker = Get-FirstLine -Command "docker" -Arguments @("--version")
Write-Check "docker CLI" ($null -ne $Docker) ($(if ($Docker) { $Docker } else { "not found on PATH" }))

Write-Section "Local Ports"
$Ports = @(
    @{ Port = 8001; Name = "backend API" },
    @{ Port = 5173; Name = "frontend Vite" },
    @{ Port = 5432; Name = "PostgreSQL/TimescaleDB" },
    @{ Port = 9090; Name = "Prometheus" },
    @{ Port = 3000; Name = "Grafana" }
)
foreach ($Item in $Ports) {
    $Listening = Test-PortListening -Port $Item.Port
    Write-Check ("port {0} ({1})" -f $Item.Port, $Item.Name) $Listening ($(if ($Listening) { "listening" } else { "not listening" }))
}

Write-Section "Git Workspace"
if (Get-Command git -ErrorAction SilentlyContinue) {
    $Status = & git status --short 2>&1
    if ($LASTEXITCODE -eq 0) {
        $Lines = @($Status)
        Write-Check "git status" ($Lines.Count -eq 0) ($(if ($Lines.Count -eq 0) { "clean" } else { "$($Lines.Count) changed/untracked entries" }))
        $Lines | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
        if ($Lines.Count -gt 20) {
            Write-Host "  ... ($($Lines.Count - 20) more)"
        }
    } else {
        Write-Check "git status" $false ($Status -join "`n")
    }
}

Write-Host ""
Write-Host "Doctor complete."
