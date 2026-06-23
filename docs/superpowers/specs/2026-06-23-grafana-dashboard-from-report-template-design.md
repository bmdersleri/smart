# Rapor Şablonundan Grafana Dashboard Türetme — Tasarım

**Tarih:** 2026-06-23
**Durum:** Onaylandı (uygulama bekliyor)
**Kapsam:** Smart Report ↔ Grafana entegrasyonu, Faz 2 (auto-dashboard generation)

## Amaç

Mevcut bir `ReportTemplate`'ten (tag_ids + ayar bayrakları) tek tıkla Grafana
dashboard türet. Rapor sistemi ile Grafana panelleri tek kaynaktan beslensin:
rapor şablonu neyi izliyorsa, türetilen dashboard da onu gösterir.

## Mevcut durum (tekrar etmeyeceğimiz)

Background automation (commit c3905fe) zaten **manuel-tetikli, şablon-bazlı**
dashboard üretimi ekledi:
- `grafana_templates.py`: 2 sabit şablon (facility_overview, water_quality) +
  panel helper'ları (`_timeseries_panel`/`_stat_panel`/`_table_panel`/`_base_dashboard`).
- `grafana_dashboards.py`: `GET /grafana/templates`, `POST /grafana/dashboards/generate`.
- Frontend Grafana.tsx: template seçici + "Dashboard oluştur" UI.
- `grafana_sync.py`: watchlist-grup → otomatik dashboard sync.

Bu özellik bunun ÜSTÜNE **ReportTemplate kaynaklı** türetme ekler — sabit
şablonlar yerine kullanıcının mevcut rapor şablonundan.

## Kararlar (özet)

| Konu | Karar |
|------|-------|
| Kaynak | Mevcut `ReportTemplate` (tag_ids + bayraklar) |
| Tetikleme | Manuel buton (AdvancedReports şablon satırı) |
| İçerik | Şablon bayraklarına göre panel seçimi |
| uid | `sr-rpt-{template_id}` (deterministik, overwrite) |
| Auth | `render_auth()` + `render_headers()` (SA-token→basic-auth) |
| Yaklaşım | Mevcut grafana_templates panel helper'larını yeniden kullan (DRY) |

## Mimari

```
ReportTemplate (DB)
   │  POST /grafana/dashboards/from-report-template/{id}
   ▼
build_report_template_dashboard()  ──reuse──> _timeseries/_stat/_table/_base
   │  (grafana_templates.py)
   ▼
Grafana POST /api/dashboards/db {overwrite:True}  →  {uid, url}
   ▲
AdvancedReports.tsx "Grafana Dashboard" butonu → generateDashboardFromTemplate()
```

## Bölüm 1 — Backend dashboard üreteci

`grafana_templates.py`'ye yeni fonksiyon:

```python
def build_report_template_dashboard(
    *, template_id: int, title: str, tag_ids: list[int],
    time_range_type: str, custom_start, custom_end,
    show_trend_charts: bool, show_summary_stats: bool,
    anomaly_enabled: bool, show_anomaly_table: bool,
) -> dict: ...
```

- **uid:** `sr-rpt-{template_id}` (deterministik → `overwrite=True` ile tekrar
  üretimde güncellenir; stale yönetimi gerekmez).
- **Zaman aralığı** (`time.from`/`time.to`): last_1h→`now-1h`, last_24h→`now-24h`,
  last_7d→`now-7d`, last_30d→`now-30d`, custom→`custom_start`/`custom_end` ISO
  (to=`now` veya custom_end).
- **Panel seçimi (bayraklara göre):**
  - `show_summary_stats` → tag başına son-değer **stat** paneli(leri) / özet.
  - `show_trend_charts` → `tag_ids` çoklu-seri **timeseries** trend (mevcut
    water_quality SQL deseni: `tag_readings JOIN tags WHERE tag_id IN (...)`).
  - `anomaly_enabled AND show_anomaly_table` → **limit aşımı tablosu**
    (min_alarm/max_alarm, mevcut su-kalitesi panelindeki SQL).
- `tag_ids` boşsa → çağıran 422 döndürür (Bölüm 2).
- **Boş bayrak kümesi:** hiçbiri seçili değilse en az **trend paneli** üret
  (boş dashboard üretme — mantıklı varsayılan).
- Datasource: `{"type": "postgres", "uid": "timescaledb"}` (mevcut şablonlarla aynı).
- `tag_ids` SQL'e int-coerce edilerek girer (injection yok; mevcut `_tag_filter` deseni).

## Bölüm 2 — Backend endpoint

`grafana_dashboards.py`'ye yeni route:

```python
@router.post("/dashboards/from-report-template/{template_id}")
async def generate_from_report_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _feature=Depends(require_feature("grafana")),
) -> dict: ...
```

- `ReportTemplate` çek → yoksa **404**.
- `tag_ids = json.loads(tmpl.tag_ids)`; boşsa **422** ("dashboard için tag'li şablon gerekir").
- Aktif tag doğrulama (mevcut `generate` gibi: `Tag.is_active`, eksikse 404 `{missing_tag_ids}`).
- `build_report_template_dashboard(...)` → şablon alanlarını geçir (title=`tmpl.name`).
- Grafana yaz: `POST /api/dashboards/db {dashboard, overwrite:True}`, client
  `auth=render_auth()` + `headers=render_headers()` (SA-token→basic-auth, render
  servisiyle tutarlı).
- httpx hata → **502**; Grafana 4xx/5xx → **502**.
- Dönüş: `{uid, title, url, template_id, status}` (mevcut `generate` şekliyle uyumlu).

## Bölüm 3 — Frontend buton + client + i18n

**client.ts:**
```ts
export const generateDashboardFromTemplate = (templateId: number) =>
  api.post<{ uid: string; title: string; url: string; template_id: number; status: string }>(
    `/grafana/dashboards/from-report-template/${templateId}`)
```

**AdvancedReports.tsx** — şablon satırına "Çalıştır/Düzenle/Sil" yanına
**"Grafana Dashboard"** butonu:
- Tıkla → `generateDashboardFromTemplate(id)` mutation; yüklenirken disabled + "Oluşturuluyor...".
- Başarı → inline mesaj + "Grafana'da Aç" linki (yeni sekme `${GRAFANA_URL}${url}`).
- Hata → inline (422 tag'siz / 404 / 502 ayırt edilir).

**i18n (5 dil, `advancedReports`):** `gen_dashboard`, `gen_dashboard_loading`,
`gen_dashboard_success`, `gen_dashboard_open`, `gen_dashboard_no_tags`.

Feature-gate: frontend feature-flag pattern yok → buton her zaman görünür,
backend 403/422 ile gate'ler (hata inline).

## Bölüm 4 — Test

**Backend birim (`tests/test_grafana_report_dashboard.py`):**
- Tüm bayraklar → stat+timeseries+table; uid `sr-rpt-{id}`.
- Sadece `show_trend_charts` → yalnız timeseries.
- Hiç bayrak → en az trend paneli (boş-değil garantisi).
- `time_range_type` eşleme: last_7d→`now-7d`; custom→custom_start/end.
- SQL'de tag_ids IN filtresi int-coerce (injection yok).

**Backend API (`tests/test_grafana_report_dashboard_api.py`, httpx.MockTransport):**
- tag'li şablon → Grafana mock'a `POST /api/dashboards/db`, dönüş `{uid,url}`.
- olmayan template → 404; tag_ids boş → 422; feature gate kapalı → 403;
  Grafana transport hatası → 502.

**Frontend (vitest, harness varsa):** buton tıkla → helper çağrılıyor (mock),
başarı linki görünüyor. Harness yoksa tsc + manuel, atla.

**Doğrulama:** `just test` (-n auto) + `tsc -b` + tarayıcı e2e (şablondan dashboard
üret → Grafana'da aç).

## Out of scope (YAGNI)

- Şablonun `grafana_panels`'ını (rapor panel referansları) türetilen dashboard'a dahil etme.
- Oto-senkron (şablon CRUD'da otomatik dashboard güncelleme).
- Stale dashboard temizliği (deterministik uid + overwrite yeterli).

## Sonraki adım

`writing-plans` skill'i ile uygulama planı.
