# Grafana panellerinde tag açıklamasını etiket olarak gösterme — Tasarım

**Tarih:** 2026-06-28
**Durum:** Onaylandı (brainstorming) — uygulama planı bekliyor

## Problem

Üretilen Grafana dashboard'larında seriler/tablolar tag'in teknik adıyla (`t.name`,
ör. `B110kkgHT04SE05.SCL_VAL`) etiketleniyor. Operatör için okunması zor.
Tag'in `description` alanı (ör. "pH Değeri") çok daha anlaşılır. Grafiklerde ve
tablolarda teknik ad yerine açıklama gösterilsin.

## Kararlar (brainstorming)

1. **Etiket biçimi:** `COALESCE(NULLIF(t.description, ''), t.name)` — açıklama
   varsa onu, boşsa tag adına düş. Hiçbir seri/satır etiketsiz kalmaz.
2. **Kapsam:** tam tutarlılık — trend grafik legend'ları + tüm tablolar
   (Son Değerler, Limit Aşımı, facility_overview son-değerler) + PostgreSQL
   report-template generator panelleri. Lab dashboard'ları **kapsam dışı**
   (`param_name` kullanırlar, tag değil — zaten açıklayıcı).
3. **Tablo kolon başlığı:** okunur — `... AS "Etiket"`.
4. **Mevcut dashboard'lar:** otomatik toplu güncelleme (yeni endpoint),
   **Yaklaşım A** (yerinde SQL dönüşümü).

## Mimari

### 1. Ortak etiket ifadesi (tek kaynak)

`app/services/grafana_templates.py` içinde modül sabiti:

```python
# Tag'in görünen etiketi: açıklama varsa onu, boşsa teknik ada düş.
_TAG_LABEL = "COALESCE(NULLIF(t.description, ''), t.name)"
```

İnsan-etiketi olarak `t.name` kullanılan **SELECT** yerlerinde bu kullanılır.
Yapısal kullanım (JOIN/WHERE/`PARTITION BY`/`row_number`/`ORDER BY t.id`)
`t.id`/`t.name` olarak kalır — yalnız görünen etiket değişir.

### 2. Generator değişiklikleri (yeni üretim)

`grafana_templates.py`:

- **`build_water_quality_dashboard`**
  - Trend (frser): `t.name AS metric` → `{_TAG_LABEL} AS metric`
  - Son Değerler tablosu: iç sorgu `t.name` → `{_TAG_LABEL} AS label`; dış
    `SELECT name` → `SELECT label AS "Etiket"` (alt-sorgu alias zinciri buna göre)
  - Limit Aşımı: `SELECT t.name` → `SELECT {_TAG_LABEL} AS "Etiket"`,
    `GROUP BY t.name` → `GROUP BY {_TAG_LABEL}`
- **`build_facility_overview_dashboard`**
  - Son Değerler tablosu: iç `t.name` → `{_TAG_LABEL} AS label`, dış
    `SELECT name, device, ...` → `SELECT label AS "Etiket", device, ...`
- **PostgreSQL report-template generator** (aynı dosyadaki PG panel kurucusu)
  - Trend: `t.name AS metric` → `{_TAG_LABEL} AS metric`
  - Son Değerler / Limit Aşımı tabloları: aynı `AS "Etiket"` dönüşümü
- **Lab** (`_lab_timeseries_panel`, `build_lab_dashboard`): değişmez.

Alt-sorgu yapısı (Son Değerler) örnek son hali:
```sql
SELECT label AS "Etiket", value, unit, quality, timestamp FROM (
  SELECT t.id AS tid, COALESCE(NULLIF(t.description,''), t.name) AS label,
         tr.value, t.unit, tr.quality, tr.timestamp,
         row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn
  FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id
  WHERE t.id IN (...)
) WHERE rn = 1 ORDER BY tid
```

### 3. Toplu güncelleme — Yaklaşım A (yerinde SQL dönüşümü)

**Transform fonksiyonu** `app/services/grafana_templates.py`:
```python
def apply_tag_label(sql: str) -> str:
    """Bir panel SQL'indeki teknik-ad etiketlerini _TAG_LABEL ile değiştirir.
    Idempotent; bilinen kalıp yoksa SQL'i olduğu gibi döndürür."""
```
- Transform, generator'ların **ürettiği tam SQL imzalarını** hedefler (kalıplar
  bizim ürettiğimiz sabit metinler olduğundan eşleşme güvenilir):
  1. **Trend (chart):** `t.name AS metric` → `{_TAG_LABEL} AS metric`. Tek satır,
     basit ve yüksek değer.
  2. **Limit Aşımı (düz tablo):** `SELECT t.name,` → `SELECT {_TAG_LABEL} AS "Etiket",`
     ve eşleşen `GROUP BY t.name` → `GROUP BY {_TAG_LABEL}`.
  3. **Son Değerler (alt-sorgulu tablo):** etiket alt-sorguya bölünmüş —
     dış `SELECT name,` ve iç `t.name,` (veya `t.id AS tid, t.name,`) **koordineli**
     değiştirilir: iç `t.name` → `{_TAG_LABEL} AS label`, dış `name` → `label AS "Etiket"`.
     İç+dış birlikte eşleşmezse bu blok NO-OP (yarı dönüşüm yapılmaz).
- **Idempotency:** SQL zaten `COALESCE(NULLIF(t.description` içeriyorsa hiç dokunma.
- **Güvenlik:** yalnız bu sabit imzaları değiştirir; eşleşme yoksa NO-OP. Lab
  (`param_name AS metric`) ve elle yazılmış/farklı SQL doğal olarak atlanır.
- **Not:** `$__time(...)`/`$__timeFilter(...)` makrolu (eski PG) trend varyantı da
  `t.name AS metric` içerdiği için (1) ile kapsanır; frser ve PG trend'leri aynı
  kalıbı paylaşır.

**Endpoint** `app/api/grafana_dashboards.py`:
```
POST /api/grafana/dashboards/refresh-managed
  guard: get_current_user + require_role("admin") + require_feature("grafana")
         + require_writable   (demo modunda 403)
  döner: { "updated": int, "skipped": [ {"uid": str, "reason": str} ] }
```
Akış:
1. Grafana search ile yönetilen dashboard'ları listele (uid prefix `sr-`).
2. Her uid için `GET /api/dashboards/uid/{uid}` → JSON.
3. `panels[].targets[].queryText` ve `rawQueryText` alanlarına `apply_tag_label`
   uygula. Hiçbir panel değişmediyse → skip (reason `"no-op"`).
4. Değiştiyse `POST /api/dashboards/db` `{dashboard, overwrite:true}` ile yaz.
5. Tek dashboard hatası → logla, `skipped`'e ekle, devam et.

**Grafana auth:** mevcut `grafana_render.py` deseni — `GRAFANA_SA_TOKEN`
(service-account) varsa Bearer, yoksa `GRAFANA_USER`/`GRAFANA_PASSWORD` basic-auth.
Ortak bir küçük Grafana HTTP istemci yardımcı fonksiyonuna çıkarılabilir.

**Frontend (opsiyonel, küçük):** Grafana sayfasına admin-görünür "Mevcut
panoları güncelle" butonu → endpoint'i çağırır, `{updated, skipped}` özetini
gösterir. (İlk turda backend + endpoint yeterli; buton ayrı küçük adım.)

## Hata yönetimi

- Grafana erişilemez (liste/fetch/post) → endpoint 502 + açıklayıcı mesaj.
- Tek dashboard dönüşüm/yazma hatası → log + `skipped`, toplu işlem durmaz.
- Idempotent: tekrar çağrı zararsız (zaten dönüşmüşler skip).

## Test

- **Unit `apply_tag_label`**: eski trend/tablo/breach SQL'leri → COALESCE+`AS "Etiket"`;
  idempotent (2. uygulama NO-OP); `param_name AS metric` korunur; alakasız SQL değişmez.
- **Generator çıktısı**: `build_water_quality_dashboard` + `build_facility_overview_dashboard`
  JSON'unda metric kolonu ve tablo kolonları `COALESCE(NULLIF(t.description` içerir;
  lab dashboard içermez.
- **Endpoint**: Grafana HTTP mock — search→fetch→(transform)→overwrite POST sırası;
  no-op dashboard skip; admin-gate (operator 403); demo `require_writable` 403;
  Grafana down → 502.

## Kapsam dışı / sonraki adımlar

- Lab dashboard etiketleri (zaten `param_name`).
- Etiket biçiminin kullanıcı-yapılandırılabilir olması (YAGNI — sabit COALESCE).
- Frontend butonu ayrı küçük adım olarak ele alınabilir.
