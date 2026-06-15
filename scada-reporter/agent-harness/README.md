# SCADA Reporter Agent CLI

Coding agent'lar (Claude Code, OpenCode, GitHub Copilot, Cursor, Windsurf vb.)
tarafından SCADA Reporter REST API'sini kullanmak için tasarlanmış CLI aracı.

## Kurulum

```bash
pip install -e scada-reporter/agent-harness
# veya
uv pip install -e scada-reporter/agent-harness
```

## Kullanım

```bash
# Giriş
scada auth login admin

# Tag'leri listele (agent'lar için --json)
scada tags list --json

# Canlı değerler
scada dashboard current-values

# SQL sorgu (read-only)
scada query run "SELECT name, value, unit FROM tags LIMIT 5" --json

# Veritabanı keşfi
scada explore schema
scada explore tags

# Python REPL (veriler yüklü)
scada shell

# Agent-native kullanım
scada tags readings 1 --limit 5 --json | jq '.[] | {t: .timestamp, v: .value}'
```

## Agent'lar İçin

Tüm komutlar `--json` flag'i ile makine-okunabilir JSON çıktısı üretir.
Token `~/.config/scada-reporter/config.json` dosyasında saklanır veya
`SCADA_TOKEN` ortam değişkeninden okunur.

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `SCADA_API_URL` | `http://localhost:8001` | Backend API adresi |
| `SCADA_TOKEN` | — | JWT token (opsiyonel) |
