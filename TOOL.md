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
| Claude Code | 2.1.177 | `claude` (npm) |
| Gemini CLI | 0.46.0 | `gemini` (npm) |
| opencode | 1.17.6 | `opencode` (npm) |
| Codex | | `C:\Users\Administrator\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe` |
| codegraph | 1.0.1 | `codegraph` (npm) |
| Kalfa | 1.0.0 | `kalfa` (npm) |
| caveman-code | | `caveman-code` (npm) |
| RTK | 0.42.4 | `rtk` — Rust Token Killer (LLM token optimizer) |
| FCC (Free Claude Code) | | `fcc-claude`, `fcc-init`, `fcc-server` |

## Python Packages (scada-reporter venv — Python 3.14)
| Package | Version | Purpose |
|---------|---------|---------|
| aiosqlite | 0.22.1 | Async SQLite (dev/test) |
| alembic | 1.14.0 | DB migrations |
| anyio | 4.13.0 | Async runtime |
| asyncpg | 0.31.0 | Async PostgreSQL |
| asyncua | 2.0 | OPC UA client/server (dahili server `app/collector/opcua_server.py`) |
| bcrypt | 4.3.0 | Password hashing |
| python-snap7 | 3.0.0 | S7 PLC communication (pure Python, no DLL) |
| pandas | 3.0.3 | Data analysis & reporting |
| matplotlib | 3.11.0 | Static chart generation |
| plotly | 6.8.0 | Interactive web charts |
| apscheduler | 3.11.2 | Lightweight task scheduling |
| tabulate | 0.10.0 | ASCII table formatting |
| python-docx | 1.2.0 | Word document export |
| reportlab | 4.5.1 | Advanced PDF generation |
| jinja2 | 3.1.6 | HTML template rendering |
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
| python-jose | 3.3.0 | JWT tokens |
| python-multipart | 0.0.12 | Form parsing |
| pytz | 2026.2 | Timezone |
| redis | 5.2.0 | Redis client |
| ruff | 0.15.17 | Linter/formatter |
| sentry-sdk | 2.62.0 | Error tracking |
| sqlalchemy | 2.0.36 | ORM |
| uvicorn | 0.30.0 | ASGI server |
| weasyprint | 62.3 | PDF generation |

## npm Global Packages
| Package | Version |
|---------|---------|
| @anthropic-ai/claude-code | 2.1.177 |
| @colbymchenry/codegraph | 1.0.1 |
| @google/gemini-cli | 0.46.0 |
| @juliusbrussee/caveman-code | |
| @komunite/kalfa | 1.0.0 |
| opencode-ai | 1.17.6 |
| prettier | 3.8.4 |
| typescript | 6.0.3 |

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
| Redis | redis:7-alpine | Cache / Celery broker |
| Grafana | grafana/grafana:latest | Monitoring dashboards |
| Portainer | portainer/portainer-ce:latest | Container management |

## Migration & CI
| Tool | Location | Notes |
|------|----------|-------|
| Alembic | `backend/alembic/` | Async migration (`env.py` async engine) |
| pre-commit | `.pre-commit-config.yaml` | `ruff`, `mypy`, `trailing-whitespace`, `end-of-file-fixer` |

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
| WeasyPrint | | Python PDF generator (GTK runtime required) |
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
| KEPServerEX | OPC server (OPC UA certs generated via `backend/gen_cert.py`) |
| UA Expert | OPC UA test client (download: unified-automation.com) |
| Siemens S7-1500 | PLC (native S7 protocol over TCP port 102) |
| Snap7 | `python-snap7` 3.0.0 — pure Python S7 library for Siemens S7 PLCs |
| S7 Client | `backend/app/collector/s7_client.py` — S7 PLC connection manager |

## VS Code
| Tool | Path |
|------|------|
| code.cmd | `C:\Users\Administrator\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd` |
| code-tunnel.exe | VS Code tunnel |

## Notes
- **Python 3.14** is the primary Python (`python` → `C:\Python314\python.exe`)
- **Python 3.12** still available at `C:\Program Files\Python312\python.exe`
- **scada-reporter backend venv**: `scada-reporter/backend/.venv/` (Python 3.14, uv-managed)
- **Docker not installed on host** — compose files ready, needs Docker Desktop or Docker Engine
- **RTK** installed for LLM token optimization. Run `rtk init -g` for Claude Code integration.
- **GitHub Pages**: User site at `b110rpsrv2` (this machine)
- **Tailscale** is connected (network overlay)
