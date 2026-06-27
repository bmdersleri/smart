# scada doctor

Agent-native triage for the CLI session and backend surface.

## Usage

```bash
scada doctor
scada doctor --json-output
```

## What it checks

- API reachability
- Token availability and validation
- `/ready` status
- Current catalog size from `system_health`

## Output

- Human mode prints a short summary plus issues, if any.
- `--json-output` returns a structured report for automation.
