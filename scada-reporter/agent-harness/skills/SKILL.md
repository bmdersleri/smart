---
name: scada-reporter-cli
description: SCADA Reporter için agent-native CLI — PLC tag yönetimi, canlı değerler, trend analizi ve rapor oluşturma
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

Su/Atıksu tesisi SCADA veri toplama ve raporlama sistemine coding agent erişimi.

## Kurulum

```bash
uv pip install -e scada-reporter/agent-harness
```

## Agent Kullanımı

Tüm komutlar `--json` flag'i ile makine-okunabilir çıktı üretir.
Token `~/.config/scada-reporter/config.json` dosyasında saklanır.

### Keşif

```bash
scada tags list --json                    # Tüm tag'leri listele
scada dashboard current-values --json     # Canlı değerler
scada dashboard overview --json           # Sistem durumu
```

### Analiz

```bash
scada dashboard trend 1 2 --hours 48 --json  # 48 saatlik trend
scada tags readings 1 --limit 100 --json     # Son 100 okuma
```

### Rapor

```bash
scada reports generate --tag-ids 1,2 --start 2024-01-01T00:00:00 --end 2024-01-02T00:00:00 --format json
```
