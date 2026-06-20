# Test Plan — EKONT SMART REPORT Agent CLI

## Unit Tests

| Test | Description |
|------|-------------|
| `test_health_command` | Health command should return an error message when the API is down |
| `test_list_tags_no_auth` | tags list should return an error without a token |
| `test_dashboard_overview_no_auth` | dashboard should return an error without a token |
| `test_repl_help` | REPL help should work |
| `test_cli_invocation` | The --help flag should work |
| `test_repl_exit` | REPL should close on exit |
| `test_repl_quit` | REPL should close on quit |
| `test_repl_invalid_command` | An invalid command should not crash |
| `test_group_help` | Each group (auth/tags/dashboard/reports) --help should run |

## Mocking Convention

Command tests mock the **client seam** — `scada_reporter_cli.commands.<mod>.get_client`
(imported into each command module from `utils.client_helper`) — never the internal
`get_token` / `ScadaClient` names (commands no longer import those directly, so patching
them raises `AttributeError`).

- **Authenticated path:** `patch("scada_reporter_cli.commands.<mod>.get_client",
  return_value=(mock_client, True))` and shape `mock_client` to return the fixtures the
  assertions expect.
- **No-auth path:** patch `scada_reporter_cli.utils.client_helper.get_token` to `None`,
  letting the real `get_client` emit the friendly "auth login" message that the test asserts.

## E2E Tests

While the backend is running:

```bash
pytest tests/ -v --api-url http://localhost:8001
```

| Test | Description |
|------|-------------|
| `test_auth_login_logout` | Login → get token → call /api/auth/me |
| `test_tags_crud` | Create tag → list → delete |
| `test_dashboard_live` | Call overview + current-values |
| `test_report_generate` | Generate report → validate JSON output |

## Test Results

```
34 passed
```

Run in CI (`.github/workflows/ci.yml` → `cli` job) and locally:
`../backend/.venv/Scripts/pytest tests/ -q`
