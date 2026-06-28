# Ekont Smart Scada Reporter - Gelişmiş Teknik Dokümantasyon

Bu dokümantasyon, **Ekont Smart Scada Reporter** sisteminin mimari tasarımını, temel çalışma prensiplerini, veri toplama stratejilerini, yapay zeka (AI) ve Model Context Protocol (MCP) entegrasyonunu, veri depolama altyapısını ve API katmanını derinlemesine incelemek üzere hazırlanmıştır.

Proje, doğrudan Siemens S7-1500 PLC'lerinden veri toplayarak, analiz edebilen, raporlayabilen ve bu işlemleri yapay zeka ajanları ile otomatize edebilen yeni nesil, ajana özgü (agent-native) bir SCADA raporlama çözümüdür.

---

## 1. Sistem Mimarisi ve Teknoloji Yığını

Sistem genel hatlarıyla üç ana katmandan ve bu katmanları destekleyen altyapı hizmetlerinden oluşur:

### 1.1 Teknoloji Yığını
- **Backend:** Python 3.14+, FastAPI, Uvicorn (Asenkron API sunucusu)
- **Veri Toplama (Collector):** python-snap7 (Siemens TCP 102 iletişimi), asyncua (Dahili OPC UA Server)
- **Veritabanı:** PostgreSQL 16 + TimescaleDB (Üretim ortamı), SQLite (Geliştirme/Test)
- **ORM:** SQLAlchemy 2.0 (async), Alembic (Veritabanı göçleri)
- **Frontend:** React 19, Vite, Tailwind CSS v4, TanStack Query, Recharts, i18next
- **Raporlama Çıktıları:** openpyxl (Excel), WeasyPrint (PDF), JSON, CSV
- **Görselleştirme:** Grafana (frser-sqlite veri kaynağı / TimescaleDB), gömülü paneller
- **Altyapı ve Konteynerizasyon:** Docker, Docker Compose, Redis (Opsiyonel)

### 1.2 Ana Bileşenler
1. **Collector (Veri Toplayıcı) Process:** PLC ile iletişim kurar. Snap7 üzerinden belirlenen periyotlarda (varsayılan: 5s) `active` durumdaki etiketleri okur.
2. **REST API (Backend):** React arayüzü ve yapay zeka ajanları için tüm CRUD, raporlama, trend verisi ve yönetim endpointlerini sunar.
3. **Frontend (React SPA):** Tarayıcı tabanlı, responsive izleme ve raporlama arayüzü.
4. **Agent Harness & MCP Server:** Yapay zeka ajanlarının (Claude, OpenCode, vb.) sisteme bir terminal CLI'ı (`scada`) veya MCP üzerinden doğrudan müdahale etmesini sağlar.

---

## 2. Veri Toplama ve "Smart Recording" Stratejisi

### 2.1 Ekont Universal Collector
Sistem, aracı bir yazılıma ihtiyaç duymadan **TCP 102** portu üzerinden doğrudan Siemens S7-1500 serisi PLC'lere bağlanır. Her PLC için `S7_HOST`, `S7_RACK` ve `S7_SLOT` bilgileri ayrı yapılandırılır. Okumalar etiketlerin DB adresine göre batch'lenerek tek S7 isteğinde gruplanır (PLC round-trip sayısı en aza iner).

### 2.2 Smart Recording System (Akıllı Kayıt)
Zaman serisi veritabanlarının en büyük problemi, saniyeler bazında toplanan ancak değişmeyen verilerin (ör. stabil bir tank seviyesi) yarattığı veri şişkinliğidir (bloat).
- **Mantık:** `should_store` fonksiyonu her tick'te her etiketi değerlendirir. Veri yalnızca tanımlı **eşik (deadband)** değerini aştığında DB'ye yazılır; eşik altı değişimler atlanır. Boolean etiketler her durum değişiminde yazılır.
- **Heartbeat:** `S7_STORE_HEARTBEAT_SECONDS` ile, değer hiç değişmese bile periyodik bir "canlı" kaydı zorlanır — böylece uzun sabit dönemlerde de veri sürekliliği korunur.
- **Kazanım:** Disk alanı, I/O yükü ve sorgu süresi optimizasyonunda yüksek oranda tasarruf sağlar.
- **Anlık vs. Kalıcı ayrımı:** Her okuma anlık önbelleğe (`latest_cache`) ve WebSocket/SSE yayınına gider (UI her zaman taze değeri görür); yalnızca deadband/heartbeat süzgecinden geçenler kalıcı `tag_readings` tablosuna yazılır.
- **Backpressure:** DB yazımı geçici hata verirse tick'ler sırayla tamponlanır ve sıra korunarak yeniden denenir (veri kaybı önlenir).
- **Simülasyon Modu:** PLC bağlantısı kopsa dahi backend, sistemin çökmesini engellemek için kesintisiz simülasyon modunda çalışmaya devam eder.

### 2.3 Dahili OPC UA Yayını
Toplanan veriler sadece veritabanına yazılmakla kalmaz; aynı zamanda sistemde çalışan dahili `asyncua` tabanlı OPC UA Sunucusu (`opc.tcp://localhost:4840`) üzerinden yayınlanır. Bu sayede harici üst katman SCADA'lar veya ERP/MES sistemleri veriyi anlık olarak tüketebilir.

---

## 3. Yapay Zeka (AI) ve MCP Entegrasyonu

Projenin en yenilikçi yönü "Agent-Native" (Ajan-Odaklı) olmasıdır. SCADA sistemi yalnızca insanların değil, doğrudan YZ ajanlarının da okuyup yönetebileceği bir altyapıya sahiptir.

### 3.1 Model Context Protocol (MCP) Sunucusu
`mcp-servers/mcp-scada/` dizininde yer alan MCP sunucusu, Claude Code gibi ajanların sistem özelliklerine "Tools" (Araçlar) olarak erişmesine olanak tanır:
- **`scada://agent/bootstrap`**: Ajanlar için başlangıç yapılandırma durumu (resource).
- **`query_current_values`**: Anlık etiket verilerini okuma aracı.
- **`query_trend` & `generate_report`**: Trend çekme ve Excel/PDF/JSON rapor üretim aracı.
- **`run_sql_query`**: Zaman serisi veritabanında salt okunur (read-only) veri sorgulama (örn. `SELECT name, value FROM tags`).
- **Yazma kapısı (Write gating):** Yazma yetkisi gerektiren araçlar yalnızca `SCADA_MCP_ALLOW_WRITES=1` ortam değişkeni ayarlıyken etkinleşir; varsayılan olarak ajan salt-okunurdur.

### 3.2 Backend AI Endpoint'leri (`/api/ai/*`)
- **NL Query (`/api/ai/query`)**: Ajanların doğal dilde ilettiği soruları (Örn: "Dün en yüksek debi neydi?") alıp arka planda sorgu planına çeviren endpoint.
- **Anomali Tespiti (`/api/ai/anomalies`)**: Z-score ve hareketli ortalama analizleri yapılarak verilerdeki aykırı hareketlerin tespiti.
- **Tahminleme (Predictive) (`/api/ai/predict`)**: Lineer regresyon (numpy `polyfit` + manuel R²) tabanlı yaklaşım ile trend'in gelecek projeksiyonu.
- **Otomatik Rapor Üretimi (`/api/ai/reports/generate`)**: Doğal dil prompt'u ile belirtilen etiketler için rapor, özet ve Excel dokümanı oluşturulması.
- **Etiket Çözümleme (`/api/ai/resolve`)**: Serbest metinde geçen etiket adlarını sistemdeki gerçek tag kayıtlarına eşler.

### 3.3 CLI ve Komut Seti (Agent CLI - `scada`)
Ajanlar, proje dizininde bir shell açtıklarında CLI ile etkileşim kurabilirler:
```bash
scada auth login admin
scada dashboard overview --json-output
scada tags readings 1 --limit 5 --json-output
scada doctor --json-output
```
CLI komutları JSON formatında çıktı üretebildiği için (`--json-output`) yapay zeka tarafından parse edilmesi oldukça başarılıdır.

---

## 4. Zaman Serisi Veritabanı ve Performans Optimizasyonu

**PostgreSQL + TimescaleDB** kullanımı, IoT/SCADA projelerinde kritik bir tercihtir.
- **Hypertables (Hiper Tablolar):** `tag_readings` gibi tablolar zaman eksenine (chunk'lara) bölünür. Böylece 10 yıllık veride bile sadece ilgili zaman aralığı aranarak milisaniyelik yanıtlar alınır.
- **Continuous Aggregates:** Saatlik/günlük rapor sorgularının her seferinde milyonlarca satırı işlemesini önlemek için veriler arka planda otomatik toplulaştırılır (materialized: `tag_readings_1m` / `tag_readings_5m` / `tag_readings_1h`). Trend uç noktası geniş pencereleri (>6 saat) otomatik olarak ilgili rollup tablosuna yönlendirir, kısa pencereler ham tabloya düşer — çıktı şekli (`{t, v}`) her iki yolda da aynıdır.
- **Veri Tutma (Retention):** Eski ve çok hassas saniyelik veriler belirli bir süre sonra silinirken, günlük/saatlik özetler uzun süre saklanabilir.

### 4.1 Ölçülmüş Performans Kazanımları
Bu donanım üzerinde `bench_ingest.py` ve `bench_sqlite_pragmas.py` ile ölçülmüştür:
- **PostgreSQL COPY ingest:** asyncpg `COPY` yolu (`S7_PG_COPY_INGEST=true`, **varsayılan KAPALI**) bulk INSERT'e göre ~**3.18×** daha hızlı yazma. COPY hatasında veri kaybı olmadan INSERT'e güvenli geri dönüş yapar. Zaman damgaları her iki yolda da naive-UTC'ye normalize edilir (asyncpg tz-aware datetime'ı reddeder).
- **Standalone timestamp index düşürme (yalnız PostgreSQL):** Hypertable partisyonu + bileşik PK `(tag_id, timestamp)` zaten kapsadığından gereksiz indeks kaldırıldı → ~**%12.5** daha hızlı yazma. SQLite'ta indeks korunur (hypertable yok).
- **SQLite pragmaları:** WAL + `synchronous=NORMAL` + 64 MB cache + 256 MB mmap + `wal_autocheckpoint` → ~**%16** daha hızlı okuma, WAL büyümesi sınırlanır.

> Tüm yazma yolu diyalekt-korumalıdır (dialect-guarded): üretimde PostgreSQL/Timescale yolu, geliştirme/testte SQLite yolu çalışır; uygulama kodu değişmez.

---

## 5. Görselleştirme: Grafana Entegrasyonu

Grafana, in-app trend grafiklerinin yanında yerleşik bir görselleştirme ve rapor-paneli katmanı olarak entegredir.

- **Veri kaynağı (dev):** Grafana, backend SQLite'ı doğrudan **frser-sqlite-datasource** üzerinden sorgular (`GRAFANA_DATASOURCE_UID`, varsayılan `scadadb`). frser `$__` makrolarını desteklemediği için üretilen tüm SQL sabit pencereler (`datetime('now','-N units')`), epoch zaman dönüşümü ve `row_number() OVER (...)` kullanır.
- **Otomatik dashboard üretimi:** `app/services/grafana_templates.py` lab, `facility_overview` ve `water_quality` dashboard'larını üretir. Rapor-şablonu dashboard'u (`build_report_template_dashboard`) PostgreSQL veri kaynağında kalır.
- **Lab → Grafana:** `POST /api/grafana/dashboards/from-lab` bir lab örnekleme noktasından, her parametre için min/max limit çizgili zaman-serisi panelleri + son-değer tablosu üreten bir dashboard oluşturur (`v_lab_timeseries` view'ı üzerinden).
- **Etiket etiketleme:** Üretilen paneller serileri/satırları teknik ad yerine etiket **açıklamasıyla** (`COALESCE(NULLIF(t.description,''), t.name)`) adlandırır. Metrik serilerinde frser'ın `"value <metric>"` ön-eki `displayName` ile kaldırılır.
- **Toplu yeniden etiketleme:** `POST /api/grafana/dashboards/refresh-managed` (admin) tüm yönetilen `sr-*` dashboard'larını yerinde günceller; idempotenttir (zaten etiketli olanları atlar).
- **Raporlara panel gömme:** Rapor şablonları Grafana panellerini ekleyebilir; rapor üretimi bunları `app/services/grafana_render.py` (Grafana `/render`, renderer servisi `:8081`) ile PDF/Excel'e gömer.
- **Yazma kimlik doğrulaması:** Backend'in toplu yazıcıları `GRAFANA_SA_TOKEN` (servis hesabı, Bearer) ayarlıysa onu, değilse `GRAFANA_USER`/`GRAFANA_PASSWORD` basic-auth'u kullanır. Basic-auth patlamaları Grafana'nın brute-force throttle'ına (aralıklı HTTP 403) takıldığından, güvenilir toplu yazma için **SA token önerilir**.

---

## 6. Güvenlik, Lisanslama ve Yetkilendirme Modeli

### 6.1 Güvenlik ve Yetkilendirme
- **Auth:** OAuth2 Password Flow (Form-data) & JWT tabanlı Token yönetimi.
- **Roller (RBAC):** Varsayılan `admin` ve `operator` rolleri. Yetkilendirme sadece rol seviyesinde değil, mikro izinler seviyesinde (Örn: "Bu kullanıcı sadece Trend modülüne girebilir ve sadece Pompa etiketlerini görebilir") uygulanabilir.
- **Veri Ayrımı:** Kullanıcıya özel izleme listeleri (Watchlist).

### 6.2 Lisanslama Yönetimi
Ticari sürümlerde lisanslama, Asimetrik Şifreleme (RS256/ES256) kullanılarak JWT ile yapılır.
- Sistem **`licensed`**, **`demo`** (Salt-okunur, özellikler kısıtlı, etiket kotalı) veya **`full`** (Dev ortamı — `SCADA_LICENSE_PUBLIC_KEY` yoksa) modlarında çalışabilir.
- Enforcement `app/api/license_guard.py`'de: özellik kapıları + `max_tags` kotası + demo salt-okunurluk. Adminler `POST /api/license` ile lisansı sıcak yükler. `SCADA_LICENSE_REQUIRED=true` katı fail-closed moddur.
- Özellik kısıtlamaları (Feature Gates): Gelişmiş raporlama, Grafana entegrasyonu, gerçek zamanlı (SSE) akış gibi özellikler lisans üzerinden kontrol edilebilir.

### 6.3 Denetim ve İzlenebilirlik (Audit)
- Tüm oluştur/güncelle/sil ve onay gibi durum-değiştiren işlemler denetim satırı yazar (`app/api/audit.py`, kim/ne/ne zaman).
- Denetim kayıtları UI ve CLI üzerinden sorgulanabilir; yasal/uyumluluk izlenebilirliğinin temelidir.

---

## 7. Yedekleme ve Veri Bütünlüğü

Uygulama yönetimli DB anlık görüntüleri (`app/services/backup_engine.py`):
- **Tutarlı snapshot:** SQLite `VACUUM INTO` (WAL-güvenli) / PostgreSQL `pg_dump -Fc`. Her yedek sha256 + `PRAGMA integrity_check` ile doğrulanır.
- **API:** `/api/backup` (oluştur/listele/indir/sil) + `/{id}/restore`. **Admin + `require_writable`** kapılı (demo modunda bloke). Geri yükleme `{"confirm":"RESTORE"}` ister, önce bir güvenlik anlık görüntüsü alır, sonra `engine.dispose()` çağırır.
- **Zamanlama:** Gecelik APScheduler işi `db_backup` + retention (`BACKUP_DIR` / `BACKUP_RETENTION_DAYS` / `BACKUP_SCHEDULE_CRON` / `RUN_BACKUP_SCHEDULER`).
- **UI:** `SettingsBackupCard` (admin); indirme, Bearer token gerektiren kimlik-doğrulamalı blob fetch'tir.
- Fiziksel PITR (pgBackRest/WAL-G) üretim için önerilen yol olarak ayrıca izlenir.

---

## 8. Frontend ve Görselleştirme Detayları

- **Trend Grafiği (Recharts):** Farklı birimlerdeki verilerin tek ekranda görülebilmesi için Çoklu Y-Ekseni. Brush ile pan/zoom. Anotasyon ekleme (Bakım yapıldı, arıza giderildi vb.). Seri adları etiket açıklamasından gelir.
- **Rapor Şablonları ve Zamanlayıcı:** Kullanıcıların periyodik olarak arka planda çalışacak rapor şablonları ayarlayabilmesi. Backend'deki zamanlayıcı servisi bu raporları belirlenen saatlerde çalıştırıp arşivler (Advanced Reports).
- **Laboratuvar Veri Girişi:** Manuel analiz sonuçlarının SCADA verileriyle harmanlanması için tasarlanmış özel grid arayüzü ve Excel içe/dışa aktarımı.
- **Canlı Metrikler (Veritabanı):** `GET /api/dashboard/database`, diyalekt-duyarlı DB boyutu (SQLite dosyası + WAL/SHM veya `pg_database_size`), toplam okuma sayısı, 24s/7g/30g sayımları, tablo-başı satır sayıları, günlük yazma hızı ve aylık büyüme tahmini döner. Sayfa **manuel "Yenile"** ile çalışır (büyük `count(*)` taramaları yalnızca yüklemede + tıklamada).
- **i18n:** en/tr/ru/de + Arapça (RTL); açık/koyu tema.

---

## 9. Geliştirici ve Entegrasyon Pratikleri

- **WinCC Migrasyonu:** Mevcut WinCC SCADA'lardan etiketlerin otomatik format tanıma ile CSV/Excel üzerinden dakikalar içinde projeye aktarımı mümkündür (`just seed-catalog`).
- **Test İzolasyonu:** Testler tek bir in-memory SQLite motorunu (StaticPool) paylaşır; autouse fixture her testten önce tüm tabloları (FK-güvenli sırada) temizler — testler sıra-bağımsızdır.
- **Development Araçları:**
  - `just dev` (Backend + Frontend paralel)
  - `just run-backend` (Sadece API, `app/` izleyen hot-reload)
  - `just run-frontend` (Vite Sunucusu)
  - `just check` (Lint, Typecheck ve Testlerin bütünü — CI)
  - `just docker-up` (Lokal PostgreSQL/Timescale ortamının ayağa kaldırılması)
  - `just gen-client` (Frontend TypeScript API istemcisini yeniden üret)

---

## 10. Yol Haritası: Compliance Center

Bir sonraki ürün adımı, sistemi jenerik SCADA raporlamasının ötesine taşıyan **permit-odaklı uyumluluk (compliance) katmanıdır** (tasarım: `docs/superpowers/specs/2026-06-28-compliance-center-design.md`, plan: `docs/superpowers/plans/2026-06-28-compliance-foundation.md`).

- **Permit Profili:** Tesis/deşarj izni meta verisi, izlenen parametreler, SCADA tag / lab parametresi kaynak eşlemesi, limit ve örnekleme-sıklığı kuralları.
- **Compliance Engine (uygulandı — Phase 1):** Deterministik motor (`app/services/compliance_engine.py`); anlık min/max, örnek sayısı, bozuk-kalite (PLC quality < 192) ve lab/hibrit eksik-örnek kontrollerini bir zaman penceresi üzerinde değerlendirir. Deterministik `event_key` ile tekrar-değerlendirmede upsert (DB-seviyesi unique constraint). Takvim sınırları tesis-yerel saat diliminde hesaplanır.
- **Compliance Events:** Kalıcı bulgular (`limit_exceeded`, `missing_sample`, `late_sample`, `bad_quality`, `needs_explanation`); açık/onaylandı/çözüldü/feragat durumları kim/ne zaman damgalıdır (feragat gerekçesi zorunlu, denetlenir). İlk not eklenince ilgili `needs_explanation` otomatik çözülür.
- **API (uygulandı — Phase 1):** `/api/compliance/*` — overview, permit CRUD, events listeleme (filtre + sayfalama), notlar, durum geçişi, manuel `evaluate`. RBAC: admin permit yönetir, operator değerlendirme çalıştırır/not ekler.
- **Ajan yüzeyi:** `scada compliance overview|events|evaluate` CLI komutları + MCP yetenekleri (okuma varsayılan, `evaluate` mevcut `SCADA_MCP_ALLOW_WRITES` kapısıyla yazma).
- **Sonraki fazlar (planlı):** Official Report Pack (PDF/Excel/JSON + onay akışı + evidence dondurma), Compliance Center frontend route, AI Compliance Assistant, zamanlanmış dönem-kapanış üretimi.

İlk sürümde doğrudan resmi portal gönderimi, gerçek elektronik imza ve mobil uygulama kapsam dışıdır.

---

## Sonuç

Ekont Smart Scada Reporter, geleneksel endüstriyel otomasyon verilerini sadece kullanıcı arayüzü üzerinden raporlamakla kalmaz; doğrudan LLM'lerin ve otonom ajanların anlayabileceği, müdahale edebileceği, MCP ve AI tabanlı servislerle güçlendirilmiş **Agentic** bir organizma formuna dönüştürür. Akıllı kayıt, ölçülmüş ingest/okuma optimizasyonları, Grafana görselleştirmesi, uygulama-yönetimli yedekleme ve gelişmekte olan uyumluluk katmanı ile üretim-hazır bir su/atıksu veri platformudur.
