# Available Tools — AI Coding Agents

## System
| Tool | Version | Path |
|------|---------|------|
| OS | Windows Server 2019 Standard | |
| CPU | Intel Xeon Silver 4208 @ 2.10GHz | |
| RAM | 63.6 GB | |
| Disk C: | 1116 GB (1008 GB free) | |
| Disk E: | 8522 GB (7932 GB free) | |
| Tailscale | | `C:\Program Files\Tailscale` |

## Shells
| Tool | Version | Path |
|------|---------|------|
| PowerShell 7 | 7.6.2 | `C:\Program Files\PowerShell\7\pwsh.exe` |

## Version Control
| Tool | Version | Path |
|------|---------|------|
| Git | 2.54.0.windows.1 | `C:\Program Files\Git` |
| GitHub CLI | 2.94.0 | `gh` |
| lazygit | 0.62.2 | `lazygit` |
| delta | 0.19.2 | `delta` |
| tig | | `tig` |
| git-lfs | | `git-lfs` |
| scalar | | `scalar` |

## Languages & Runtimes
| Tool | Version | Path |
|------|---------|------|
| Python 3.12 | 3.12.x | `C:\Program Files\Python312\python.exe` |
| Python 3.14 | 3.14.6 | `C:\Python314\python.exe` |
| Node.js | 24.16.0 | `C:\Program Files\nodejs\node.exe` |
| Rust | 1.96.0 (x86_64-pc-windows-gnu) | `C:\Users\Administrator\.cargo\bin\rustc.exe` |
| Go | 1.26.4 | `go` |
| .NET SDK | 10.0.301 | `dotnet` |
| TypeScript | 6.0.3 | `tsc` |
| GCC (MinGW) | 15.2.0 | `C:\ProgramData\mingw64\mingw64\bin\gcc.exe` |

## Package Managers
| Tool | Version | Notes |
|------|---------|-------|
| uv | 0.11.21 | Python package manager |
| pip (3.12) | 26.1.2 | |
| pip (3.14) | 26.1.2 | |
| npm | 11.17.0 | |
| pnpm | 11.6.0 | |
| corepack | | |
| Cargo | 1.96.0 | Rust package manager |
| Chocolatey | 2.7.3 | System package manager |
| Scoop | | System package manager (shims in `C:\ProgramData\scoop\shims`) |
| Just | 1.52.0 | Command runner |

## AI Coding Tools
| Tool | Version | Path |
|------|---------|------|
| Claude Code | 2.1.178 | `claude` (npm) |
| Gemini CLI | 0.46.0 | `gemini` (npm) |
| opencode | 1.17.6 | `opencode` (npm) |
| Codex | | `C:\Users\Administrator\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe` |
| codegraph | 1.0.1 | `codegraph` — semantic code intelligence; connected as Claude Code MCP, repo indexed (`.codegraph/`) |
| Kalfa | 1.0.0 | `kalfa` (npm) |
| caveman | enabled plugin | `caveman@caveman` Claude Code plugin (user scope, ✔ enabled) — token-reduction skill; `/caveman` etc. activate after CC restart. Installer: `caveman-code` (npm) |
| RTK | 0.42.4 | `C:\Users\aa\.local\bin\rtk.exe` (NOT on default bash/PowerShell PATH) — Rust Token Killer; prefix shell cmds (`rtk git status`) |
| FCC (Free Claude Code) | | `fcc-claude`, `fcc-init`, `fcc-server` |
| scada | | `scada` — EKONT SMART REPORT agent CLI (agent-harness) |

## Project CLI (`scada`)
| Command | Description |
|---------|-------------|
| `scada auth login <username>` | JWT login |
| `scada auth register <username> <email>` | Create user account |
| `scada tags list [--json-output]` | List all tags |
| `scada tags create --node-id <id> --name <name>` | Create tag from PLC |
| `scada tags update <id> [--unit] [--device] [--channel]` | Update tag (unit, device, alarm thresholds) |
| `scada tags delete <id>` | Delete tag |
| `scada tags readings <id> [--start] [--end] [--limit]` | Tag readings with time range |
| `scada dashboard overview [--json-output]` | System overview |
| `scada dashboard current-values [--alarm-only] [--watch N]` | Live values with alarm filtering and auto-refresh |
| `scada dashboard trend <tag_id>... [--hours N]` | Trend visualization (48h default) |
| `scada reports generate --tag-ids 1,2,3 --start <iso> --end <iso>` | Generate Excel/JSON report |
| `scada reports list-history [--json-output]` | List last 10 saved reports |
| `scada reports download-history <id> [--output FILE]` | Re-download cached report |
| `scada query run "SELECT ..." [--limit N]` | Read-only SQL execution |
| `scada explore schema [--json-output]` | DB schema discovery |
| `scada explore tags [--json-output]` | Tag catalog grouped by device with alarm thresholds |
| `scada explore summary [--json-output]` | System summary (tag count, PLC status, DB size) |
| `scada shell` | Python REPL with data context |
| `scada health [--json-output]` | Backend health check |

## Python Packages (scada-reporter venv — Python 3.14)
| Package | Version | Purpose |
|---------|---------|---------|
| aiosqlite | 0.22.1 | Async SQLite (dev/test) |
| alembic | 1.14.0 | DB migrations |
| anyio | 4.13.0 | Async runtime |
| asyncpg | 0.31.0 | Async PostgreSQL |
| asyncua | 2.0 | OPC UA client/server (built-in server `app/collector/opcua_server.py`, port 4840) |
| bandit | 1.9.4 | Security linter (`just security`); B608 SQL nosec markers for SA-reflected names |
| bcrypt | 4.3.0 | Password hashing |
| python-snap7 | 3.0.0 | S7 PLC communication (`app/collector/s7_collector.py`) — free, no third-party software required |
| pandas | 3.0.3 | Data analysis & reporting |
| matplotlib | 3.11.0 | Static chart generation |
| plotly | 6.8.0 | Interactive web charts |
| apscheduler | 3.11.2 | Lightweight task scheduling |
| tabulate | 0.10.0 | ASCII table formatting |
| python-docx | 1.2.0 | Word document export |
| reportlab | 4.5.1 | Advanced PDF generation |
| jinja2 | 3.1.6 | HTML template rendering (autoescape=True) |
| cryptography | 49.0.0 | Crypto |
| fastapi | 0.115.x | Web framework |
| httpx | 0.28.0 | HTTP client (dev/test) |
| librt | 0.11.0 | |
| mypy | 2.1.0 | Type checker |
| openpyxl | 3.1.5 | Excel export |
| pre-commit | 4.6.0 | Git hook manager |
| pypdf | 6.13.2 | PDF processing |
| pyOpenSSL | 26.3.0 | SSL/TLS |
| pytest | 9.1.0 | Test framework |
| pytest-asyncio | 1.4.0 | Async test support |
| pytest-cov | 7.1.0 | Test coverage |
| pytest-xdist | 3.8.0 | Parallel test execution (`-n auto`, default via addopts) |
| pytest-randomly | 4.1.0 | Randomized test order (surfaces cross-test leakage) |
| pytest-watch | 4.2.0 | TDD hot reload (`ptw`) |
| python-jose | 3.3.0 | JWT tokens |
| python-multipart | 0.0.12 | Form parsing |
| pytz | 2026.2 | Timezone |
| redis | 5.2.0 | Redis client |
| ruff | 0.15.17 | Linter/formatter |
| safety | 3.8.1 | Dependency vulnerability scanner (`just security`) |
| sentry-sdk | 2.62.0 | Error tracking |
| sqlalchemy | 2.0.36 | ORM |
| uvicorn | 0.30.0 | ASGI server |
| weasyprint | 69.0 | PDF generation (GTK3 runtime required) |

## npm Global Packages
| Package | Version |
|---------|---------|
| @anthropic-ai/claude-code | 2.1.178 |
| @colbymchenry/codegraph | 1.0.1 |
| @google/gemini-cli | 0.46.0 |
| @juliusbrussee/caveman-code | |
| @komunite/kalfa | 1.0.0 |
| opencode-ai | 1.17.6 |
| prettier | 3.8.4 |
| typescript | 6.0.3 |

## Frontend (scada-reporter/frontend — pnpm)
| Package | Version | Purpose |
|---------|---------|---------|
| react | 19.x | UI framework |
| react-dom | 19.x | DOM renderer |
| react-router-dom | 7.x | Routing |
| i18next | 26.x | i18n core — 5 locales (en/tr/ru/de/ar) |
| react-i18next | 17.x | React i18n bindings; Arabic (`ar`) drives RTL (`html dir/lang`) |
| @tanstack/react-query | 5.x | Server state / data fetching |
| axios | 1.x | HTTP client |
| recharts | 3.x | Chart library |
| lucide-react | 1.x | Icon set |
| date-fns | 4.x | Date utilities (locale-aware) |
| html-to-image | 1.x | PNG export from DOM nodes |
| tailwindcss | 4.x | CSS framework |
| vite | 8.x | Dev server + bundler |
| vitest | 4.x | Unit test framework (jsdom env) |
| @testing-library/react | 16.x | React component testing |
| @testing-library/user-event | 14.x | User interaction simulation |
| jsdom | 29.x | DOM environment for tests |
| @playwright/test | 1.61.x | E2E browser tests (`pnpm e2e`; chromium installed) |
| puppeteer-core | 25.x | System-Chrome E2E driver (`pnpm e2e:verify`, `scripts/verify-dashboard.mjs`) |
| @hey-api/openapi-ts | 0.98.x | TypeScript client gen from OpenAPI spec (`pnpm gen-client`) |

## CLI Utilities
| Tool | Version | Description |
|------|---------|-------------|
| ripgrep (rg) | 15.1.0 | Fast code search |
| fd | 10.4.2 | Fast file find |
| bat | 0.26.1 | Syntax highlight cat |
| fzf | 0.73.1 | Fuzzy finder |
| jq | 1.8.1 | JSON processor |
| yq | 4.53.3 | YAML/JSON/XML processor |
| eza | 0.23.4 | Modern ls |
| zoxide | 0.9.9 | Smart cd |
| btop | 1.0.5 | System monitor |
| dust | 1.2.4 | Disk usage |
| hyperfine | 1.20.0 | Benchmark |
| tldr | 0.6.1 | Short man pages |
| 7-Zip | 15.2.0 | Archive tool |
| curl | 8.13.0 | HTTP client |
| xh | 0.25.3 | HTTPie-compatible HTTP client (Rust) |
| ruff | 0.15.17 | Python linter/formatter |
| agy | | AI commit message generator |

## Databases
| Tool | Version | Notes |
|------|---------|-------|
| DBeaver | 26.1.0 | Universal DB client (`C:\Program Files\DBeaver`) |
| SQLCMD | 13.x | SQL Server |
| SQL Server | 2016+ | `SQLCMD.EXE`, `bcp`, `OSQL` |
| asyncpg | 0.31.0 | Python async PostgreSQL driver |
| asyncua | 2.0 | OPC UA (SQLite-backed historian) |
| aiosqlite | 0.22.1 | Python async SQLite |
| PostgreSQL (TimescaleDB) | — | Target DB (Docker container: `docker/postgres`) |

## Infrastructure (Docker)
| Service | Image | Purpose |
|---------|-------|---------|
| PostgreSQL | timescale/timescaledb:latest-pg17 | Time-series DB |
| Redis | redis:7-alpine | Cache (not used in dev, for prod) |
| Grafana | grafana/grafana:latest | Monitoring dashboards |
| Portainer | portainer/portainer-ce:latest | Container management |

## Migration & CI
| Tool | Location | Notes |
|------|----------|-------|
| Alembic | `backend/alembic/` | Async migration (`env.py` async engine) |
| pre-commit | `.pre-commit-config.yaml` | Hooks **active** (`.git/hooks/pre-commit`); `ruff`, `ruff-format`, `mypy`, `trailing-whitespace`, `end-of-file-fixer`, `check-yaml/json/toml` |
| pyproject.toml | `backend/pyproject.toml` | pytest `asyncio_mode=auto`, ruff `line-length=100`, mypy config |
| GitHub Actions CI | `.github/workflows/ci.yml` | 3 jobs: backend (ruff·mypy·pytest·bandit) + frontend (tsc·eslint·vitest) + cli (agent-harness tests); triggers on push/PR to master |

## Build Tools
| Tool | Version | Notes |
|------|---------|-------|
| Cargo | 1.96.0 | Rust build |
| rustup | 1.96.0 | Rust toolchain mgr |
| rust-analyzer | | LSP |
| clippy | | Rust linter |
| rustfmt | | Rust formatter |
| Go | 1.26.4 | `go build`, `gofmt` |
| dotnet | 10.0.301 | .NET SDK |
| MinGW GCC | 15.2.0 | C/C++ compiler (posix-seh-ucrt) |
| GTK3 Runtime | | For WeasyPrint PDF (Win64) |
| WeasyPrint | 69.0 | Python PDF generator (GTK runtime required) |
| Node.js | 24.16.0 | JS/TS build |
| Prettier | 3.8.4 | Code formatter |

## SCADA / Siemens WinCC
| Tool | Notes |
|------|-------|
| WinCC Runtime | Siemens SCADA system |
| CommonArchiving | Archive manager, redundancy agent |
| SIMATIC OAM | Industrial communication |
| OPC Tags | OPC server interface |
| ACE | Advanced Control Engine |
| KEPServerEX | External OPC UA server (optional — the built-in OPC UA server on port 4840 is used) |
| UA Expert | OPC UA test client (download: unified-automation.com) |
| Siemens S7-1500 | PLC (native S7 protocol over TCP port 102) |
| Snap7 | `python-snap7` 3.0.0 — pure Python S7 library for Siemens S7 PLCs |
| S7 Collector | `backend/app/collector/s7_collector.py` — S7 PLC connection + tag reading |
| Built-in OPC UA Server | `backend/app/collector/opcua_server.py` — port 4840, publishes the latest values from the DB |

## VS Code
| Tool | Path |
|------|------|
| code.cmd | `C:\Users\Administrator\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd` |
| code-tunnel.exe | VS Code tunnel |

## Notes
- **Python 3.14** is the primary Python (`python` → `C:\Python314\python.exe`)
- **Python 3.12** still available at `C:\Program Files\Python312\python.exe`
- **scada-reporter backend venv**: `scada-reporter/backend/.venv/` (Python 3.14, uv-managed)
- **scada CLI** requires `uv pip install -e scada-reporter/agent-harness` from project root (`just install-agent`)
- **Backend API**: 15 router grubu — auth, tags, dashboard, reports, advanced_reports, excel_templates, plc, query, explore, groups, annotations, realtime (SSE), users, ai, license (`/api/*`)
- **Frontend pages**: Dashboard (3 tabs), Trend (zoom/pan/PNG/Excel/right-click menu/height setting), Reports, Advanced Reports, Excel Templates, Tags, PLC Management, Live Metrics, User Operations (admin), Settings (preferences + license status/upload). Sidebar shows a license-mode badge.
- **i18n / RTL**: 5 languages (en/tr/ru/de/ar) via i18next; Arabic flips layout to RTL (`html dir/lang`, logical Tailwind utilities). Language persists per-user (`/api/auth/me`) + localStorage
- **E2E browser tests**: Playwright (`pnpm e2e`, chromium) + puppeteer-core system-Chrome fallback (`pnpm e2e:verify`). Backend must be on :8001 for data
- **Auth**: the `/api/auth/token` endpoint expects OAuth2 **form-data**, not JSON. `curl -d "username=...&password=..."`
- **Default users**: `just seed-users` → admin/admin123, operator/operator123
- **Licensing** (commercial, optional): signed-JWT (RS256/ES256) verified at startup against the env public key. Runtime modes — `licensed` (features/quota per claims) / `demo` (read-only, premium features off, tag list capped at `SCADA_LICENSE_DEMO_MAX_TAGS`=25) / `full` (no public key ⇒ dev/tests unaffected); `SCADA_LICENSE_REQUIRED=true` is strict fail-closed. Enforcement in `app/api/license_guard.py` (feature gates + `max_tags` quota + demo read-only). Admins hot-reload a license via `POST /api/license` (Settings → License, no restart). Vendor tooling: `scripts/generate_license.py` (`just license "keygen ..."` / `"issue ..."`) signs/issues with a private key. Deploy guide `docs/license-deployment.md`; env in `.env.production.example`. Keys/tokens (`*.pem`/`*.jwt`) are gitignored.
- **Backend reload (dev)**: `just run-backend` runs uvicorn `--reload --reload-dir app --reload-exclude "*.db*"` so the watcher only follows `app/` code, not the dev DB churn (poller writes). If reload wedges (reloader parent respawns its child, so a port kill isn't enough), use `just restart-backend` (stops all `python`, then starts clean). Override `OPCUA_SERVER_PORT`/`DATABASE_URL` env to run a second instance without clashing on :4840.
- **Architecture**: S7 PLC → Snap7 (s7_collector) → SQLite (dev) / PostgreSQL (prod) → built-in OPC UA server (port 4840) + REST API. No paid third-party software (KEPServerEX) required.
- **Stats engine**: numpy-only (scipy yok) — `np.polyfit` + manuel R²
- **Docker not installed on host** — compose files ready, needs Docker Desktop or Docker Engine
- **RTK** (Rust Token Killer) v0.42.4 at `C:\Users\aa\.local\bin\rtk.exe` — **not on the default bash/PowerShell PATH** (so a bare `rtk`/`which rtk` fails; call the full path or add `~/.local/bin` to PATH). Wraps shell commands to cut output tokens: prefix commands (`rtk git status`, `rtk pytest -q`); `rtk gain` shows savings (~85% in a test), `rtk proxy <cmd>` runs raw, `rtk rewrite <cmd>` applies rewrite rules. Integrations present for other agents: opencode plugin `~/.config/opencode/plugins/rtk.ts` + Codex `~/.codex/RTK.md` (rule: "always prefix shell commands with `rtk`").
- **caveman** token-reduction skill installed as an enabled Claude Code plugin (`caveman@caveman`, user scope — verify with `claude plugin list`). Slash commands `/caveman`, `/caveman-commit`, `/caveman-review`, `/caveman-stats`, `/caveman-compress` (and "caveman mode") activate only after a Claude Code **restart** (plugins load at session start). Installer: `npx -y github:JuliusBrussee/caveman` (npm `@juliusbrussee/caveman-code`); pins remote fetches to a release tag; uninstall via `... -- --uninstall`.
- **codegraph** connected as a Claude Code MCP server (`~/.claude.json`) and the repo is indexed (204 files / 2530 nodes / 4861 edges; `.codegraph/` is gitignored). Use `codegraph explore "<question>"` / `codegraph node <symbol|file>` to get callers + covering tests + verbatim source in one call. MCP tools (`codegraph_explore`/`codegraph_node`) require a Claude Code restart; the shell CLI always works. Keep the index fresh with `codegraph sync`.
- **Test DB isolation**: backend tests share one in-memory SQLite engine (StaticPool); an autouse fixture in `tests/conftest.py` clears all tables before each test, so order is irrelevant (`pytest-randomly` shuffles every run). Savepoint-rollback isolation is unreliable on pysqlite (no real outer BEGIN). Default run is parallel (`pytest-xdist -n auto`); use `-n0` to debug serially.
- **Windows**: no `python3` — use `python`; a `~/bin/python3.exe` shim covers tools/hooks that hard-code `python3`.
- **GitHub Actions CI**: `.github/workflows/ci.yml` — on push/PR, backend (ruff·mypy·pytest·bandit) + frontend (tsc·eslint·vitest) run automatically
- **Security scan**: `just security` → bandit (Python code) + safety (dependency CVEs)
- **GitHub Pages**: User site at `b110rpsrv2` (this machine)
- **Tailscale** is connected (network overlay)
