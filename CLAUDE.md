# SCADA Reporter

Water/wastewater plant SCADA data acquisition and reporting system.

## Project Structure

```
scada-reporter/
├── backend/       # Python FastAPI backend (:8001)
│   ├── app/
│   │   ├── api/        # REST API (auth/dashboard/tags/reports/advanced_reports/plc/query/explore)
│   │   ├── collector/  # Snap7 S7 collector + built-in OPC UA server + poller
│   │   ├── core/       # Config, DB, security (JWT)
│   │   ├── models/     # Tag, User, PlcConfig, Watchlist, ReportHistory/Template/Scheduled/Archive
│   │   └── reports/    # Excel / PDF generators
│   ├── tests/          # pytest async tests (185+)
│   ├── alembic/        # DB migration files
│   ├── seed_users.py   # admin + operator user creation
│   ├── pyproject.toml  # pytest/ruff/mypy config
│   ├── .venv/          # Python venv (managed with uv, Python 3.14)
│   └── requirements.txt
├── frontend/      # React 19 + Vite + Tailwind CSS v4 + TanStack Query (:5173)
│   ├── src/
│   │   ├── pages/      # Dashboard, Trend, Reports, AdvancedReports, Tags, PlcConfig, Settings
│   │   ├── context/    # AuthContext, SettingsContext (localStorage)
│   │   └── api/        # Generated OpenAPI TypeScript client
│   ├── openapi-ts.config.ts  # TypeScript API client generator
│   └── package.json
├── agent-harness/ # Agent-native CLI (Click + JSON + REPL)
│   ├── src/scada_reporter_cli/
│   └── setup.py
├── commands/      # Claude Code slash commands (markdown)
├── guides/        # Agent methodology guides
├── .claude-plugin/  # Claude Code marketplace registration
└── AGENTS.md      # Agent usage guide
docker/        # TimescaleDB + Redis + Grafana
```

## Commands

### Development
- **Backend + Frontend in parallel:** `just dev`
- **Backend only:** `just run-backend`
- **Frontend only:** `just run-frontend`
- **Install dependencies:** `just install`

### Test
- **Run tests:** `just test`
- **Coverage report:** `just test-cov`
- **TDD hot reload:** `just test-watch`

### Database
- **Apply migration:** `just migrate`
- **Create migration:** `just makemigration msg="description"`
- **Roll back migration:** `just migrate-down`
- **Migration history:** `just migrate-history`
- **Add PLC tags:** `just seed-tags`
- **Default users:** `just seed-users` *(admin/admin123, operator/operator123)*
- **WinCC xlsx catalog:** `just seed-catalog`

### Quality
- **Lint:** `just lint`
- **Lint + auto-fix:** `just lint-fix`
- **Format:** `just format`
- **Type check:** `just typecheck`
- **All checks (CI):** `just check`

### Agent CLI
- **Install the CLI:** `just install-agent`
- **Test it:** `just test-agent`
- **REPL (interactive):** `just agent-repl`
- **SQL query:** `just agent cli_args="query run 'SELECT * FROM tags LIMIT 5' --json"`
- **Database discovery:** `just agent cli_args="explore schema"`
- **Python REPL:** `just agent cli_args="shell"`
- **Single command:** `just agent cli_args="tags list --json"`

### Tools
- **Generate TS API client:** `just gen-client` *(while backend running)*
- **PLC connection test:** `just test-plc`
- **Start/stop Docker:** `just docker-up` / `just docker-down`
- **Project tree:** `just tree`

## Database

- Dev/test: SQLite (`scada_reporter.db`) — no Docker required
- Prod: PostgreSQL (TimescaleDB) + Redis (via Docker)
- Copy `.env.example` → `.env` and set the env vars

## Available Tools

| Tool | Version | Usage |
|------|---------|-------|
| Python | 3.14.6 | `python` or `.venv\Scripts\activate` |
| uv | 0.11.21 | Fast pip alternative |
| ruff | 0.15.17 | Python linter + formatter |
| mypy | 2.1.0 | Python type checker |
| Node.js | 24.16.0 | JS runtime |
| pnpm | 11.6.0 | Fast npm alternative |
| TypeScript | 6.0.3 | `tsc` |
| Prettier | 3.8.4 | Code formatter |
| Git | 2.54.0 | Version control |
| Go | 1.26.4 | Go language |
| Rust | 1.96.0 | `rustc` + `cargo` |
| .NET SDK | 10.0.301 | Dotnet |
| ripgrep | 15.1.0 | Fast code search (`rg`) |
| fd | 10.4.2 | Fast file find |
| bat | 0.26.1 | View with syntax highlight |
| fzf | 0.73.1 | Fuzzy finder |
| jq | 1.8.1 | JSON processing |
| yq | 4.53.3 | YAML/JSON/XML processing |
| gh | 2.94.0 | GitHub CLI |
| lazygit | 0.62.2 | Terminal Git UI |
| delta | 0.19.2 | Git diff viewer |
| tldr | 0.6.1 | Short man pages |
| eza | 0.23.4 | Modern ls |
| zoxide | 0.9.9 | Smart cd (`z <dir>`) |
| btop | 1.0.5 | System monitor |
| dust | 1.2.4 | Disk usage analysis |
| hyperfine | 1.20.0 | Benchmark |
| just | 1.52.0 | Command runner |

## Notes

- **Built-in OPC UA Server**: `opc.tcp://localhost:4840` — comes up automatically when the backend starts. No paid third-party software (KEPServerEX etc.) required.
- **S7 PLC connection**: direct to S7-1500 over TCP 102 via Snap7 (free, pure Python). Configured with the `S7_HOST`/`S7_RACK`/`S7_SLOT` env vars.
- **Simulation mode**: the backend runs fine when no PLC is present or reachable.
- **OAuth2 login**: `/api/auth/token` expects **form-data**, not JSON. The frontend sends it correctly; use `curl -d "username=...&password=..."`.
- **WeasyPrint PDF**: requires the GTK3 runtime on Windows (installed — working).
- **Stats engine**: numpy-only (scipy is not in the venv) — `np.polyfit` + manual R².
- Start the backend with `just run-backend`
- Fast package install with `uv pip install ...`
- pre-commit hooks are active — ruff + mypy + format checks run on every commit
- Update the frontend TS client: `just gen-client` while the backend is running
