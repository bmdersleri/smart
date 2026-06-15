---
name: scada-reporter-cli
description: SCADA Reporter için agent-native CLI — PLC tag yönetimi, canlı değerler, trend analizi ve rapor oluşturma
author: SCADA Reporter Team
commands:
  - scada auth login <username>
  - scada auth me
  - scada tags list
  - scada tags create --node-id <id> --name <name>
  - scada tags delete <id>
  - scada tags readings <id>
  - scada dashboard overview
  - scada dashboard current-values
  - scada dashboard trend <tag_ids>
  - scada reports generate --tag-ids <ids> --start <iso> --end <iso>
  - scada health
environment:
  SCADA_API_URL: "http://localhost:8001"
  SCADA_TOKEN: "<jwt>"
output_format: JSON (--json flag ile)
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
