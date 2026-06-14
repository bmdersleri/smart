# SCADA Reporter

Su ve atıksu tesisleri için **OPC UA tabanlı SCADA veri toplama ve raporlama sistemi**.

Saha ekipmanlarından (PLC, RTU) KEPServerEX aracılığıyla OPC UA protokolü üzerinden gerçek zamanlı veri toplar; zaman serisi veritabanına kaydeder ve kullanıcılara dashboard ile Excel/JSON raporu sunar.

---

## Kapsam ve Özellikler

### Veri Toplama
- KEPServerEX'e OPC UA bağlantısı (varsayılan: `opc.tcp://localhost:49320`)
- Aktif tag'lerin periyodik olarak toplu okunması (varsayılan aralık: 5 saniye)
- OPC quality kodu ile birlikte her okumanın timestamp'li kaydı
- OPC UA sunucusu erişilemediğinde simülasyon modunda çalışmaya devam

### Tag Yönetimi
- OPC UA ağacını (kanal → cihaz → tag hiyerarşisi) otomatik tarama
- Tag'leri aktif/pasif yapma; birimi ve açıklamasını düzenleme

### Dashboard API
| Endpoint | Açıklama |
|---|---|
| `GET /api/dashboard/overview` | Toplam aktif tag sayısı, son okuma zamanı, son 24 saatteki okuma adedi |
| `GET /api/dashboard/current-values` | Her aktif tag için anlık değer ve quality durumu |
| `GET /api/dashboard/trend` | Seçili tag'ler için zaman serisi (saat bazında filtrelenebilir) |

### Raporlama
- Saatlik veya günlük aralıkta ortalama / min / max / okuma sayısı agregasyonu
- Excel (.xlsx) çıktısı: her tag için ayrı sekme + özet sayfası
- JSON çıktısı: makine tüketimi için

### Güvenlik
- JWT tabanlı kimlik doğrulama (OAuth2 Password Flow)
- Rol tabanlı yetkilendirme: `operator` ve `admin`
- Token süresi yapılandırılabilir (varsayılan: 8 saat)

---

## Teknoloji Yığını

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.12+, FastAPI, Uvicorn |
| OPC UA İstemcisi | asyncua |
| Veritabanı | PostgreSQL 16 + TimescaleDB (zaman serisi optimizasyonu) |
| ORM | SQLAlchemy 2.0 (async) |
| Görev kuyruğu | Celery + Redis |
| Rapor üretimi | openpyxl, WeasyPrint |
| Doğrulama | Pydantic v2 |
| Konteyner | Docker Compose |

---

## Proje Yapısı

```
scada-reporter/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py        # JWT kimlik doğrulama ve kayıt
│   │   │   ├── dashboard.py   # Anlık değer ve trend endpoint'leri
│   │   │   ├── reports.py     # Excel/JSON rapor üretimi
│   │   │   └── tags.py        # Tag CRUD
│   │   ├── collector/
│   │   │   ├── opc_client.py  # OPC UA bağlantı ve tag okuma
│   │   │   └── poller.py      # Periyodik veri toplama döngüsü
│   │   ├── core/
│   │   │   ├── config.py      # Ortam değişkeni yönetimi
│   │   │   ├── database.py    # Async SQLAlchemy motoru
│   │   │   └── security.py    # Şifreleme ve token işlemleri
│   │   ├── models/
│   │   │   ├── tag.py         # Tag ve TagReading tabloları
│   │   │   └── user.py        # Kullanıcı tablosu
│   │   └── main.py            # FastAPI uygulama girişi
│   ├── .env.example
│   └── requirements.txt
└── docker/
    └── docker-compose.yml     # TimescaleDB + Redis
```

---

## Kurulum

### Gereksinimler
- Python 3.12+
- Docker ve Docker Compose
- KEPServerEX (veya başka bir OPC UA sunucusu)

### 1. Altyapıyı Başlat (Docker)

```bash
cd scada-reporter/docker
docker compose up -d
```

Bu komut TimescaleDB (port 5432) ve Redis (port 6379) servislerini başlatır.

### 2. Backend Kurulumu

```bash
cd scada-reporter/backend

# Sanal ortam oluştur
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# Bağımlılıkları yükle
pip install -r requirements.txt

# Ortam değişkenlerini yapılandır
copy .env.example .env
# .env dosyasını düzenle
```

### 3. Ortam Değişkenleri (`.env`)

```env
DATABASE_URL=postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter
SECRET_KEY=change-this-in-production-32-chars-min
ACCESS_TOKEN_EXPIRE_MINUTES=480

OPC_UA_URL=opc.tcp://localhost:49320
OPC_UA_USERNAME=
OPC_UA_PASSWORD=

REDIS_URL=redis://localhost:6379/0
```

### 4. Sunucuyu Çalıştır

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Uygulama başlarken:
1. Veritabanı tablolarını otomatik oluşturur.
2. OPC UA sunucusuna bağlanmaya çalışır; başarısız olursa simülasyon modunda devam eder.
3. Aktif tag'leri okuma döngüsünü başlatır.

---

## API Kullanımı

Interaktif dokümantasyon: `http://localhost:8000/docs`

### Kimlik Doğrulama

```bash
# Kullanıcı oluştur
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"gizli","role":"admin"}'

# Token al
curl -X POST http://localhost:8000/api/auth/token \
  -d "username=admin&password=gizli"
```

### Rapor Üretme

```bash
curl -X POST http://localhost:8000/api/reports/generate \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "tag_ids": [1, 2, 3],
    "start": "2024-01-01T00:00:00",
    "end": "2024-01-07T23:59:59",
    "interval": "daily",
    "format": "excel"
  }' \
  --output rapor.xlsx
```

### Sistem Durumu

```bash
curl http://localhost:8000/health
# {"status":"ok","opc_connected":true}
```

---

## Veri Modeli

```
Tag
├── node_id     — OPC UA node kimliği (ns=2;s=Channel1.Device1.Tag1)
├── name        — Görünen ad
├── unit        — Ölçüm birimi (m³/h, bar, °C ...)
├── channel     — KEPServerEX kanal adı
├── device      — PLC/RTU adı
└── is_active   — Aktif mi?

TagReading
├── tag_id      — Tag referansı
├── value       — Okunan değer (Float)
├── quality     — OPC quality kodu (192 = Good)
└── timestamp   — Kaynak zaman damgası
```
