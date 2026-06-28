# Ekont Smart Scada Reporter - Gelişmiş Teknik Dokümantasyon

Bu dokümantasyon, **Ekont Smart Scada Reporter** sisteminin mimari tasarımını, temel çalışma prensiplerini, veri toplama stratejilerini, yapay zeka (AI) ve Model Context Protocol (MCP) entegrasyonunu, veri depolama altyapısını ve API katmanını derinlemesine incelemek üzere hazırlanmıştır.

Proje, doğrudan Siemens S7-1500 PLC'lerinden veri toplayarak, analiz edebilen, raporlayabilen ve bu işlemleri yapay zeka ajanları ile otomatize edebilen yeni nesil, ajana özgü (agent-native) bir SCADA raporlama çözümüdür.

---

## 1. Sistem Mimarisi ve Teknoloji Yığını

Sistem genel hatlarıyla üç ana katmandan ve bu katmanları destekleyen altyapı hizmetlerinden oluşur:

### 1.1 Teknoloji Yığını
- **Backend:** Python 3.14+, FastAPI, Uvicorn (Asenkron API sunucusu)
- **Veri Toplama (Collector):** python-snap7 (Siemens TCP 102 iletişimi), asyncua (Dahili OPC UA Server)
- **Veritabanı:** PostgreSQL 16 + TimescaleDB (Üretim ortamı), SQLite (Geliştirme)
- **ORM:** SQLAlchemy 2.0 (async), Alembic (Veritabanı göçleri)
- **Frontend:** React 19, Vite, Tailwind CSS v4, TanStack Query, Recharts, i18next
- **Raporlama Çıktıları:** openpyxl (Excel), WeasyPrint (PDF), JSON, CSV
- **Altyapı ve Konteynerizasyon:** Docker, Docker Compose, Redis (Opsiyonel)

### 1.2 Ana Bileşenler
1. **Collector (Veri Toplayıcı) Process:** PLC ile iletişim kurar. Snap7 üzerinden belirlenen periyotlarda (varsayılan: 5s) `active` durumdaki etiketleri okur.
2. **REST API (Backend):** React arayüzü ve yapay zeka ajanları için tüm CRUD, raporlama, trend verisi ve yönetim endpointlerini sunar.
3. **Frontend (React SPA):** Tarayıcı tabanlı, responsive izleme ve raporlama arayüzü.
4. **Agent Harness & MCP Server:** Yapay zeka ajanlarının (Claude, OpenCode, vb.) sisteme bir terminal CLI'ı (`scada`) veya MCP üzerinden doğrudan müdahale etmesini sağlar.

---

## 2. Veri Toplama ve "Smart Recording" Stratejisi

### 2.1 Ekont Universal Collector
Sistem, aracı bir yazılıma ihtiyaç duymadan **TCP 102** portu üzerinden doğrudan Siemens S7-1500 serisi PLC'lere bağlanır. Her PLC için `S7_HOST`, `S7_RACK` ve `S7_SLOT` bilgileri ayrı yapılandırılır.

### 2.2 Smart Recording System (Akıllı Kayıt)
Zaman serisi veritabanlarının en büyük problemi, saniyeler bazında toplanan ancak değişmeyen verilerin (ör. stabil bir tank seviyesi) yarattığı veri şişkinliğidir (bloat).
- **Mantık:** Veriler yalnızca daha önce tanımlanmış **eşik (deadband/threshold)** değerlerini aştığında veritabanına yazılır.
- **Kazanım:** Disk alanı, I/O yükü ve sorgu süresi optimizasyonunda %95'e varan tasarruf sağlar.
- **Simülasyon Modu:** PLC bağlantısı kopsa dahi backend, sistemin çökmesini engellemek için kesintisiz simülasyon modunda çalışmaya devam eder.

### 2.3 Dahili OPC UA Yayını
Toplanan veriler sadece veritabanına yazılmakla kalmaz; aynı zamanda sistemde çalışan dahili `asyncua` tabanlı OPC UA Sunucusu (`opc.tcp://localhost:4840`) üzerinden yayınlanır. Bu sayede harici üst katman SCADA'lar veya ERP/MES sistemleri veriyi anlık olarak tüketebilir.

---

## 3. Yapay Zeka (AI) ve MCP Entegrasyonu

Projenin en yenilikçi yönü "Agent-Native" (Ajan-Odaklı) olmasıdır. SCADA sistemi yalnızca insanların değil, doğrudan YZ ajanlarının da okuyup yönetebileceği bir altyapıya sahiptir.

### 3.1 Model Context Protocol (MCP) Sunucusu
`mcp-servers/mcp-scada/` dizininde yer alan MCP sunucusu, Claude Code gibi ajanların sistem özelliklerine "Tools" (Araçlar) olarak erişmesine olanak tanır:
- **`scada://agent/bootstrap`**: Ajanlar için başlangıç yapılandırma durumu.
- **`query_current_values`**: Anlık etiket verilerini okuma aracı.
- **`query_trend` & `generate_report`**: Trend çekme ve Excel/PDF/JSON rapor üretim aracı.
- **`run_sql_query`**: Zaman serisi veritabanında salt okunur (read-only) veri sorgulama (örn. `SELECT name, value FROM tags`).

### 3.2 Backend AI Endpoint'leri (`/api/ai/*`)
- **NL Query (`/api/ai/query`)**: Ajanların doğal dilde ilettiği soruları (Örn: "Dün en yüksek debi neydi?") alıp arka planda sorgu planına çeviren endpoint.
- **Anomali Tespiti (`/api/ai/anomalies`)**: Z-score ve hareketli ortalama analizleri yapılarak verilerdeki aykırı hareketlerin tespiti.
- **Tahminleme (Predictive) (`/api/ai/predict`)**: Lineer regresyon veya prophet tabanlı yaklaşım ile trend'in gelecek projeksiyonu.
- **Otomatik Rapor Üretimi**: Sadece doğal dil prompt'u ile belirtilen etiketler için rapor, özet ve excel dokümanı oluşturulması.

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

## 4. Zaman Serisi Veritabanı Optimizasyonu

**PostgreSQL + TimescaleDB** kullanımı, IoT/SCADA projelerinde kritik bir tercihtir.
- **Hypertables (Hiper Tablolar):** `tag_readings` gibi tablolar zaman eksenine (chunk'lara) bölünür. Böylece 10 yıllık veride bile sadece ilgili zaman aralığı aranarak milisaniyelik yanıtlar alınır.
- **Continuous Aggregates:** Saatlik, günlük, haftalık rapor sorgularının her seferinde milyonlarca satırı işlemesini önlemek için veriler arka planda otomatik toplulaştırılır (materialized). Sorgu, ana tablo yerine toplulaştırılmış tablodan yanıt döner.
- **Veri Tutma (Retention):** Eski ve çok hassas saniyelik veriler belirli bir süre sonra (örneğin 3 ay) silinirken, günlük/saatlik özetler sonsuza kadar saklanabilir.

---

## 5. Güvenlik, Lisanslama ve Yetkilendirme Modeli

### 5.1 Güvenlik ve Yetkilendirme
- **Auth:** OAuth2 Password Flow (Form-data) & JWT tabanlı Token yönetimi.
- **Roller (RBAC):** Varsayılan `admin` ve `operator` rolleri. Yetkilendirme sadece rol seviyesinde değil, mikro izinler seviyesinde (Örn: "Bu kullanıcı sadece Trend modülüne girebilir ve sadece Pompa etiketlerini görebilir") uygulanabilir.
- **Veri Ayrımı:** Kullanıcıya özel izleme listeleri (Watchlist).

### 5.2 Lisanslama Yönetimi
Ticari sürümlerde lisanslama, Asimetrik Şifreleme (RS256/ES256) kullanılarak JWT ile yapılır.
- Sistem **`licensed`**, **`demo`** (Salt-okunur, özellikler kısıtlı) veya **`full`** (Dev ortamı) modlarında çalışabilir.
- Özellik kısıtlamaları (Feature Gates): Gelişmiş raporlama, Grafana entegrasyonu, gerçek zamanlı (SSE) akış gibi özellikler lisans üzerinden kontrol edilebilir.

---

## 6. Frontend ve Görselleştirme Detayları

- **Trend Grafiği (Recharts):** Farklı birimlerdeki verilerin tek ekranda görülebilmesi için Çoklu Y-Ekseni. Brush ile pan/zoom. Anotasyon ekleme (Bakım yapıldı, arıza giderildi vb.)
- **Rapor Şablonları ve Zamanlayıcı:** Kullanıcıların periyodik olarak arka planda çalışacak rapor şablonları ayarlayabilmesi. Backend'deki zamanlayıcı servisi bu raporları belirlenen saatlerde çalıştırıp arşivler (Advanced Reports).
- **Laboratuvar Veri Girişi:** Manuel analiz sonuçlarının SCADA verileriyle harmanlanması için tasarlanmış özel grid arayüzü ve Excel içe/dışa aktarımı.

---

## 7. Geliştirici ve Entegrasyon Pratikleri

- **WinCC Migrasyonu:** Mevcut WinCC SCADA'lardan etiketlerin otomatik format tanıma ile CSV/Excel üzerinden dakikalar içinde projeye aktarımı mümkündür (`just seed-catalog`).
- **Development Araçları:**
  - `just run-backend` (Sadece API)
  - `just run-frontend` (Vite Sunucusu)
  - `just check` (Lint, Typecheck ve Testlerin bütünü)
  - `just docker-up` (Lokal PostgreSQL/Timescale ortamının ayağa kaldırılması)

---

## Sonuç

Ekont Smart Scada Reporter, geleneksel endüstriyel otomasyon verilerini sadece kullanıcı arayüzü üzerinden raporlamakla kalmaz; doğrudan LLM'lerin ve otonom ajanların anlayabileceği, müdahale edebileceği, MCP ve AI tabanlı servislerle güçlendirilmiş **Agentic** bir organizma formuna dönüştürür.
