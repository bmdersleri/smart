# EKONT SMART REPORT Agent CLI

A CLI tool designed for coding agents (Claude Code, OpenCode, GitHub Copilot,
Cursor, Windsurf, etc.) to use the EKONT SMART REPORT REST API.

## Installation

```bash
pip install -e scada-reporter/agent-harness
# or
uv pip install -e scada-reporter/agent-harness
```

## Usage

```bash
# Login
scada auth login admin

# List tags (--json for agents)
scada tags list --json

# Live values
scada dashboard current-values

# SQL query (read-only)
scada query run "SELECT name, value, unit FROM tags LIMIT 5" --json

# Database discovery
scada explore schema
scada explore tags

# Python REPL (data loaded)
scada shell

# Agent-native usage
scada tags readings 1 --limit 5 --json | jq '.[] | {t: .timestamp, v: .value}'
```

## For Agents

All commands produce machine-readable JSON output with the `--json` flag.
The token is stored in `~/.config/scada-reporter/config.json` or read from
the `SCADA_TOKEN` environment variable.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCADA_API_URL` | `http://localhost:8001` | Backend API address |
| `SCADA_TOKEN` | — | JWT token (optional) |
