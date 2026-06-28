# Production Readiness and Frontend Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch a fresh subagent per task, then run spec-compliance review and code-quality review before marking the task complete.

**Goal:** Build the first high-value productization layer: release artifacts, Windows service lifecycle, backup restore verification, and maintainable frontend page decomposition.

**Architecture:** Keep the documented native-process production model. Docker remains local infrastructure only. Add infrastructure scripts and docs around the existing backend/frontend/CLI/MCP system, then reduce frontend risk by splitting large pages into hooks, helpers, and focused components without changing visible behavior.

**Tech Stack:** PowerShell, GitHub Actions, `just`, Python 3.14, FastAPI, Alembic, uv, pnpm, Vite, React 19, Vitest, Playwright, existing backend pytest suite.

---

## Execution Rules

- Use subagents for implementation.
- Do not dispatch multiple implementation subagents in parallel against the same worktree.
- Use low-cost/fast model for isolated script, docs, and 1-2 file component extraction tasks.
- Use standard model for integration tasks that touch GitHub Actions, `justfile`, and multiple scripts.
- Use a high-capability model only for final cross-cutting review or if a subagent is repeatedly blocked.
- Each task must end with targeted verification and a commit.
- Preserve existing deployment decision: no production Docker app services unless explicitly approved later.
- Do not modify generated OpenAPI files manually.
- Do not run destructive restore or service installation without dry-run or explicit local-safe guardrails.

## Subagent Staffing Plan

| Task Area | Implementer Model | Review Model | Reason |
|---|---|---|---|
| Release validation script | low/fast | standard | Mostly deterministic PowerShell and tests. |
| Release artifact build + workflow | standard | standard | Crosses PowerShell, pnpm, Python packaging, GitHub Actions. |
| Windows service scripts | standard | standard | OS integration and safety checks require judgment. |
| Backup command + restore smoke | standard | standard | Data safety and DB restore guardrails matter. |
| Frontend helper extraction | low/fast | standard | Small behavior-preserving refactors. |
| Large page decomposition | standard | standard | Multi-file React refactor with tests. |
| Final integration review | high only if needed | high only if needed | Use high-capability model only if lower-cost review finds unresolved architecture risk. |

## Current Evidence

- CI already covers backend, frontend, CLI, MCP, and OpenAPI contract freshness: `.github/workflows/ci.yml`.
- Release workflow currently creates release notes only: `.github/workflows/release.yml`.
- Existing production infrastructure plan exists but is not implemented for these items: `docs/superpowers/plans/2026-06-23-production-infrastructure-maturity.md`.
- Backup API and engine exist: `scada-reporter/backend/app/api/backup.py`, `scada-reporter/backend/app/services/backup_engine.py`.
- Large frontend files are current maintainability targets:
  - `scada-reporter/frontend/src/pages/AdvancedReports.tsx`
  - `scada-reporter/frontend/src/pages/Tags.tsx`
  - `scada-reporter/frontend/src/pages/Trend.tsx`
  - `scada-reporter/frontend/src/pages/Grafana.tsx`
  - `scada-reporter/frontend/src/api/client.ts`

---

## File Structure

### New Scripts

- `scripts/check_release.ps1`
  Validates tag/version/changelog freshness and contract freshness before release build.

- `scripts/build_release.ps1`
  Builds release artifacts into `artifacts/release/vX.Y.Z/`.

- `scripts/install-services.ps1`
  Installs or dry-runs Windows services for API, collector, scheduler, and frontend.

- `scripts/uninstall-services.ps1`
  Uninstalls Windows services safely.

- `scripts/service-status.ps1`
  Reports service install/running state and configuration warnings.

- `scripts/backup-db.ps1`
  Creates PostgreSQL custom-format backup or delegates SQLite backup to the app-supported path where appropriate.

- `scripts/restore-smoke.ps1`
  Restores a backup into an isolated target and validates schema/table readiness.

### Modified Infrastructure Files

- `justfile`
  Adds release, service, backup, and restore-smoke recipes.

- `.github/workflows/release.yml`
  Runs release validation/build and uploads artifacts to GitHub Release.

- `.gitignore`
  Ensures release artifacts and local service logs remain ignored where needed.

### New Documentation

- `docs/release-build.md`
- `docs/windows-services.md`
- `docs/restore-smoke.md`

### Frontend Decomposition Files

- `scada-reporter/frontend/src/pages/advancedReports/`
  - `types.ts`
  - `advancedReportsStorage.ts`
  - `TemplatesTab.tsx`
  - `ScheduledTab.tsx`
  - `ArchiveTab.tsx`

- `scada-reporter/frontend/src/pages/tags/`
  - `tagFilters.ts`
  - `TagImportExportPanel.tsx`
  - `TagGroupPanel.tsx`
  - `TagsTable.tsx`

- `scada-reporter/frontend/src/pages/trend/`
  - Keep existing `TrendChart.tsx`, `TrendTagSelector.tsx`, `GroupTree.tsx`.
  - Add `trendPresetsStorage.ts`.
  - Add `useTrendData.ts`.

- `scada-reporter/frontend/src/pages/grafana/`
  - `grafanaUrls.ts`
  - `DashboardGenerator.tsx`
  - `LabDashboardGenerator.tsx`
  - `GrafanaDashboardTabs.tsx`

---

## Task 1: Release Validation Script

**Subagent:** implementer, low/fast model.

**Files:**
- Create: `scripts/check_release.ps1`
- Modify: `justfile`
- Create: `docs/release-build.md`

- [ ] Write a failing Pester-free smoke check by running the missing script.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_release.ps1 -Version 0.0.0 -DryRun
```

Expected: fails because script does not exist.

- [ ] Create `scripts/check_release.ps1`.

Required behavior:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$Version,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

if ($Version.StartsWith("v")) {
    $Version = $Version.Substring(1)
}

if (-not ($Version -match '^\d+\.\d+\.\d+([\-][A-Za-z0-9\.\-]+)?$')) {
    Fail "Version must look like 1.2.3 or 1.2.3-rc.1"
}

$changelog = Get-Content -Raw "CHANGELOG.md"
if ($changelog -notmatch [regex]::Escape("## [$Version]")) {
    Fail "CHANGELOG.md has no section for [$Version]"
}

if (-not $DryRun) {
    just contract-check
    if ($LASTEXITCODE -ne 0) { Fail "OpenAPI/generated client contract is stale" }
}

Write-Host "OK release validation passed for v$Version"
```

- [ ] Add `release-check` recipe to `justfile`.

Recipe:

```just
release-check version:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_release.ps1 -Version "{{version}}"
```

- [ ] Document usage in `docs/release-build.md`.

Include:

```markdown
# Release Build

Run:

```powershell
just release-check version="1.0.0"
```

The check validates the changelog section and OpenAPI/generated-client freshness.
```

- [ ] Verify.

Run:

```powershell
just release-check version="0.0.0"
```

Expected: fails with missing changelog section.

Run against an existing changelog version if available:

```powershell
just release-check version="<existing-version>"
```

Expected: passes or fails only on real contract drift.

- [ ] Commit.

```powershell
git add scripts/check_release.ps1 justfile docs/release-build.md
git commit -m "chore(release): add release validation"
```

---

## Task 2: Release Artifact Builder and GitHub Release Upload

**Subagent:** implementer, standard model.

**Files:**
- Create: `scripts/build_release.ps1`
- Modify: `justfile`
- Modify: `.github/workflows/release.yml`
- Modify: `docs/release-build.md`

- [ ] Write the initial failing command.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1 -Version 0.0.0 -DryRun
```

Expected: fails because script does not exist.

- [ ] Create `scripts/build_release.ps1`.

Required behavior:

- Accept `-Version`.
- Normalize optional `v` prefix.
- Create `artifacts/release/v<version>/`.
- Run `scripts/check_release.ps1`.
- Build frontend with `pnpm install --frozen-lockfile` and `pnpm build`.
- Zip frontend `dist`.
- Build wheels/sdists for `scada-core` and `agent-harness`.
- Copy `frontend/openapi.json`.
- Create backend source zip excluding `.env`, `.venv`, DBs, caches, `reports`, `backups`.
- Create `checksums-v<version>.sha256`.
- Support `-DryRun` that prints actions without building.

Core script structure:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$Version,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if ($Version.StartsWith("v")) { $Version = $Version.Substring(1) }
$Tag = "v$Version"
$OutDir = Join-Path $Root "artifacts/release/$Tag"

function Run-Step([string]$Command) {
    Write-Host ">> $Command"
    if (-not $DryRun) {
        pwsh -NoProfile -Command $Command
        if ($LASTEXITCODE -ne 0) { throw "Command failed: $Command" }
    }
}

Run-Step "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_release.ps1 -Version '$Version'"

if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

Run-Step "cd scada-reporter/frontend; pnpm install --frozen-lockfile; pnpm build"

if (-not $DryRun) {
    Compress-Archive -Path "scada-reporter/frontend/dist/*" -DestinationPath "$OutDir/ekont-smart-report-frontend-dist-$Tag.zip" -Force
    Copy-Item "scada-reporter/frontend/openapi.json" "$OutDir/openapi-$Tag.json" -Force
}

Run-Step "cd scada-reporter/packages/scada-core; python -m build"
Run-Step "cd scada-reporter/agent-harness; python -m build"

if (-not $DryRun) {
    Copy-Item "scada-reporter/packages/scada-core/dist/*" $OutDir -Force
    Copy-Item "scada-reporter/agent-harness/dist/*" $OutDir -Force
    git archive --format=zip --output="$OutDir/ekont-smart-report-backend-source-$Tag.zip" HEAD:scada-reporter/backend
    Get-ChildItem $OutDir -File | Where-Object { $_.Name -notlike "checksums-*" } | ForEach-Object {
        $hash = Get-FileHash $_.FullName -Algorithm SHA256
        "$($hash.Hash.ToLower())  $($_.Name)"
    } | Set-Content "$OutDir/checksums-$Tag.sha256"
}

Write-Host "OK release artifacts ready at $OutDir"
```

- [ ] Add `release-build` recipe to `justfile`.

```just
release-build version:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1 -Version "{{version}}"
```

- [ ] Update `.github/workflows/release.yml`.

Add setup steps before release creation:

```yaml
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.14"

      - uses: pnpm/action-setup@v4
        with:
          version: 11

      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: "pnpm"
          cache-dependency-path: scada-reporter/frontend/pnpm-lock.yaml

      - name: Install Python build tool
        run: python -m pip install build

      - name: Build release artifacts
        run: just release-build version="${GITHUB_REF_NAME#v}"
```

Configure `softprops/action-gh-release`:

```yaml
          files: artifacts/release/${{ github.ref_name }}/*
```

- [ ] Update docs with artifact list and release process.

- [ ] Verify dry-run.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1 -Version 0.0.0 -DryRun
```

Expected: prints planned actions and fails only if changelog validation is intentionally active for non-existing version. If needed for dry-run only, allow `-SkipValidation` after reviewer approval.

- [ ] Verify actual build with a changelog version.

```powershell
just release-build version="<existing-version>"
```

Expected: artifacts appear under `artifacts/release/v<existing-version>/`.

- [ ] Commit.

```powershell
git add scripts/build_release.ps1 justfile .github/workflows/release.yml docs/release-build.md
git commit -m "chore(release): build release artifacts"
```

---

## Task 3: Windows Service Lifecycle Scripts

**Subagent:** implementer, standard model.

**Files:**
- Create: `scripts/install-services.ps1`
- Create: `scripts/uninstall-services.ps1`
- Create: `scripts/service-status.ps1`
- Modify: `justfile`
- Create: `docs/windows-services.md`

- [ ] Start with dry-run-first behavior.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/service-status.ps1
```

Expected: fails because script does not exist.

- [ ] Create `scripts/service-status.ps1`.

Required service names:

```powershell
$Services = @(
    @{ Name = "EkontSmartReportApi"; Role = "api" },
    @{ Name = "EkontSmartReportCollector"; Role = "collector" },
    @{ Name = "EkontSmartReportScheduler"; Role = "scheduler" },
    @{ Name = "EkontSmartReportFrontend"; Role = "frontend" }
)
```

Output fields:

- service name
- installed true/false
- status if installed
- role
- warnings for missing frontend `dist`
- warnings if backend `.env` has unsafe role split

- [ ] Create `scripts/install-services.ps1`.

Required behavior:

- Default to `-DryRun`.
- Require `-Apply` to actually create services.
- Use `New-Service` only when `-Apply` is provided.
- Refuse to install frontend service if `scada-reporter/frontend/dist` is missing.
- Print exact command line for each service.
- Use native process model:
  - API: backend server command with `RUN_COLLECTOR=False`, `RUN_SCHEDULER=False`.
  - Collector: `python -m app.collector.runner`.
  - Scheduler: `python -m app.scheduler.runner`.
  - Frontend: static server command documented by the script.

Minimum structure:

```powershell
param(
    [switch]$Apply,
    [string]$Python = "python",
    [string]$Node = "node"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Backend = Join-Path $Root "scada-reporter/backend"
$FrontendDist = Join-Path $Root "scada-reporter/frontend/dist"

function Install-Or-Print($Name, $Binary, $Args, $WorkingDirectory) {
    Write-Host "Service: $Name"
    Write-Host "  Binary: $Binary"
    Write-Host "  Args: $Args"
    Write-Host "  WorkingDirectory: $WorkingDirectory"
    if ($Apply) {
        New-Service -Name $Name -BinaryPathName "`"$Binary`" $Args" -StartupType Automatic
    }
}
```

- [ ] Create `scripts/uninstall-services.ps1`.

Required behavior:

- Default dry-run.
- `-Apply` stops installed services then deletes them.
- Never errors if a service is absent.

- [ ] Add `justfile` recipes.

```just
service-status:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/service-status.ps1

install-services:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-services.ps1 -Apply

install-services-dry-run:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-services.ps1

uninstall-services:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall-services.ps1 -Apply

uninstall-services-dry-run:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall-services.ps1
```

- [ ] Write `docs/windows-services.md`.

Must cover:

- prerequisites
- dry-run
- install
- status
- uninstall
- API/collector/scheduler split
- log strategy
- upgrade flow
- rollback flow

- [ ] Verify syntax and dry-run.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-services.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall-services.ps1
just service-status
```

Expected: no changes are made; output is readable.

- [ ] Commit.

```powershell
git add scripts/install-services.ps1 scripts/uninstall-services.ps1 scripts/service-status.ps1 justfile docs/windows-services.md
git commit -m "chore(ops): add Windows service lifecycle scripts"
```

---

## Task 4: Backup Command Script

**Subagent:** implementer, low/fast model unless PostgreSQL parsing becomes complex.

**Files:**
- Create: `scripts/backup-db.ps1`
- Modify: `justfile`
- Modify: `docs/restore-smoke.md`

- [ ] Create missing-command failing check.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/backup-db.ps1 -DryRun
```

Expected: fails because script does not exist.

- [ ] Create `scripts/backup-db.ps1`.

Required behavior:

- Read `DATABASE_URL` from parameter or backend `.env`.
- For PostgreSQL URL, call `pg_dump -Fc`.
- For SQLite URL, print that in-app backup API is preferred unless `-AllowSqliteFileCopy` is provided.
- Write to `artifacts/backups/` by default.
- Support `-DryRun`.

Core structure:

```powershell
param(
    [string]$DatabaseUrl = "",
    [string]$OutDir = "artifacts/backups",
    [switch]$DryRun,
    [switch]$AllowSqliteFileCopy
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not $DatabaseUrl) {
    $envPath = "scada-reporter/backend/.env"
    if (Test-Path $envPath) {
        $line = Get-Content $envPath | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
        if ($line) { $DatabaseUrl = $line.Substring("DATABASE_URL=".Length).Trim('"') }
    }
}

if (-not $DatabaseUrl) { throw "DATABASE_URL not provided and not found in backend .env" }

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if ($DatabaseUrl -match '^postgresql') {
    $libpq = $DatabaseUrl -replace '^postgresql\+asyncpg', 'postgresql' -replace '^postgresql\+psycopg', 'postgresql'
    $dest = Join-Path $OutDir "scada-reporter-$Timestamp.dump"
    $cmd = "pg_dump -Fc -d `"$libpq`" -f `"$dest`""
    Write-Host ">> $cmd"
    if (-not $DryRun) {
        pg_dump -Fc -d $libpq -f $dest
        if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }
        Write-Host "OK backup written: $dest"
    }
    exit 0
}

if ($DatabaseUrl -match '^sqlite') {
    if (-not $AllowSqliteFileCopy) {
        throw "SQLite backups should use the app backup API/VACUUM path. Pass -AllowSqliteFileCopy only for local emergency copies."
    }
}
```

- [ ] Add `just backup-db`.

```just
backup-db:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/backup-db.ps1
```

- [ ] Create or update `docs/restore-smoke.md` with backup command section.

- [ ] Verify dry-run.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/backup-db.ps1 -DatabaseUrl "postgresql+asyncpg://u:p@localhost:5432/db" -DryRun
```

Expected: prints `pg_dump -Fc` command and does not create a dump.

- [ ] Commit.

```powershell
git add scripts/backup-db.ps1 justfile docs/restore-smoke.md
git commit -m "chore(backup): add database backup command"
```

---

## Task 5: Isolated Restore Smoke Script

**Subagent:** implementer, standard model.

**Files:**
- Create: `scripts/restore-smoke.ps1`
- Modify: `justfile`
- Modify: `docs/restore-smoke.md`

- [ ] Create missing-command failing check.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restore-smoke.ps1 -BackupPath missing.dump -TargetDatabaseUrl "postgresql://u:p@localhost:5432/restore_db" -DryRun
```

Expected: fails because script does not exist.

- [ ] Create `scripts/restore-smoke.ps1`.

Required safeguards:

- Require explicit `-TargetDatabaseUrl`.
- Refuse target DB names containing `scada_reporter` unless `-AllowProductionLikeName` is passed.
- Refuse if `TargetDatabaseUrl` equals app `DATABASE_URL`.
- Support `-DryRun`.
- Validate backup path exists unless dry-run.
- Use `pg_restore --clean --if-exists --no-owner --no-privileges`.
- Run Alembic current/head check using backend venv when available.
- Query critical tables with `psql`.

Core structure:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [Parameter(Mandatory=$true)][string]$TargetDatabaseUrl,
    [switch]$DryRun,
    [switch]$AllowProductionLikeName
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not $DryRun -and -not (Test-Path $BackupPath)) {
    throw "Backup not found: $BackupPath"
}

if (-not $AllowProductionLikeName -and $TargetDatabaseUrl -match 'scada_reporter($|[?])') {
    throw "Refusing production-like target database name. Use a dedicated restore DB."
}

$appEnv = "scada-reporter/backend/.env"
if (Test-Path $appEnv) {
    $line = Get-Content $appEnv | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
    if ($line) {
        $appDb = $line.Substring("DATABASE_URL=".Length).Trim('"')
        if ($appDb -eq $TargetDatabaseUrl) {
            throw "Refusing to restore into configured application DATABASE_URL"
        }
    }
}

$libpq = $TargetDatabaseUrl -replace '^postgresql\+asyncpg', 'postgresql' -replace '^postgresql\+psycopg', 'postgresql'
$cmd = "pg_restore --clean --if-exists --no-owner --no-privileges -d `"$libpq`" `"$BackupPath`""
Write-Host ">> $cmd"
if (-not $DryRun) {
    pg_restore --clean --if-exists --no-owner --no-privileges -d $libpq $BackupPath
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed" }
}

$tables = @("users", "tags", "tag_readings", "report_templates", "scheduled_reports", "report_archives")
foreach ($table in $tables) {
    $sql = "select count(*) from $table;"
    Write-Host ">> $sql"
    if (-not $DryRun) {
        psql $libpq -c $sql
        if ($LASTEXITCODE -ne 0) { throw "Table check failed: $table" }
    }
}

Write-Host "OK restore smoke completed"
```

- [ ] Add `just restore-smoke`.

```just
restore-smoke backup target:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restore-smoke.ps1 -BackupPath "{{backup}}" -TargetDatabaseUrl "{{target}}"
```

- [ ] Update `docs/restore-smoke.md`.

Must explain:

- create a dedicated restore DB
- never target production DB
- required tools: `pg_restore`, `psql`, backend venv for optional Alembic checks
- expected success output

- [ ] Verify dry-run.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restore-smoke.ps1 -BackupPath fake.dump -TargetDatabaseUrl "postgresql://u:p@localhost:5432/smart_restore_smoke" -DryRun
```

Expected: prints restore and table-check commands, does not require file.

- [ ] Commit.

```powershell
git add scripts/restore-smoke.ps1 justfile docs/restore-smoke.md
git commit -m "chore(backup): add isolated restore smoke"
```

---

## Task 6: Frontend Decomposition Baseline Helpers

**Subagent:** implementer, low/fast model.

**Files:**
- Create: `scada-reporter/frontend/src/pages/grafana/grafanaUrls.ts`
- Create: `scada-reporter/frontend/src/pages/grafana/grafanaUrls.test.ts`
- Create: `scada-reporter/frontend/src/pages/trend/trendPresetsStorage.ts`
- Create: `scada-reporter/frontend/src/pages/trend/trendPresetsStorage.test.ts`
- Modify: `scada-reporter/frontend/src/pages/Grafana.tsx`
- Modify: `scada-reporter/frontend/src/pages/Trend.tsx`

- [ ] Extract Grafana URL helpers.

Move `buildUrl` and `buildGrafanaPath` behavior from `Grafana.tsx` into `grafanaUrls.ts`.

Expected helper API:

```typescript
export interface GrafanaDashboardLink {
  uid: string
  title: string
  url: string
}

export function buildGrafanaDashboardUrl(
  dashboard: GrafanaDashboardLink,
  grafanaBaseUrl: string,
  kiosk: boolean,
  theme: 'dark' | 'light',
) {
  const url = new URL(dashboard.url, grafanaBaseUrl)
  url.searchParams.set('orgId', '1')
  url.searchParams.set('theme', theme)
  url.searchParams.set('refresh', '30s')
  if (kiosk) url.searchParams.set('kiosk', '')
  return url.toString()
}

export function buildGrafanaPathUrl(path: string, grafanaBaseUrl: string, theme: 'dark' | 'light') {
  const url = new URL(path, grafanaBaseUrl)
  url.searchParams.set('orgId', '1')
  url.searchParams.set('theme', theme)
  return url.toString()
}
```

- [ ] Add tests for URL helpers.

Run:

```powershell
cd scada-reporter/frontend
pnpm vitest run src/pages/grafana/grafanaUrls.test.ts
```

Expected: pass.

- [ ] Extract trend preset localStorage helper.

Expected helper API:

```typescript
export interface TrendPresetStorageItem {
  name: string
  tag_ids: number[]
  hours: number
}

export function loadTrendPresets(storage: Pick<Storage, 'getItem'>, key: string): TrendPresetStorageItem[] {
  try {
    const raw = storage.getItem(key)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function saveTrendPresets(
  storage: Pick<Storage, 'setItem'>,
  key: string,
  presets: TrendPresetStorageItem[],
) {
  storage.setItem(key, JSON.stringify(presets))
}
```

- [ ] Modify `Grafana.tsx` and `Trend.tsx` to use helpers without changing UI.

- [ ] Verify.

```powershell
cd scada-reporter/frontend
pnpm tsc --noEmit
pnpm vitest run src/pages/grafana/grafanaUrls.test.ts src/pages/trend/trendPresetsStorage.test.ts
```

- [ ] Commit.

```powershell
git add scada-reporter/frontend/src/pages/grafana scada-reporter/frontend/src/pages/trend scada-reporter/frontend/src/pages/Grafana.tsx scada-reporter/frontend/src/pages/Trend.tsx
git commit -m "refactor(frontend): extract Grafana and trend helpers"
```

---

## Task 7: Advanced Reports Page Decomposition

**Subagent:** implementer, standard model.

**Files:**
- Create: `scada-reporter/frontend/src/pages/advancedReports/types.ts`
- Create: `scada-reporter/frontend/src/pages/advancedReports/TemplatesTab.tsx`
- Create: `scada-reporter/frontend/src/pages/advancedReports/ScheduledTab.tsx`
- Create: `scada-reporter/frontend/src/pages/advancedReports/ArchiveTab.tsx`
- Modify: `scada-reporter/frontend/src/pages/AdvancedReports.tsx`
- Update tests if needed: `scada-reporter/frontend/src/pages/AdvancedReports.i18n.test.tsx`

- [ ] Use CodeGraph before editing.

```powershell
codegraph impact AdvancedReports --depth 2
```

- [ ] Move tab-local code out of `AdvancedReports.tsx`.

Target final `AdvancedReports.tsx`:

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import TemplatesTab from './advancedReports/TemplatesTab'
import ScheduledTab from './advancedReports/ScheduledTab'
import ArchiveTab from './advancedReports/ArchiveTab'

type Tab = 'templates' | 'scheduled' | 'archive'

export default function AdvancedReports() {
  const { t } = useTranslation('advancedReports')
  const [tab, setTab] = useState<Tab>('templates')

  const tabs: { id: Tab; label: string }[] = [
    { id: 'templates', label: t('tab_templates') },
    { id: 'scheduled', label: t('tab_scheduled') },
    { id: 'archive', label: t('tab_archive') },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">{t('title')}</h1>
        <p className="text-gray-500 text-sm mt-1">{t('subtitle')}</p>
      </div>

      <div className="flex border-b border-gray-800 mb-6">
        {tabs.map((tb) => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === tb.id ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}>
            {tb.label}
          </button>
        ))}
      </div>

      {tab === 'templates' && <TemplatesTab onRunDone={() => setTab('archive')} />}
      {tab === 'scheduled' && <ScheduledTab />}
      {tab === 'archive' && <ArchiveTab />}
    </div>
  )
}
```

- [ ] Preserve all existing behavior.

Rules:

- Do not rename translation keys.
- Do not change API calls.
- Do not change CSS classes except import path fixes.
- Do not migrate generated API usage in this task.

- [ ] Verify.

```powershell
cd scada-reporter/frontend
pnpm tsc --noEmit
pnpm vitest run src/pages/AdvancedReports.i18n.test.tsx
```

- [ ] Commit.

```powershell
git add scada-reporter/frontend/src/pages/AdvancedReports.tsx scada-reporter/frontend/src/pages/advancedReports scada-reporter/frontend/src/pages/AdvancedReports.i18n.test.tsx
git commit -m "refactor(frontend): split advanced reports tabs"
```

---

## Task 8: Tags, Trend, and Grafana Component Decomposition

**Subagent:** implementer, standard model.

**Files:**
- Create/modify files under:
  - `scada-reporter/frontend/src/pages/tags/`
  - `scada-reporter/frontend/src/pages/trend/`
  - `scada-reporter/frontend/src/pages/grafana/`
- Modify:
  - `scada-reporter/frontend/src/pages/Tags.tsx`
  - `scada-reporter/frontend/src/pages/Trend.tsx`
  - `scada-reporter/frontend/src/pages/Grafana.tsx`
- Update relevant tests:
  - `scada-reporter/frontend/src/pages/Tags.*.test.tsx`
  - `scada-reporter/frontend/src/pages/Grafana.test.tsx`
  - existing trend helper tests

- [ ] Use CodeGraph before editing.

```powershell
codegraph explore "frontend large pages Trend Tags Grafana helpers components tests" --path C:\project\smart
```

- [ ] Split `Grafana.tsx` generator forms.

Create:

- `DashboardGenerator.tsx`
- `LabDashboardGenerator.tsx`
- `GrafanaDashboardTabs.tsx`

Rules:

- Parent keeps state orchestration only if moving state would broaden the diff.
- Child components receive explicit props.
- Keep generated dashboard delete behavior unchanged.

- [ ] Split `Tags.tsx` panels.

Create:

- `TagImportExportPanel.tsx`
- `TagGroupPanel.tsx`
- `TagsTable.tsx`
- `tagFilters.ts`

Rules:

- Extract pure filtering/sorting logic into `tagFilters.ts`.
- Add tests for filter helper.
- Keep existing permission gating tests green.

- [ ] Split `Trend.tsx` data hook.

Create:

- `useTrendData.ts`

Rules:

- Keep chart rendering in existing `TrendChart.tsx`.
- Move fetch/loading/error state into hook only if tests can cover it with small mocks.
- Keep preset behavior from Task 6 helper.

- [ ] Verify targeted tests.

```powershell
cd scada-reporter/frontend
pnpm tsc --noEmit
pnpm vitest run src/pages/Grafana.test.tsx src/pages/Tags.gating.test.tsx src/pages/Tags.description.test.tsx src/pages/trend/trendPresetsStorage.test.ts
```

- [ ] Run broader frontend gate.

```powershell
cd scada-reporter/frontend
pnpm lint
pnpm test
```

- [ ] Commit.

```powershell
git add scada-reporter/frontend/src/pages/Tags.tsx scada-reporter/frontend/src/pages/Trend.tsx scada-reporter/frontend/src/pages/Grafana.tsx scada-reporter/frontend/src/pages/tags scada-reporter/frontend/src/pages/trend scada-reporter/frontend/src/pages/grafana
git commit -m "refactor(frontend): decompose large operations pages"
```

---

## Task 9: Documentation Index and Final Gate

**Subagent:** implementer, low/fast model for docs; standard reviewer.

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment.md`
- Modify: `docs/backup-recovery.md`
- Modify: `DOCKER.md` only if release/service/restore docs need a local-infra pointer

- [ ] Update README command list.

Add concise entries:

```markdown
just release-check version="1.0.0"
just release-build version="1.0.0"
just install-services-dry-run
just service-status
just backup-db
just restore-smoke backup="..." target="..."
```

- [ ] Link detailed docs.

Add links to:

- `docs/release-build.md`
- `docs/windows-services.md`
- `docs/restore-smoke.md`

- [ ] Update deployment docs.

Clarify:

- API service role
- collector service role
- scheduler service role
- frontend static serving
- release artifact install path

- [ ] Update backup docs.

Clarify:

- backup creation command
- restore-smoke command
- isolated target requirement

- [ ] Run final checks.

Use the project’s existing gate:

```powershell
just check
```

If this is too slow for the current machine, run at minimum:

```powershell
just backend-check
just frontend-check
just cli-check
just mcp-check
just contract-check
```

- [ ] Final subagent review.

Dispatch a final reviewer subagent with:

- full diff summary
- plan path
- exact verification outputs
- request for findings only

- [ ] Commit docs/fixes.

```powershell
git add README.md docs/deployment.md docs/backup-recovery.md DOCKER.md
git commit -m "docs: document production readiness workflows"
```

---

## Final Acceptance Checklist

- [ ] `just release-check version="<version>"` validates changelog and contract freshness.
- [ ] `just release-build version="<version>"` creates deterministic artifacts under `artifacts/release/v<version>/`.
- [ ] GitHub Release uploads artifacts and checksums.
- [ ] `just install-services-dry-run` prints API, collector, scheduler, and frontend service definitions without changing the machine.
- [ ] `just service-status` reports installed/missing services clearly.
- [ ] `just backup-db` can create a PostgreSQL custom-format dump.
- [ ] `just restore-smoke backup="..." target="..."` refuses unsafe targets and validates isolated restore targets.
- [ ] `AdvancedReports.tsx` is reduced to route/tab orchestration.
- [ ] `Tags.tsx`, `Trend.tsx`, and `Grafana.tsx` have focused helper/component extractions with no visible behavior change.
- [ ] Frontend tests and `pnpm tsc --noEmit` pass.
- [ ] `just check` passes, or any skipped portion is documented with the exact reason.
- [ ] Implementation was done through subagents with per-task spec and quality review.

## Self-Review

Spec coverage:

- Item 1, release artifact pipeline: Tasks 1 and 2.
- Item 2, Windows service lifecycle: Task 3.
- Item 3, backup restore-smoke: Tasks 4 and 5.
- Item 7, frontend decomposition: Tasks 6, 7, and 8.
- Documentation and final validation: Task 9.

Placeholder scan:

- No unfinished-marker text or unspecified implementation steps remain.
- Destructive operations are guarded by dry-run or explicit target parameters.

Type/path consistency:

- Frontend helper names are defined before call-site migration.
- `justfile` recipes map directly to script paths.
- Release artifact output path is consistently `artifacts/release/v<version>/`.
