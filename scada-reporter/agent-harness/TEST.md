# Test Plan — SCADA Reporter Agent CLI

## Unit Tests

| Test | Description |
|------|-------------|
| `test_health_command` | API kapalıyken health komutu hata mesajı dönmeli |
| `test_list_tags_no_auth` | Token yokken tags list hata dönmeli |
| `test_dashboard_overview_no_auth` | Token yokken dashboard hata dönmeli |
| `test_repl_help` | REPL help çalışmalı |
| `test_cli_invocation` | --help flag'i çalışmalı |
| `test_repl_exit` | REPL exit ile kapanmalı |
| `test_repl_quit` | REPL quit ile kapanmalı |
| `test_repl_invalid_command` | Geçersiz komut crash yapmamalı |
| `test_group_help` | Her grup (auth/tags/dashboard/reports) --help çalıştırabilmeli |

## E2E Tests

Backend çalışırken:

```bash
pytest tests/ -v --api-url http://localhost:8001
```

| Test | Description |
|------|-------------|
| `test_auth_login_logout` | Login → token al → /api/auth/me çağır |
| `test_tags_crud` | Tag oluştur → listele → sil |
| `test_dashboard_live` | Overview + current-values çağır |
| `test_report_generate` | Rapor oluştur → JSON çıktıyı doğrula |

## Test Results

```
(cixan)
```
