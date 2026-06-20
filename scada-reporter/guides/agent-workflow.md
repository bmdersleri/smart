# Agent Workflow — EKONT SMART REPORT

This guide describes how coding agents work with EKONT SMART REPORT.

## Discovery Flow

1. `scada health` — Check API connectivity
2. `scada auth login` — Authenticate
3. `scada tags list --json` — Discover available tags
4. `scada dashboard overview --json` — Learn the system state

## Operational Flows

### Current State Query

```bash
scada dashboard current-values --json | jq '.[] | {device, name, value, unit}'
```

### Trend Analysis

```bash
scada dashboard trend 1 2 --hours 24 --json | jq '.[] | {name, avg: (.data | map(.v) | add / length)}'
```

### Report Generation

```bash
scada reports generate --tag-ids 1,2,3 --start "<yesterday>" --end "<today>" --format json
```

## Error Handling

- The `--json` flag always returns machine-readable output
- Errors are returned in `{"error": true, "detail": "..."}` format
- Sessions can be carried via the `SCADA_TOKEN` env var

## First-Use Scenario

1. `scada auth login operator` — Log in
2. `scada health` — Connectivity check
3. `scada tags list --json` — See tags
4. `scada dashboard current-values` — See live values as a table
5. `scada tags readings 1 --limit 5` — Check the last 5 readings
