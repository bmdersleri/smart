# SCADA Reporter

Su/Atıksu tesisi SCADA veri toplama ve raporlama sistemi.

## Proje Yapısı

```
scada-reporter/
├── backend/       # Python FastAPI backend
│   ├── app/
│   │   ├── api/        # REST API endpoints
│   │   ├── collector/  # OPC UA veri toplayıcı
│   │   ├── core/       # Config, DB, güvenlik
│   │   ├── models/     # SQLAlchemy modelleri
│   │   └── reports/    # Rapor üretimi
│   ├── .venv/          # Python venv (uv ile yönetilir)
│   └── requirements.txt
├── frontend/      # Henüz oluşturulmadı
└── docker/        # TimescaleDB + Redis
```

## Komutlar

- **Backend başlat:** `just run-backend`
- **Bağımlılıkları yükle:** `just install`
- **Docker altyapı:** `just docker-up` / `just docker-down`
- **Lint:** `just lint`
- **Format:** `just format`
- **Type check:** `just typecheck`
- **Tüm kontroller:** `just check`

## Veritabanı

- PostgreSQL (TimescaleDB) + Redis (Docker ile)
- Docker olmadan backend çalışır ancak DB bağlantısı olmaz

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
- Backend başlatmak için önce `.venv\Scripts\activate` yap
- `uv pip install ...` ile hızlı paket yükleme
