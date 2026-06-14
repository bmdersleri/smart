# SCADA Reporter

Su/Atıksu tesisi SCADA veri toplama ve raporlama sistemi.

## Proje Yapısı

```
scada-reporter/
├── backend/       # Python FastAPI backend (:8001)
│   ├── app/
│   │   ├── api/        # REST API endpoints (auth/dashboard/tags/reports)
│   │   ├── collector/  # S7 snap7 PLC toplayıcı + dahili OPC UA server
│   │   ├── core/       # Config, DB, güvenlik (JWT)
│   │   ├── models/     # SQLAlchemy modelleri
│   │   └── reports/    # Rapor üretimi
│   ├── tests/          # pytest async test paketi
│   ├── alembic/        # DB migration dosyaları
│   ├── pyproject.toml  # pytest/ruff/mypy config
│   ├── .venv/          # Python venv (uv ile yönetilir, Python 3.14)
│   └── requirements.txt
├── frontend/      # React + Vite + Tailwind + TanStack Query (:5173)
│   ├── src/
│   ├── openapi-ts.config.ts  # TypeScript API client üretici
│   └── package.json
└── docker/        # TimescaleDB + Redis + Grafana
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

### Kalite
- **Lint:** `just lint`
- **Lint + otomatik düzelt:** `just lint-fix`
- **Format:** `just format`
- **Type check:** `just typecheck`
- **Tüm kontroller (CI):** `just check`

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

- WeasyPrint PDF üretimi için GTK runtime gerekir (Windows'da)
- Backend başlatmak için `.venv\Scripts\activate` veya `just run-backend`
- `uv pip install ...` ile hızlı paket yükleme
- pre-commit hooks aktif — her commit'te ruff + mypy + format kontrolleri çalışır
- Frontend TS client güncelle: backend çalışırken `just gen-client`
