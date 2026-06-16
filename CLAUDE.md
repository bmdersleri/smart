# SCADA Reporter

Su/Atıksu tesisi SCADA veri toplama ve raporlama sistemi.

## Proje Yapısı

```
scada-reporter/
├── backend/       # Python FastAPI backend (:8001)
│   ├── app/
│   │   ├── api/        # REST API (auth/dashboard/tags/reports/advanced_reports/plc/query/explore)
│   │   ├── collector/  # Snap7 S7 toplayıcı + dahili OPC UA server + poller
│   │   ├── core/       # Config, DB, güvenlik (JWT)
│   │   ├── models/     # Tag, User, PlcConfig, Watchlist, ReportHistory/Template/Scheduled/Archive
│   │   └── reports/    # Excel / PDF üreticiler
│   ├── tests/          # pytest async testler (185+)
│   ├── alembic/        # DB migration dosyaları
│   ├── seed_users.py   # admin + operator kullanıcı oluşturma
│   ├── pyproject.toml  # pytest/ruff/mypy config
│   ├── .venv/          # Python venv (uv ile yönetilir, Python 3.14)
│   └── requirements.txt
├── frontend/      # React 19 + Vite + Tailwind CSS v4 + TanStack Query (:5173)
│   ├── src/
│   │   ├── pages/      # Dashboard, Trend, Reports, AdvancedReports, Tags, PlcConfig, Settings
│   │   ├── context/    # AuthContext, SettingsContext (localStorage)
│   │   └── api/        # Üretilmiş OpenAPI TypeScript client
│   ├── openapi-ts.config.ts  # TypeScript API client üretici
│   └── package.json
├── agent-harness/ # Agent-native CLI (Click + JSON + REPL)
│   ├── src/scada_reporter_cli/
│   └── setup.py
├── commands/      # Claude Code slash komutları (markdown)
├── guides/        # Agent metodoloji rehberleri
├── .claude-plugin/  # Claude Code marketplace kaydı
└── AGENTS.md      # Agent kullanım rehberi
docker/        # TimescaleDB + Redis + Grafana
```

## Komutlar

### Geliştirme
- **Backend + Frontend paralel:** `just dev`
- **Sadece backend:** `just run-backend`
- **Sadece frontend:** `just run-frontend`
- **Bağımlılıkları yükle:** `just install`

### Test
- **Testleri çalıştır:** `just test`
- **Coverage raporu:** `just test-cov`
- **TDD hot reload:** `just test-watch`

### Veritabanı
- **Migration uygula:** `just migrate`
- **Migration oluştur:** `just makemigration msg="açıklama"`
- **Migration geri al:** `just migrate-down`
- **Migration geçmişi:** `just migrate-history`
- **PLC tag'lerini ekle:** `just seed-tags`
- **Varsayılan kullanıcılar:** `just seed-users` *(admin/admin123, operator/operator123)*
- **WinCC xlsx kataloğu:** `just seed-catalog`

### Kalite
- **Lint:** `just lint`
- **Lint + otomatik düzelt:** `just lint-fix`
- **Format:** `just format`
- **Type check:** `just typecheck`
- **Tüm kontroller (CI):** `just check`

### Agent CLI
- **CLI'yi yükle:** `just install-agent`
- **Test et:** `just test-agent`
- **REPL (interaktif):** `just agent-repl`
- **SQL sorgu:** `just agent cli_args="query run 'SELECT * FROM tags LIMIT 5' --json"`
- **Veritabanı keşfi:** `just agent cli_args="explore schema"`
- **Python REPL:** `just agent cli_args="shell"`
- **Tek komut:** `just agent cli_args="tags list --json"`

### Araçlar
- **TS API client üret:** `just gen-client` *(backend çalışırken)*
- **PLC bağlantı testi:** `just test-plc`
- **Docker başlat/durdur:** `just docker-up` / `just docker-down`
- **Proje ağacı:** `just tree`

## Veritabanı

- Dev/test: SQLite (`scada_reporter.db`) — Docker gerekmez
- Prod: PostgreSQL (TimescaleDB) + Redis (Docker ile)
- `.env.example` → `.env` kopyalayıp env var'ları ayarla

## Mevcut Araçlar

| Araç | Versiyon | Kullanım |
|------|----------|----------|
| Python | 3.14.6 | `python` veya `.venv\Scripts\activate` |
| uv | 0.11.21 | Hızlı pip alternatifi |
| ruff | 0.15.17 | Python linter + formatter |
| mypy | 2.1.0 | Python type checker |
| Node.js | 24.16.0 | JS runtime |
| pnpm | 11.6.0 | Hızlı npm alternatifi |
| TypeScript | 6.0.3 | `tsc` |
| Prettier | 3.8.4 | Code formatter |
| Git | 2.54.0 | Versiyon kontrol |
| Go | 1.26.4 | Go dili |
| Rust | 1.96.0 | `rustc` + `cargo` |
| .NET SDK | 10.0.301 | Dotnet |
| ripgrep | 15.1.0 | Hızlı kod arama (`rg`) |
| fd | 10.4.2 | Hızlı dosya bulma |
| bat | 0.26.1 | Syntax highlight ile görüntüle |
| fzf | 0.73.1 | Fuzzy finder |
| jq | 1.8.1 | JSON işlemleri |
| yq | 4.53.3 | YAML/JSON/XML işlemleri |
| gh | 2.94.0 | GitHub CLI |
| lazygit | 0.62.2 | Terminal Git UI |
| delta | 0.19.2 | Git diff viewer |
| tldr | 0.6.1 | Kısa man sayfaları |
| eza | 0.23.4 | Modern ls |
| zoxide | 0.9.9 | Akıllı cd (`z <dizin>`) |
| btop | 1.0.5 | Sistem monitörü |
| dust | 1.2.4 | Disk analizi |
| hyperfine | 1.20.0 | Benchmark |
| just | 1.52.0 | Komut çalıştırıcı |

## Notlar

- **Dahili OPC UA Server**: `opc.tcp://localhost:4840` — backend başlarken otomatik ayağa kalkar. Harici ücretli yazılım (KEPServerEX vb.) gerekmez.
- **S7 PLC bağlantısı**: Snap7 (ücretsiz, pure Python) ile S7-1500'e doğrudan TCP 102. `S7_HOST`/`S7_RACK`/`S7_SLOT` env var'ları ile yapılandırılır.
- **Simülasyon modu**: PLC yoksa veya erişilemezse backend sorunsuz çalışır.
- **OAuth2 giriş**: `/api/auth/token` **form-data** bekler, JSON değil. Frontend doğru gönderir; `curl -d "username=...&password=..."` kullanın.
- **WeasyPrint PDF**: Windows'da GTK3 runtime gerektirir (kurulu — çalışıyor).
- **Stats engine**: numpy-only (scipy venv'de yok) — `np.polyfit` + manuel R².
- Backend başlatmak için `just run-backend`
- `uv pip install ...` ile hızlı paket yükleme
- pre-commit hooks aktif — her commit'te ruff + mypy + format kontrolleri çalışır
- Frontend TS client güncelle: backend çalışırken `just gen-client`
