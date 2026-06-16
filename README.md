# SCADA Reporter

Su ve atıksu tesisleri için **Snap7 tabanlı SCADA veri toplama ve raporlama sistemi**.

Siemens S7-1500 PLC'den doğrudan veri toplar, zaman serisi veritabanına kaydeder, React tabanlı web arayüzü ve REST API üzerinden kullanıcılara sunar. Harici ücretli yazılım gerektirmez.

---

## Özellikler

### Veri Toplama
- Siemens S7-1500 PLC'ye **Snap7** ile doğrudan bağlantı (TCP 102, ücretsiz)
- Çok-PLC desteği: 3000+ tag kataloğu, her PLC için ayrı IP/rack/slot yapılandırması
- Aktif tag'lerin periyodik toplu okunması (varsayılan: 5 s)
- PLC erişilemediğinde **simülasyon modunda** çalışmaya devam
- **Dahili OPC UA server** (`opc.tcp://localhost:4840`) son değerleri yayınlar

### Web Arayüzü (Frontend — React)

| Sayfa | Açıklama |
|-------|----------|
| **Dashboard** | 3 sekme: Özet (sayaçlar), İzleme Listesi (kullanıcı başına), Tüm Tag'ler (arama/filtre/sayfalama) |
| **Trend Grafik** | Çok-tag, çok-Y-ekseni; zoom/pan (Brush + mouse wheel); sarı kesik çizgi imleç; hover veri tablosu; PNG ve Excel dışa aktarım; preset kaydet/yükle |
| **Raporlar** | Tag/zaman seçimi, saatlik/günlük agregasyon, Excel+JSON çıktısı; filtre presetleri |
| **Gelişmiş Raporlar** | Rapor şablonları + zamanlayıcı + arşiv (şablon bazlı, tekrarlayan, indir) |
| **Tags** | Tag listesi, birim ve açıklama düzenleme, aktif/pasif yönetimi |
| **PLC Yapılandırma** | PLC ekle/sil, IP/rack/slot/bağlantı durumu yönetimi |
| **Ayarlar** | Kullanıcı tercihleri (ör. trend grafik yüksekliği 300–2000 px) |

### Backend API (`/api/*`)

| Grup | Prefix | Açıklama |
|------|--------|----------|
| Auth | `/api/auth` | Giriş (OAuth2 form-data), token |
| Tags | `/api/tags` | Tag CRUD, okuma geçmişi |
| Dashboard | `/api/dashboard` | Özet, anlık değerler, trend sorgusu |
| Reports | `/api/reports` | Rapor üretimi ve geçmişi |
| Advanced Reports | `/api/advanced-reports` | Şablon CRUD, zamanlayıcı, arşiv, indirme |
| PLC | `/api/plc` | PLC yapılandırma CRUD |
| Query | `/api/query` | Read-only SQL sorgusu (SELECT / WITH / EXPLAIN) |
| Explore | `/api/explore` | Şema ve tag kataloğu keşfi |

### Güvenlik
- JWT tabanlı kimlik doğrulama (OAuth2 Password Flow — **form-data**, JSON değil)
- Rol tabanlı yetkilendirme: `operator` ve `admin`
- Varsayılan kullanıcılar: `admin / admin123`, `operator / operator123`

---

## Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| Backend | Python 3.14, FastAPI, Uvicorn |
| S7 PLC Bağlantısı | python-snap7 (ücretsiz, TCP 102 doğrudan) |
| Dahili OPC UA | asyncua |
| Veritabanı (dev) | SQLite + aiosqlite (Docker gerekmez) |
| Veritabanı (prod) | PostgreSQL 16 + TimescaleDB |
| ORM | SQLAlchemy 2.0 (async) + Alembic |
| Rapor üretimi | openpyxl, WeasyPrint (PDF — GTK3 gerektirir) |
| Doğrulama | Pydantic v2 |
| Frontend | React 19, Vite, Tailwind CSS v4, TanStack Query |
| Grafik | Recharts |
| Paket yöneticisi | uv (backend), pnpm (frontend) |
| Task runner | just |
| Konteyner | Docker Compose (prod) |

---

## Proje Yapısı

```
scada-reporter/
├── backend/                    # Python FastAPI backend (:8001)
│   ├── app/
│   │   ├── api/                # REST endpoint'leri
│   │   │   ├── auth.py         # Giriş / token
│   │   │   ├── dashboard.py    # Özet, anlık değerler, trend
│   │   │   ├── tags.py         # Tag CRUD
│   │   │   ├── reports.py      # Temel raporlama
│   │   │   ├── advanced_reports.py  # Şablon / zamanlayıcı / arşiv
│   │   │   ├── plc.py          # PLC yapılandırma CRUD
│   │   │   ├── query.py        # Read-only SQL
│   │   │   └── explore.py      # Şema / katalog keşfi
│   │   ├── collector/
│   │   │   ├── s7_collector.py # Snap7 S7-1500 bağlantısı
│   │   │   ├── opcua_server.py # Dahili OPC UA sunucu
│   │   │   └── poller.py       # Periyodik okuma döngüsü
│   │   ├── core/
│   │   │   ├── config.py       # Ortam değişkenleri
│   │   │   ├── database.py     # Async SQLAlchemy motoru
│   │   │   └── security.py     # JWT / şifreleme
│   │   ├── models/
│   │   │   ├── tag.py          # Tag + TagReading
│   │   │   ├── user.py         # Kullanıcı
│   │   │   ├── plc_config.py   # PLC yapılandırma
│   │   │   ├── watchlist.py    # Kullanıcı izleme listesi
│   │   │   ├── report_history.py    # Rapor geçmişi
│   │   │   ├── report_template.py   # Gelişmiş rapor şablonu
│   │   │   ├── scheduled_report.py  # Zamanlı rapor
│   │   │   └── report_archive.py    # Arşivlenmiş raporlar
│   │   ├── reports/            # Excel / PDF üreticiler
│   │   └── main.py             # FastAPI uygulama girişi
│   ├── tests/                  # pytest async testler (185+)
│   ├── alembic/                # DB migration dosyaları
│   ├── seed_users.py           # Varsayılan kullanıcı oluşturma
│   ├── pyproject.toml          # pytest / ruff / mypy config
│   └── requirements.txt
├── frontend/                   # React + Vite (:5173)
│   ├── src/
│   │   ├── pages/              # Dashboard, Trend, Reports, AdvancedReports,
│   │   │                       # Tags, PlcConfig, Settings, Login
│   │   ├── context/            # AuthContext, SettingsContext (localStorage)
│   │   ├── components/         # Layout (sidebar nav)
│   │   └── api/                # Üretilmiş OpenAPI TypeScript client
│   └── openapi-ts.config.ts    # TS client üretici config
├── agent-harness/              # Agent-native CLI (Click + JSON + REPL)
│   └── src/scada_reporter_cli/
├── commands/                   # Claude Code slash komutları
├── guides/                     # Agent metodoloji rehberleri
└── AGENTS.md                   # Agent kullanım rehberi
docker/                         # TimescaleDB + Redis + Grafana
```

---

## Kurulum ve Çalıştırma

### Gereksinimler
- Python 3.12+ (uv ile yönetilir)
- Node.js 18+, pnpm
- just (task runner)
- Siemens S7-1500 PLC (veya simülasyon modu)

### Hızlı Başlangıç

```bash
# Bağımlılıkları yükle
just install

# Varsayılan kullanıcıları oluştur (admin/admin123, operator/operator123)
just seed-users

# Backend + frontend paralel başlat
just dev
```

Uygulama:
- Backend: `http://localhost:8001` — API docs: `http://localhost:8001/docs`
- Frontend: `http://localhost:5173`

### Komutlar

```bash
# Geliştirme
just run-backend      # Sadece backend (hot reload)
just run-frontend     # Sadece frontend (Vite)

# Veritabanı
just migrate          # Migration uygula
just makemigration msg="açıklama"
just seed-tags        # Demo tag seti ekle
just seed-users       # Varsayılan kullanıcılar (admin + operator)
just seed-catalog     # WinCC xlsx'ten tag kataloğu yükle

# Test & Kalite
just test             # pytest
just test-cov         # Coverage raporu
just lint             # ruff
just typecheck        # mypy
just check            # Tüm kontroller (CI)

# Araçlar
just gen-client       # OpenAPI → TypeScript client (backend çalışırken)
just test-plc         # PLC bağlantı testi
just docker-up        # PostgreSQL + Redis başlat (prod)
```

### Ortam Değişkenleri (`.env`)

```env
# Dev (SQLite — Docker gerekmez)
DATABASE_URL=sqlite+aiosqlite:///./scada_reporter.db

# Prod (PostgreSQL)
# DATABASE_URL=postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter

SECRET_KEY=change-this-in-production-32-chars-minimum
ACCESS_TOKEN_EXPIRE_MINUTES=480

# S7 PLC (simülasyon modunda atlanır)
S7_HOST=192.168.1.1
S7_RACK=0
S7_SLOT=1
```

`.env.example` dosyasını kopyala ve düzenle:
```bash
copy scada-reporter/backend/.env.example scada-reporter/backend/.env
```

---

## Agent CLI (`scada`)

Coding agent'lar (Claude Code vb.) REST API'yi `scada` CLI ile kullanabilir.

```bash
just install-agent        # Kurulum

scada auth login admin    # Giriş
scada tags list --json    # Tag listesi
scada dashboard overview  # Özet
scada query run "SELECT name, value FROM tags LIMIT 5" --json
scada explore schema      # DB şeması
scada shell               # Python REPL (veriler yüklü)
```

Detaylı rehber: `scada-reporter/AGENTS.md`

---

## Notlar

- **OAuth2 giriş**: `/api/auth/token` endpoint'i **form-data** bekler (JSON değil) — `curl -d "username=admin&password=admin123"` kullanın
- **Simülasyon modu**: PLC yoksa veya erişilemezse backend sorunsuz çalışır
- **WeasyPrint PDF**: Windows'da GTK3 runtime gerektirir
- **pre-commit hooks**: Her commit'te ruff + mypy + format kontrolleri çalışır
