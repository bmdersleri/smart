# SCADA Reporter — Agent Rehberi

Bu proje, CLI-Anything yaklaşımı ile **agent-native** olarak tasarlanmıştır.
Coding agent'lar (Claude Code, OpenCode, GitHub Copilot, Cursor, Windsurf)
SCADA Reporter sistemini aşağıdaki araçlarla sorunsuz kullanabilir.

## Agent CLI

```
scada-reporter/agent-harness/
├── src/scada_reporter_cli/   # Click CLI (JSON + REPL)
├── setup.py
└── skills/SKILL.md           # Agent skill tanımı
```

Kurulum: `uv pip install -e scada-reporter/agent-harness`

## Claude Code Plugin

```
scada-reporter/.claude-plugin/marketplace.json   # Marketplace kaydı
scada-reporter/cli-anything-plugin/               # Plugin tanımı
scada-reporter/commands/                          # Slash komutları
scada-reporter/guides/                            # Metodoloji rehberleri
```

## Agent-Native Prensipleri

1. **JSON çıktı**: Tüm CLI komutları `--json` flag'i ile makine-okunabilir çıktı üretir
2. **REPL modu**: `scada` komutu varsayılan olarak interaktif REPL açar
3. **Durumlu oturum**: JWT token `~/.config/scada-reporter/config.json` dosyasında saklanır
4. **Keşfedilebilirlik**: `scada tags list`, `scada dashboard overview` ile sistem kendi kendini tanıtır
5. **SKILL.md**: Agent'lar CLI yeteneklerini skill dosyasından keşfedebilir

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `SCADA_API_URL` | `http://localhost:8001` | Backend adresi |
| `SCADA_TOKEN` | — | JWT token (opsiyonel) |

## Hızlı Başlangıç

```bash
# 1. CLI'yi yükle
uv pip install -e scada-reporter/agent-harness

# 2. Giriş yap
scada auth login admin

# 3. Sistemi keşfet
scada tags list --json
scada dashboard current-values
scada health
```
