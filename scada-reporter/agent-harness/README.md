# EKONT SMART REPORT Agent CLI — Harness

> **For agent usage (setup, commands, workflows), see [`/AGENTS.md`](../../AGENTS.md).**

This directory contains the `scada` CLI harness — a Click-based, agent-native
command-line interface to the EKONT SMART REPORT REST API.

## Install (editable / dev)

```bash
# From repo root (recommended):
just install-agent

# Or directly:
uv pip install -e scada-reporter/agent-harness
```

## Run Tests

```bash
just test-agent
# or:
cd scada-reporter/agent-harness && ../backend/.venv/Scripts/pytest tests/ -v
```

## Structure

```
src/scada_reporter_cli/
├── cli.py           # Click group + REPL entry point
├── commands/        # auth, tags, dashboard, reports, query, explore, shell, …
└── utils/           # config (token store), client helper, REPL skin
skills/
└── SKILL.md         # Machine-readable skill definition (do not edit manually)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCADA_API_URL` | `http://localhost:8001` | Backend API address |
| `SCADA_TOKEN` | — | JWT token (optional) |
