---
name: scada-reporter-cli
description: Agent-native CLI for SCADA Reporter — PLC tag management, live values, trend analysis and report generation
author: SCADA Reporter Team
commands:
  # Auth
  - scada auth login <username>
  - scada auth me
  - scada auth register <username> <email>
  # Tags
  - scada tags list [--json-output]
  - scada tags create --node-id <id> --name <name> [--unit] [--device] [--channel]
  - scada tags update <id> [--unit] [--device] [--channel] [--description] [--min-alarm N] [--max-alarm N] [--json-output]
  - scada tags delete <id>
  - scada tags readings <id> [--start ISO] [--end ISO] [--limit N] [--json-output]
  # Dashboard
  - scada dashboard overview [--json-output]
  - scada dashboard current-values [--alarm-only] [--watch N] [--json-output]
  - scada dashboard trend <tag_id>... [--hours N] [--json-output]
  # Reports
  - scada reports generate --tag-ids 1,2,3 --start ISO --end ISO [--interval hourly|daily] [--format json|excel]
  - scada reports list-history [--json-output]
  - scada reports download-history <id> [--output FILE] [--json-output]
  # Explore
  - scada explore schema [--json-output]
  - scada explore summary [--json-output]
  - scada explore tags [--json-output]
  # Query / Shell
  - scada query run "SELECT ..." [--limit N] [--json-output]
  - scada shell
  # Health
  - scada health [--json-output]
environment:
  SCADA_API_URL: "http://localhost:8001"
  SCADA_TOKEN: "<jwt>"
output_format: JSON (--json flag ile)
alarm_state_values:
  overflow: "value > 1,000,000 or quality != 192 (PLC connection issue)"
  max: "value exceeded tag's max_alarm threshold"
  min: "value fell below tag's min_alarm threshold"
  null: "normal, no alarm"
---

# SCADA Reporter Agent CLI

Coding agent access to the water/wastewater plant SCADA data acquisition and reporting system.

## Installation

```bash
uv pip install -e scada-reporter/agent-harness
```

## Agent Usage

All commands produce machine-readable output with the `--json` flag.
The token is stored in `~/.config/scada-reporter/config.json`.

### Discovery

```bash
scada tags list --json                    # List all tags
scada dashboard current-values --json     # Live values
scada dashboard overview --json           # System state
```

### Analysis

```bash
scada dashboard trend 1 2 --hours 48 --json  # 48-hour trend
scada tags readings 1 --limit 100 --json     # Last 100 readings
```

### Reports

```bash
scada reports generate --tag-ids 1,2 --start 2024-01-01T00:00:00 --end 2024-01-02T00:00:00 --format json
```
