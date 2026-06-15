# Agent Kurulumu — SCADA Reporter

## 1. Backend'i Başlat

```bash
cd scada-reporter
just run-backend
# → http://localhost:8001
```

## 2. Agent CLI'yi Yükle

```bash
uv pip install -e scada-reporter/agent-harness
```

Doğrulama:

```bash
scada --help
scada health
```

## 3. Giriş Yap

```bash
scada auth login admin
```

## 4. Agent'ınızı Yapılandırın

### Claude Code

```bash
# Plugin'i yükle
/plugin marketplace add <proje-repo>

# Plugin komutları:
/scada-login
/scada-tags list
/scada-dashboard current-values
```

### OpenCode

`AGENTS.md` dosyası otomatik olarak yüklenir. Agent CLI komutlarını doğrudan kullanabilirsiniz.

### Diğer Agent'lar (Cursor, Copilot, Windsurf)

```bash
# Agent prompt'larınızda:
scada <komut> --json
```

JSON çıktı tüm agent'lar tarafından kolayca işlenebilir.
