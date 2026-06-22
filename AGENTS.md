# EKONT SMART REPORT — Agent Guide

Water/wastewater plant SCADA data acquisition and reporting system.
This file is the **single authoritative agent guide**. All secondary agent docs
point here.

---

## Overview

The project is designed **agent-native** following the CLI-Anything approach.
Coding agents (Claude Code, OpenCode, GitHub Copilot, Cursor, Windsurf) can
interact with the system through a dedicated CLI, a Claude Code plugin, and an
MCP server — without needing to parse HTML or scrape a UI.

### Agent-Native Principles

1. **JSON output** — use each command's `--json-output` option for machine-readable output; `reports generate --format json` returns JSON report data
2. **REPL mode** — `scada` with no subcommand opens an interactive REPL
3. **Stateful session** — JWT token is stored in `~/.config/scada-reporter/config.json`
4. **Discoverability** — `scada tags list`, `scada dashboard overview`, `scada explore schema`
5. **SKILL.md** — agents discover CLI capabilities from `scada-reporter/agent-harness/skills/SKILL.md`

---

## Repository Layout (agent-relevant)

```
scada-reporter/
├── agent-harness/            # Agent-native CLI (Click + JSON + REPL)
│   ├── src/scada_reporter_cli/
│   └── skills/
│       └── SKILL.md          # Machine-readable skill definition
├── .claude-plugin/           # Claude Code marketplace registration
│   └── marketplace.json
├── commands/                 # Slash commands (scada-login, scada-tags, scada-dashboard, scada-reports)
└── guides/                   # Pointer files (see this file instead)
mcp-servers/
└── mcp-scada/                # MCP server: resources + tools via FastMCP
```

---

## Setup (30 seconds)

**Requires Python 3.14+ (single supported baseline).**

### 1. Start the Backend

From the **repo root**:

```bash
just run-backend          # hot-reload, http://localhost:8001
```

The built-in OPC UA server comes up at `opc.tcp://localhost:4840` automatically.
Simulation mode works when no PLC is present.

### 2. Install the Agent CLI

From the **repo root**:

```bash
just install-agent        # installs scada-reporter/agent-harness (editable)
```

Or manually:

```bash
uv pip install -e scada-reporter/agent-harness
```

Verify:

```bash
scada --help
scada health
```

### 3. Log In

```bash
scada auth login admin          # prompts for password
# Default credentials: admin/admin123, operator/operator123
```

The JWT token is saved to `~/.config/scada-reporter/config.json` and reused
automatically. Alternatively, set `SCADA_TOKEN=<jwt>` in the environment.

### 4. Per-Agent Configuration

#### Claude Code

```bash
# Available slash commands (loaded from scada-reporter/commands/):
/scada-login
/scada-tags list
/scada-dashboard current-values
/scada-reports
```

#### OpenCode

`AGENTS.md` (this file) is loaded automatically. Run CLI commands directly.

#### Cursor / Copilot / Windsurf

```bash
scada <command> --json-output   # command-local machine-readable JSON where supported
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCADA_API_URL` | `http://localhost:8001` | Backend API address |
| `SCADA_TOKEN` | — | JWT token (optional, overrides stored token) |

---

## Quick-Start Commands

```bash
# System health
scada health

# Discover tags
scada tags list --json-output

# Live values
scada dashboard current-values --json-output

# System overview
scada dashboard overview --json-output

# Database schema
scada explore schema --json-output

# Last 5 readings for tag ID 1
scada tags readings 1 --limit 5 --json-output

# 24-hour trend for tags 1 and 2
scada dashboard trend 1 2 --hours 24 --json-output

# Read-only SQL
scada query run "SELECT name, value, unit FROM tags LIMIT 5" --json-output

# Python REPL with data preloaded
scada shell
```

---

## CLI Command Groups

Most read-oriented commands support `--json-output` for machine-readable output and all groups support `--help` for usage. Prefer `--json-output` in scripts; the root `--json` flag is not consistently consumed by subcommands.

| Group | Purpose |
|-------|---------|
| `auth` | Authenticate: login, logout, show current user |
| `tags` | PLC tag management: list, create, update, readings |
| `dashboard` | Live values, system overview, trend data |
| `reports` | Generate Excel/PDF reports for a time range |
| `query` | Run read-only SQL against the SCADA database |
| `explore` | Database schema discovery and summary statistics |
| `shell` | Interactive Python REPL with data pre-loaded |
| `agent` | AI agent workflow helpers: monitor, analyze |
| `watchlist` | Manage tag watchlists for monitoring |
| `annotations` | Annotate time-series events on tags |
| `templates` | Report template management |
| `scheduled` | Schedule and manage recurring reports |
| `groups` | Tag group management |
| `plc` | PLC connection configuration |
| `users` | User management (admin only) |

`health` is a top-level command (not a group): `scada health`. Use `--json-output` for machine-readable output: `scada health --json-output`.

---

## Operational Workflows

### Discovery Flow

```bash
scada health                          # 1. Check API connectivity
scada auth login <user>               # 2. Authenticate
scada tags list --json-output          # 3. Discover available tags
scada dashboard overview --json-output # 4. Learn system state
```

### Current State Query

```bash
scada dashboard current-values --json-output | jq '.[] | {device, name, value, unit}'
```

### Trend Analysis

```bash
scada dashboard trend 1 2 --hours 24 --json-output \
  | jq '.[] | {name, avg: (.data | map(.v) | add / length)}'
```

### Report Generation

```bash
scada reports generate \
  --tag-ids 1,2,3 \
  --start "<ISO-datetime>" \
  --end "<ISO-datetime>" \
  --format json
```

### First-Use Scenario

```bash
scada auth login operator             # 1. Log in
scada health                          # 2. Connectivity check
scada tags list --json-output          # 3. See all tags
scada dashboard current-values        # 4. Live values as table
scada tags readings 1 --limit 5       # 5. Last 5 readings for tag 1
```

### Error Handling

- `--json-output` returns machine-readable output on supported commands
- Errors are returned as `{"error": true, "detail": "..."}`
- Session can be passed via `SCADA_TOKEN` env var (useful in CI/scripts)

---

## MCP Server (Claude Code native)

`mcp-servers/mcp-scada/` exposes the SCADA system as an MCP server via
FastMCP. It provides resources (schema, tag list) and workflow prompts — Claude
Code reads these natively without the CLI layer.

Configuration lives in `mcp.json` at the repo root.

---

## Reference

| Location | Purpose |
|----------|---------|
| `scada-reporter/agent-harness/skills/SKILL.md` | Machine-readable skill definition (command list, env vars, alarm states) |
| `scada-reporter/.claude-plugin/marketplace.json` | Claude Code marketplace registration |
| `scada-reporter/commands/` | Slash command markdown files |
| `mcp-servers/mcp-scada/` | MCP server source |
| `CLAUDE.md` | Project-wide developer conventions (not agent-facing) |
| `TOOL.md` | Tool configuration (not agent-facing) |
