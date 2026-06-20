# EKONT SMART REPORT — Agent Guide

This project is designed **agent-native** following the CLI-Anything approach.
Coding agents (Claude Code, OpenCode, GitHub Copilot, Cursor, Windsurf)
can use the EKONT SMART REPORT system seamlessly through the tools below.

## Agent CLI

```
scada-reporter/agent-harness/
├── src/scada_reporter_cli/   # Click CLI (JSON + REPL)
├── setup.py
└── skills/SKILL.md           # Agent skill definition
```

Install: `uv pip install -e scada-reporter/agent-harness`

## Claude Code Plugin

```
scada-reporter/.claude-plugin/marketplace.json   # Marketplace registration
scada-reporter/cli-anything-plugin/               # Plugin definition
scada-reporter/commands/                          # Slash commands
scada-reporter/guides/                            # Methodology guides
```

## Agent-Native Principles

1. **JSON output**: all CLI commands produce machine-readable output with the `--json` flag
2. **REPL mode**: the `scada` command opens an interactive REPL by default
3. **Stateful session**: the JWT token is stored in `~/.config/scada-reporter/config.json`
4. **Discoverability**: the system describes itself via `scada tags list`, `scada dashboard overview`
5. **SKILL.md**: agents can discover CLI capabilities from the skill file

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCADA_API_URL` | `http://localhost:8001` | Backend address |
| `SCADA_TOKEN` | — | JWT token (optional) |

## Quick Start

```bash
# 1. Install the CLI
uv pip install -e scada-reporter/agent-harness

# 2. Log in
scada auth login admin

# 3. Explore the system
scada tags list --json
scada dashboard current-values
scada health
```
