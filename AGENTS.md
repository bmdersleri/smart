# SCADA Reporter — Agent Kullanım Rehberi

Bu proje **agent-native** olarak CLI-Anything yaklaşımı ile yapılandırılmıştır.
Detaylı rehber: `scada-reporter/AGENTS.md`

## Hızlı Bağlantılar

| İhtiyaç | Adres |
|---------|-------|
| Agent CLI kaynağı | `scada-reporter/agent-harness/` |
| Claude Code plugin | `scada-reporter/.claude-plugin/` |
| Slash komutları | `scada-reporter/commands/` |
| Rehberler | `scada-reporter/guides/` |
| SKILL.md | `scada-reporter/agent-harness/skills/SKILL.md` |

## Kurulum (30 saniye)

```bash
cd scada-reporter
uv pip install -e agent-harness
scada auth login admin --password <sifre>
scada tags list
```
