# Rapor Şablonundan Grafana Dashboard Türetme — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mevcut bir `ReportTemplate`'ten tek tıkla Grafana dashboard türetmek (paneller şablon bayraklarına göre, zaman aralığı `time_range_type`'tan).

**Architecture:** `grafana_templates.py`'deki mevcut panel helper'ları (`_timeseries_panel`/`_table_panel`/`_base_dashboard`/`_tag_filter`) yeniden kullanılarak yeni `build_report_template_dashboard()` üreteci; `grafana_dashboards.py`'ye `POST /grafana/dashboards/from-report-template/{id}` endpoint'i; AdvancedReports şablon satırına buton. `c3905fe`'nin template-based generation deseni üstüne kurulur.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic v2, httpx (async + MockTransport), React 19 + TanStack Query, pytest-asyncio.

## Global Constraints

- Python 3.14; `just check` (ruff + mypy + format) temiz olmalı.
- Backend testleri `just test` (pytest-xdist `-n auto`, randomized); order-independent. TDD targeted runs `-n0`.
- Yeni endpoint `require_feature("grafana")` + `get_current_user` arkasında.
- Grafana HTTP client: `auth=render_auth()` + `headers=render_headers()` (SA-token→basic-auth; `app/services/grafana_render.py`).
- Datasource: `{"type": "postgres", "uid": "timescaledb"}` (mevcut şablonlarla aynı).
- uid deterministik: `sr-rpt-{template_id}`; Grafana yazımı `overwrite=True`.
- `tag_ids` SQL'e yalnız int-coerce ile girer (injection yok; mevcut `_tag_filter`).
- i18n: yeni kullanıcıya görünür metin 5 dile (en/tr/ru/de/ar), `advancedReports` namespace, `t()` ile.
- httpx test deseni: `httpx.MockTransport(handler)` (bkz. `tests/test_grafana_api.py`).
- Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Dashboard üreteci `build_report_template_dashboard`

**Files:**
- Modify: `scada-reporter/backend/app/services/grafana_templates.py`
- Test: `scada-reporter/backend/tests/test_grafana_report_dashboard.py` (create)

**Interfaces:**
- Consumes: mevcut `_timeseries_panel`, `_table_panel`, `_base_dashboard`, `_tag_filter` (aynı dosya).
- Produces:
  - `report_dashboard_uid(template_id: int) -> str` → `"sr-rpt-{template_id}"`.
  - `resolve_dashboard_time(time_range_type: str, custom_start, custom_end) -> dict` → `{"from": str, "to": str}`.
  - `build_report_template_dashboard(*, template_id: int, title: str, tag_ids: list[int], time_range_type: str, custom_start=None, custom_end=None, show_trend_charts: bool, show_summary_stats: bool, anomaly_enabled: bool, show_anomaly_table: bool) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grafana_report_dashboard.py
import pytest

from app.services.grafana_templates import (
    build_report_template_dashboard,
    report_dashboard_uid,
    resolve_dashboard_time,
)


def test_report_dashboard_uid_deterministic():
    assert report_dashboard_uid(7) == "sr-rpt-7"


def test_resolve_time_presets():
    assert resolve_dashboard_time("last_1h", None, None) == {"from": "now-1h", "to": "now"}
    assert resolve_dashboard_time("last_24h", None, None) == {"from": "now-24h", "to": "now"}
    assert resolve_dashboard_time("last_7d", None, None) == {"from": "now-7d", "to": "now"}
    assert resolve_dashboard_time("last_30d", None, None) == {"from": "now-30d", "to": "now"}


def test_resolve_time_custom():
    from datetime import UTC, datetime

    s = datetime(2026, 1, 1, tzinfo=UTC)
    e = datetime(2026, 1, 2, tzinfo=UTC)
    out = resolve_dashboard_time("custom", s, e)
    assert out["from"] == s.isoformat()
    assert out["to"] == e.isoformat()


def _kw(**over):
    base = dict(
        template_id=3, title="Rapor X", tag_ids=[1, 2],
        time_range_type="last_7d", custom_start=None, custom_end=None,
        show_trend_charts=True, show_summary_stats=True,
        anomaly_enabled=True, show_anomaly_table=True,
    )
    base.update(over)
    return base


def test_all_flags_produce_three_panel_types():
    d = build_report_template_dashboard(**_kw())
    assert d["uid"] == "sr-rpt-3"
    assert d["title"] == "Rapor X"
    assert d["time"] == {"from": "now-7d", "to": "now"}
    types = [p["type"] for p in d["panels"]]
    assert "timeseries" in types  # trend
    assert types.count("table") == 2  # summary + anomaly
    # tag filter present in trend SQL, int-coerced
    trend = next(p for p in d["panels"] if p["type"] == "timeseries")
    assert "1, 2" in trend["targets"][0]["rawSql"]


def test_only_trend_flag_yields_single_panel():
    d = build_report_template_dashboard(
        **_kw(show_summary_stats=False, anomaly_enabled=False, show_anomaly_table=False)
    )
    assert [p["type"] for p in d["panels"]] == ["timeseries"]


def test_no_flags_still_has_trend_panel():
    d = build_report_template_dashboard(
        **_kw(show_trend_charts=False, show_summary_stats=False,
              anomaly_enabled=False, show_anomaly_table=False)
    )
    assert any(p["type"] == "timeseries" for p in d["panels"])
    assert len(d["panels"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/project/smart/scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_grafana_report_dashboard.py -v -n0`
Expected: FAIL — ImportError (`build_report_template_dashboard` yok).

- [ ] **Step 3: Implement the generator**

`grafana_templates.py` sonuna ekle:

```python
def report_dashboard_uid(template_id: int) -> str:
    return f"sr-rpt-{int(template_id)}"


def resolve_dashboard_time(time_range_type: str, custom_start, custom_end) -> dict:
    presets = {
        "last_1h": "now-1h",
        "last_24h": "now-24h",
        "last_7d": "now-7d",
        "last_30d": "now-30d",
    }
    if time_range_type == "custom" and custom_start and custom_end:
        return {"from": custom_start.isoformat(), "to": custom_end.isoformat()}
    return {"from": presets.get(time_range_type, "now-24h"), "to": "now"}


def build_report_template_dashboard(
    *,
    template_id: int,
    title: str,
    tag_ids: list[int],
    time_range_type: str,
    custom_start=None,
    custom_end=None,
    show_trend_charts: bool,
    show_summary_stats: bool,
    anomaly_enabled: bool,
    show_anomaly_table: bool,
) -> dict:
    ids = _tag_filter(tag_ids)  # int-coerce + validate non-empty
    panels: list[dict] = []
    pid = 1
    y = 0

    # Trend timeseries — included if requested OR as the non-empty fallback.
    want_trend = show_trend_charts or not (show_summary_stats or (anomaly_enabled and show_anomaly_table))
    if want_trend:
        panels.append(
            _timeseries_panel(
                pid,
                "Tag Trendleri",
                (
                    "SELECT $__time(tr.timestamp) AS time, t.name AS metric, tr.value AS value "
                    "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
                    f"WHERE $__timeFilter(tr.timestamp) AND tr.tag_id IN ({ids}) ORDER BY 1"
                ),
                x=0, y=y, w=24, h=11,
            )
        )
        pid += 1
        y += 11

    if show_summary_stats:
        panels.append(
            _table_panel(
                pid,
                "Son Değerler",
                (
                    "SELECT DISTINCT ON (t.id) t.name, tr.value, t.unit, tr.quality, tr.timestamp "
                    "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
                    f"WHERE t.id IN ({ids}) ORDER BY t.id, tr.timestamp DESC"
                ),
                x=0, y=y, w=12, h=8,
            )
        )
        pid += 1

    if anomaly_enabled and show_anomaly_table:
        panels.append(
            _table_panel(
                pid,
                "Limit Aşımı Özeti",
                (
                    "SELECT t.name, "
                    "sum(CASE WHEN t.min_alarm IS NOT NULL "
                    "AND tr.value < t.min_alarm THEN 1 ELSE 0 END) AS \"Alt Limit\", "
                    "sum(CASE WHEN t.max_alarm IS NOT NULL "
                    "AND tr.value > t.max_alarm THEN 1 ELSE 0 END) AS \"Üst Limit\" "
                    "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
                    f"WHERE $__timeFilter(tr.timestamp) AND t.id IN ({ids}) "
                    "GROUP BY t.name ORDER BY t.name"
                ),
                x=12, y=y, w=12, h=8,
            )
        )
        pid += 1

    dash = _base_dashboard(report_dashboard_uid(template_id), title, ["report-template"], panels)
    dash["time"] = resolve_dashboard_time(time_range_type, custom_start, custom_end)
    return dash
```

> NOT: `_tag_filter` boş `tag_ids`'te `ValueError` atar — çağıran (Task 2) önce 422 döndürür, bu yüzden bu fonksiyon boş-tag senaryosunu görmez. Testler hep dolu tag verir.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_report_dashboard.py -v -n0`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/grafana_templates.py scada-reporter/backend/tests/test_grafana_report_dashboard.py
git commit -m "feat(grafana): build dashboard from report template (flag-driven panels)"
```

---

### Task 2: Endpoint `POST /grafana/dashboards/from-report-template/{id}`

**Files:**
- Modify: `scada-reporter/backend/app/api/grafana_dashboards.py`
- Test: `scada-reporter/backend/tests/test_grafana_report_dashboard_api.py` (create)

**Interfaces:**
- Consumes: `build_report_template_dashboard`, `report_dashboard_uid` (Task 1); `render_auth`/`render_headers` (`app/services/grafana_render.py`); `ReportTemplate` model.
- Produces: `POST /api/grafana/dashboards/from-report-template/{template_id}` → `{"uid","title","url","template_id","status"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grafana_report_dashboard_api.py
import json

import httpx
import pytest

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.main import app
from app.models.report_template import ReportTemplate
from app.models.user import User
from app.core.security import hash_password  # adjust import if needed


@pytest.fixture
def _auth_override():
    fake = User(id=1, username="a", email="a@x.io", hashed_password="x", role="admin")
    guard = require_feature("grafana")
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[guard] = lambda: None
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(guard, None)


async def _mk_template(db, tag_ids):
    t = ReportTemplate(name="Rapor X", tag_ids=json.dumps(tag_ids), grafana_panels="[]")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@pytest.mark.asyncio
async def test_generate_from_report_template(client, db_session, monkeypatch, _auth_override):
    tmpl = await _mk_template(db_session, [1, 2])
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/dashboards/db":
            posted["json"] = json.loads(request.content)
            return httpx.Response(200, json={"status": "success", "url": "/d/sr-rpt-1/x"})
        return httpx.Response(404)

    import app.api.grafana_dashboards as gd
    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(handler), raising=False)

    r = await client.post(f"/api/grafana/dashboards/from-report-template/{tmpl.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uid"] == f"sr-rpt-{tmpl.id}"
    assert body["template_id"] == tmpl.id
    assert posted["json"]["overwrite"] is True


@pytest.mark.asyncio
async def test_missing_template_404(client, monkeypatch, _auth_override):
    import app.api.grafana_dashboards as gd
    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False)
    r = await client.post("/api/grafana/dashboards/from-report-template/99999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_empty_tags_422(client, db_session, monkeypatch, _auth_override):
    tmpl = await _mk_template(db_session, [])
    import app.api.grafana_dashboards as gd
    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False)
    r = await client.post(f"/api/grafana/dashboards/from-report-template/{tmpl.id}")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_grafana_transport_error_502(client, db_session, monkeypatch, _auth_override):
    tmpl = await _mk_template(db_session, [1])

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    import app.api.grafana_dashboards as gd
    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(boom), raising=False)
    r = await client.post(f"/api/grafana/dashboards/from-report-template/{tmpl.id}")
    assert r.status_code == 502
```

> NOT: `_auth_override` fixture'ı `require_feature("grafana")` guard'ını referansıyla pop'lar (`.clear()` KULLANMA — conftest `get_db` override'ını siler; bkz. test_grafana_api.py isolation fix). `User`/`hash_password` import yollarını mevcut bir test dosyasından (örn. `test_grafana_api.py`, `test_token_versioning.py`) doğrula.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_report_dashboard_api.py -v -n0`
Expected: FAIL — 404 (route yok) / AttributeError.

- [ ] **Step 3: Implement the endpoint**

`grafana_dashboards.py` üst importlara ekle:

```python
import json as _json

from app.models.report_template import ReportTemplate
from app.services.grafana_render import render_auth, render_headers
from app.services.grafana_templates import build_report_template_dashboard, report_dashboard_uid
```

Modül seviyesine (router tanımından sonra) test-enjekte edilebilir transport ekle:

```python
_transport = None  # httpx.MockTransport | None — testlerde monkeypatch'lenir
```

Yeni route (dosya sonuna):

```python
@router.post("/dashboards/from-report-template/{template_id}")
async def generate_from_report_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _feature=Depends(require_feature("grafana")),
) -> dict:
    tmpl = await db.get(ReportTemplate, template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")

    tag_ids = _json.loads(tmpl.tag_ids or "[]")
    if not tag_ids:
        raise HTTPException(status_code=422, detail="Dashboard için tag'li bir şablon gerekir")

    rows = (
        (await db.execute(select(Tag.id).where(Tag.id.in_(tag_ids), Tag.is_active.is_(True))))
        .scalars()
        .all()
    )
    missing = sorted(set(tag_ids) - set(rows))
    if missing:
        raise HTTPException(status_code=404, detail={"missing_tag_ids": missing})

    dashboard = build_report_template_dashboard(
        template_id=tmpl.id,
        title=tmpl.name,
        tag_ids=tag_ids,
        time_range_type=tmpl.time_range_type,
        custom_start=tmpl.custom_start,
        custom_end=tmpl.custom_end,
        show_trend_charts=tmpl.show_trend_charts,
        show_summary_stats=tmpl.show_summary_stats,
        anomaly_enabled=tmpl.anomaly_enabled,
        show_anomaly_table=tmpl.show_anomaly_table,
    )

    try:
        async with httpx.AsyncClient(
            base_url=settings.GRAFANA_URL,
            auth=render_auth(),
            headers=render_headers(),
            timeout=10.0,
            transport=_transport,
        ) as http:
            response = await http.post(
                "/api/dashboards/db",
                json={"dashboard": dashboard, "overwrite": True},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"Grafana dashboard yazılamadı: HTTP {response.status_code}"
        )

    payload = response.json()
    return {
        "uid": report_dashboard_uid(tmpl.id),
        "title": tmpl.name,
        "url": payload.get("url") or f"/d/{report_dashboard_uid(tmpl.id)}",
        "template_id": tmpl.id,
        "status": payload.get("status", "success"),
    }
```

> NOT: `select`, `Tag`, `httpx`, `settings`, `HTTPException`, `Depends`, `AsyncSession`, `get_db`, `get_current_user`, `require_feature`, `User` zaten `grafana_dashboards.py`'de importlu (mevcut `generate` endpoint'i kullanıyor) — yalnız eksik olanları ekle.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_report_dashboard_api.py -v -n0`
Expected: PASS (4 passed).

- [ ] **Step 5: Quick route-registration smoke**

Run:
```bash
.venv/Scripts/python -c "from app.main import app; import json; s=app.openapi(); print([p for p in s['paths'] if 'from-report-template' in p])"
```
Expected: `['/api/grafana/dashboards/from-report-template/{template_id}']`

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/api/grafana_dashboards.py scada-reporter/backend/tests/test_grafana_report_dashboard_api.py
git commit -m "feat(api): endpoint to generate grafana dashboard from report template"
```

---

### Task 3: Frontend buton + client + i18n

**Files:**
- Modify: `scada-reporter/frontend/src/api/client.ts`
- Modify: `scada-reporter/frontend/src/pages/AdvancedReports.tsx`
- Modify: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/advancedReports.json`
- Regenerate: `scada-reporter/frontend/src/api/generated/*` + `openapi.json` (`just gen-client`)

**Interfaces:**
- Consumes: `POST /api/grafana/dashboards/from-report-template/{id}` (Task 2).

- [ ] **Step 1: Add client helper**

`client.ts`'e (mevcut `listGrafanaTemplates`/`generateGrafanaDashboard` yanına; path style `/grafana/...`, baseURL `/api` ekler):

```ts
export const generateDashboardFromTemplate = (templateId: number) =>
  api.post<{ uid: string; title: string; url: string; template_id: number; status: string }>(
    `/grafana/dashboards/from-report-template/${templateId}`)
```

- [ ] **Step 2: Add i18n keys (5 locales)**

Her `advancedReports.json`'a ekle. EN: `"gen_dashboard": "Grafana Dashboard"`, `"gen_dashboard_loading": "Oluşturuluyor..."`→"Generating...", `"gen_dashboard_open": "Open in Grafana"`, `"gen_dashboard_no_tags": "Template needs at least one tag"`, `"gen_dashboard_error": "Dashboard generation failed"`.
TR: `"Grafana Dashboard"`, `"Oluşturuluyor..."`, `"Grafana'da Aç"`, `"Tag'li şablon gerekir"`, `"Dashboard oluşturulamadı"`. (ru/de/ar eşdeğer çeviriler.)

- [ ] **Step 3: Add the button to the template row**

`AdvancedReports.tsx` şablon tablosu satırında "Çalıştır/Düzenle/Sil" grubuna **"Grafana Dashboard"** butonu ekle:
- `useMutation({ mutationFn: () => generateDashboardFromTemplate(t.id) })`.
- Pending → buton disabled + `t('gen_dashboard_loading')`.
- `onSuccess(data)` → inline başarı: `t('gen_dashboard_open')` linki, `href={`${GRAFANA_URL}${data.data.url}`}` (Grafana.tsx'teki `GRAFANA_URL` sabitini içe al ya da `import.meta.env.VITE_GRAFANA_URL ?? 'http://localhost:3000'`), `target="_blank"`.
- `onError(err)` → inline hata: 422 ise `t('gen_dashboard_no_tags')`, değilse `t('gen_dashboard_error')` (axios err.response?.status kontrolü).
- Mevcut satır buton stilini (text-xs, renkli) izle.

> NOT: AdvancedReports.tsx büyük; şablon listesini render eden bölümü (template rows, `Çalıştır` butonunun olduğu yer — bu repoda ~ref e201 civarı) bul ve buraya ekle. Mutation state per-row olmalı (her satır kendi durumu) — satırı küçük bir `TemplateRow` bileşenine çıkarmak temiz olur; dosya zaten büyükse mevcut inline desene uyup `useMutation`'ı satır map'i içinde tutma (React hook kuralı) yerine tek mutation + aktif templateId state ile yönet.

- [ ] **Step 4: Regenerate client + verify types**

Run: `just gen-client` (repo root; `dump_openapi.py` app'i import eder, servis restart gerekmez).
Run: `cd scada-reporter/frontend && pnpm exec tsc -b`
Expected: `0 errors`.
Run: `pnpm build`
Expected: başarılı.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/pages/AdvancedReports.tsx scada-reporter/frontend/src/i18n/locales/*/advancedReports.json scada-reporter/frontend/src/api/generated/ scada-reporter/frontend/openapi.json
git commit -m "feat(frontend): generate grafana dashboard from report template button"
```

---

### Task 4: Uçtan uca doğrulama + tam test

**Files:** yok (doğrulama).

- [ ] **Step 1: Full backend suite**

Run: `cd /c/project/smart/scada-reporter/backend && .venv/Scripts/python -m pytest -q`
Expected: tümü PASS (yeni testler + regresyon yok).

- [ ] **Step 2: Lint + types**

Run (repo root): `just check`
Expected: ruff + mypy + format temiz.
Run: `cd scada-reporter/frontend && pnpm exec tsc -b`
Expected: 0 errors.

- [ ] **Step 3: Manuel/tarayıcı smoke (servisler ayakta; backend restart edilmiş güncel kod ile)**

- Frontend → Gelişmiş Raporlar → tag'li bir şablonda **"Grafana Dashboard"** → başarı linki.
- "Grafana'da Aç" → yeni sekmede `sr-rpt-{id}` dashboard'u, panelleri (trend/son-değerler/limit) görünür.
- Tag'siz şablonda buton → 422 inline mesaj ("Tag'li şablon gerekir").

- [ ] **Step 4: Final commit (gerekirse)**

Kalan düzeltmeler varsa commit et.

---

## Self-Review Notları

- **Spec kapsamı:** Bölüm 1→Task 1, Bölüm 2→Task 2, Bölüm 3→Task 3, Bölüm 4→Task 1/2/4. Tüm bölümler kapsandı.
- **Tip tutarlılığı:** `report_dashboard_uid(id)`/`resolve_dashboard_time(...)`/`build_report_template_dashboard(**kw)` Task 1'de tanımlı, Task 2'de aynı imzayla çağrılıyor. Dönüş `{uid,title,url,template_id,status}` Task 2 ↔ Task 3 client tipi aynı.
- **Auth:** `render_auth()`+`render_headers()` (mevcut `generate` sadece basic-auth kullanıyordu; bu endpoint render servisiyle tutarlı katmanlı auth kullanır — kasıtlı iyileştirme).
- **Test izolasyonu:** `_auth_override` guard-ref pop (no `.clear()`), `_transport` monkeypatch — mevcut test_grafana_api.py deseniyle aynı.
- **Boş-tag:** `_tag_filter` ValueError → endpoint 422 ile önler (üreteç boş-tag görmez).
- **YAGNI:** grafana_panels dahil değil, oto-senkron yok, stale temizliği yok (deterministik uid + overwrite).
