# Grafana Panellerini Raporlara Gömme — Tasarım

**Tarih:** 2026-06-23
**Durum:** Onaylandı (uygulama bekliyor)
**Kapsam:** Smart Report ↔ Grafana entegrasyonu, Faz 1

## Amaç

Rapor şablonlarına "Grafana paneli" referansları eklenebilsin; rapor (PDF + Excel)
üretilirken bu panellerin görüntüsü Grafana `/render` API'sinden çekilip rapora
gömülsün. Şu an raporlar grafiklerini yalnızca matplotlib (`chart_generator.py`) ile
üretiyor; Grafana panel gömme yok — bu özellik sıfırdan eklenir, mevcut chart akışına
oturur.

## Kararlar (özet)

| Konu | Karar |
|------|-------|
| Dahil etme şekli | Şablona "Grafana paneli" bloğu (panel referansları listesi) |
| Çıktı formatı | PDF + Excel (JSON'da sadece metin referans) |
| Panel seçimi | Dashboard dropdown → panel dropdown (backend proxy) |
| Zaman aralığı | Şablonun mevcut time range'i panele de uygulanır |
| Render auth | Service-account token (Bearer); yoksa basic-auth fallback |
| Yaklaşım | Render-on-generate (snapshot cache YOK — YAGNI) |

## Mimari

```
Şablon (grafana_panels JSON)
        │  rapor üretimi
        ▼
report_generator ──► grafana_render.render_panel() ──► Grafana /render/d-solo ──► PNG
        │                                                    (renderer :8081)
        ▼
grafana_charts[] ──► pdf_builder (report.html.j2)  ──► PDF
                └──► excel_builder (_embed_image)   ──► XLSX
```

## Bölüm 1 — Veri modeli

`ReportTemplate`'e tek yeni alan:

```python
grafana_panels: Mapped[str] = mapped_column(Text, default="[]")
# JSON: [{"dashboard_uid": "scada-watchlist", "panel_id": 1, "title": "Debi"}]
```

- Alembic migration, additive, default `"[]"` → mevcut şablonlar etkilenmez.
- Pydantic şemalar (`TemplateCreate/Update/Response`): `grafana_panels: list[GrafanaPanelRef]`
  - `GrafanaPanelRef = {dashboard_uid: str, panel_id: int, title: str}`
- Time range ayrı tutulmaz; şablonun `time_range_type`/`custom_start`/`custom_end` alanları kullanılır.

## Bölüm 2 — Render servisi + auth

Yeni dosya: `app/services/grafana_render.py`

```python
async def render_panel(
    *, dashboard_uid: str, panel_id: int,
    from_ms: int, to_ms: int, theme: str = "light",
    width: int = 1000, height: int = 500, tz: str = "UTC",
    http: httpx.AsyncClient,
) -> bytes: ...
```

- **Çağrı:** `GET /render/d-solo/<uid>/_?panelId=<id>&from=<ms>&to=<ms>&width=&height=&theme=&tz=&kiosk`
  → PNG bytes (renderer servisi `:8081` üretir, Grafana proxy'ler).
- **Auth (katmanlı):**
  1. `GRAFANA_SA_TOKEN` set ise → `Authorization: Bearer <token>` (prod, seçilen yol).
  2. Yoksa → mevcut `GRAFANA_USER`/`GRAFANA_PASSWORD` basic-auth fallback (dev).
- **Yeni config (`config.py`):**
  - `GRAFANA_SA_TOKEN: str = ""`
  - `GRAFANA_RENDER_TIMEOUT: float = 30.0`
  - `GRAFANA_RENDER_WIDTH: int = 1000`, `GRAFANA_RENDER_HEIGHT: int = 500`
- **Hata yönetimi (kritik):** Render başarısız (timeout / renderer down / HTTP≥400) →
  rapor **fail OLMAZ**. Panel atlanır, `errors` listesine `"render <uid>/<id>: <sebep>"`
  eklenir, raporda o panel yerine kısa "render edilemedi" notu görünür.
- **Theme:** rapor görseli için `light` sabit (beyaz zemin, PDF/Excel'e uygun).

## Bölüm 3 — Rapor üretimi entegrasyonu + PDF/Excel gömme

**`report_generator.py`:**
- `resolve_time_range()` start/end → epoch ms (`from_ms`/`to_ms`).
- Tag döngüsünden sonra: `template.grafana_panels` parse, her ref için `render_panel(...)`
  (paylaşılan `httpx.AsyncClient`, base_url=`GRAFANA_URL`).
- Rapor seviyesinde liste:
  ```python
  grafana_charts = [{"title": ref.title, "png": bytes_or_empty, "error": str_or_None}]
  ```
- `build_pdf(...)` ve `build_advanced_excel(...)` çağrılarına yeni parametre.
- JSON çıktıda: `{title, dashboard_uid, panel_id, rendered: bool}` (görsel yok).

**PDF (`pdf_builder.py` + `templates/report.html.j2`):**
- `grafana_charts` context'e eklenir.
- `.j2`'ye yeni bölüm "Grafana Panelleri": her panel `<img src="data:image/png;base64,...">`
  (mevcut `chart_b64` deseni); `error` varsa görsel yerine not.

**Excel (`excel_builder.py`):**
- Yeni sheet "Grafana": mevcut `_embed_image(ws, png, anchor)` ile her panel görseli +
  başlık ardışık. `error` varsa hücreye not.

**Sıralama:** Grafana panelleri raporun sonunda (trend/anomali bölümlerinden sonra).

## Bölüm 4 — Backend panel-list endpoint + frontend editör

**Backend — yeni router `app/api/grafana.py`** (prefix `/api/grafana`, `require_feature("grafana")`):
- `GET /dashboards` → Grafana `/api/search?type=dash-db` proxy → `[{uid, title}]`.
- `GET /dashboards/{uid}/panels` → Grafana `/api/dashboards/uid/{uid}` →
  `dashboard.panels[]`'ten `[{id, title}]` (row/başlıksız panelleri ele).
- İkisi de Bölüm 2'deki katmanlı auth'u kullanır.

**Frontend — şablon editörü (`AdvancedReports` template formu):**
- Yeni bölüm "Grafana Panelleri":
  - Dashboard `<select>` (← `/api/grafana/dashboards`)
  - Panel `<select>` (← `/api/grafana/dashboards/{uid}/panels`, dashboard seçilince)
  - "Ekle" → liste (uid + panelId + title), silinebilir.
- Submit → `grafana_panels` array'i create/update payload'ında.
- `just gen-client` ile TS client yenilenir.
- i18n: 5 dile yeni anahtarlar (`advancedReports` namespace).
- "grafana" feature gate arkasında — demo/lisanssız modda gizli/pasif.

## Bölüm 5 — Test + kurulum

**Testler (pytest):**
- `grafana_render`: `httpx.MockTransport` — başarılı render, timeout/HTTP≥400 → boş + error,
  auth header seçimi (SA token → Bearer, yoksa basic).
- `report_generator`: `grafana_panels` dolu şablon (render mock) → `grafana_charts` builder'a
  doğru geçiyor mu; bir panel hata verince diğerleri + rapor tamamlanıyor mu
  (`status="completed"`, error kaydı).
- `excel_builder`/`pdf_builder`: `grafana_charts` ile görsel/bölüm; boş listede regresyon yok.
- API: `/api/grafana/dashboards` ve `.../panels` (Grafana mock); feature gate kapalı → 403.
- Template create/update: `grafana_panels` round-trip.

**Migration:** `just makemigration` — additive, default `"[]"`.

**Dokümantasyon:**
- Yeni `docs/grafana-report-panels.md`: service-account token oluşturma
  (Grafana → Administration → Service accounts → "render" rolü → token), `.env`'e
  `GRAFANA_SA_TOKEN=...`, renderer servisi (`:8081`) gereği.
- `.env.example` + `CLAUDE.md` notu.

## Out of scope (YAGNI)

- Panel snapshot cache
- Panel başına ayrı time range
- JSON çıktıya görsel gömme
- Panel boyut/tema'nın UI'dan ayarı (sabit varsayılan)

## Sonraki adım

`writing-plans` skill'i ile uygulama planı oluşturulacak.
