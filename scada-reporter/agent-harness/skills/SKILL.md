---
name: scada-reporter-cli
description: Agent-native CLI for EKONT SMART REPORT — PLC tag management, live values, trend analysis and report generation
author: EKONT SMART REPORT Team
commands:
  # Auth
  - scada auth login <username> [--password TEXT] [--json-output]
  - scada auth me [--json-output]
  - scada auth register <username> <email> [--password TEXT] [--full-name TEXT] [--role admin|operator|viewer] [--json-output]
  # Tags
  - scada tags list [--json-output]
  - scada tags create --node-id <id> --name <name> [--description TEXT] [--unit TEXT] [--device TEXT] [--channel TEXT] [--json-output]
  - scada tags update <id> [--unit TEXT] [--device TEXT] [--channel TEXT] [--description TEXT] [--min-alarm N] [--max-alarm N] [--json-output]
  - scada tags delete <id> [--json-output]
  - scada tags readings <id> [--start ISO] [--end ISO] [--limit N] [--json-output]
  # Dashboard
  - scada dashboard overview [--json-output]
  - scada dashboard current-values [--alarm-only] [--watch N] [--json-output]
  - scada dashboard trend <tag_id>... [--hours N] [--json-output]
  # Reports
  - scada reports generate --tag-ids 1,2,3 --start ISO --end ISO [--interval hourly|daily] [--format json|excel] [--json-output]
  - scada reports list-history [--json-output]
  - scada reports download-history <id> [--output FILE] [--json-output]
  # Explore
  - scada explore schema [--json-output]
  - scada explore summary [--json-output]
  - scada explore tags [--json-output]
  # Query / Shell
  - scada query run "SELECT ..." [--limit N] [--json-output]
  - scada shell
  # Operational write helpers (JSON output by default)
  - scada watchlist add <tag_id>
  - scada watchlist remove <tag_id>
  - scada annotations add --ts ISO --text TEXT [--tag-id N]
  - scada annotations delete <annotation_id>
  - scada templates create --payload JSON
  - scada templates update <template_id> --payload JSON
  - scada templates run <template_id> [--start ISO] [--end ISO]
  - scada scheduled create --payload JSON
  - scada groups create <name> [--parent-id N] [--sort-order N]
  - scada groups assign <group_id> --tag-ids 1,2,3
  - scada plc create <name> [--ip TEXT] [--rack N] [--slot N]
  - scada users create <username> --email EMAIL --password PASSWORD --confirm
  # Health
  - scada health [--json-output]
environment:
  SCADA_API_URL: "http://localhost:8001"
  SCADA_TOKEN: "<jwt>"
output_format: JSON (--json-output flag ile; reports generate ayrıca --format json destekler)
alarm_state_values:
  overflow: "value > 1,000,000 or quality != 192 (PLC connection issue)"
  max: "value exceeded tag's max_alarm threshold"
  min: "value fell below tag's min_alarm threshold"
  null: "normal, no alarm"
---

# EKONT SMART REPORT Agent CLI

Coding agent access to the water/wastewater plant SCADA data acquisition and reporting system.

## Installation

```bash
uv pip install -e scada-reporter/agent-harness
```

## Agent Usage

Use each command's `--json-output` flag for machine-readable output.
The token is stored in `~/.config/scada-reporter/config.json`.

### Discovery

```bash
scada tags list --json-output                    # List all tags
scada dashboard current-values --json-output     # Live values
scada dashboard overview --json-output           # System state
```

### Analysis

```bash
scada dashboard trend 1 2 --hours 48 --json-output  # 48-hour trend
scada tags readings 1 --limit 100 --json-output     # Last 100 readings
```

### Reports

```bash
scada reports generate --tag-ids 1,2 --start 2024-01-01T00:00:00 --end 2024-01-02T00:00:00 --format json
```
