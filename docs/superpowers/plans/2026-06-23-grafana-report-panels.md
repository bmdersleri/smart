# Grafana Panellerini Raporlara Gömme — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rapor şablonlarına Grafana paneli referansları eklenip rapor (PDF + Excel) üretilirken bu panellerin görüntüsünün Grafana `/render` API'sinden çekilip gömülmesi.

**Architecture:** Render-on-generate. Şablona `grafana_panels` JSON alanı eklenir; `report_generator` her referans için `grafana_render.render_panel()` çağırır (httpx → Grafana `/render/d-solo`), sonuç PNG listesi PDF (`report.html.j2`) ve Excel (`_embed_image`) çıktısına gömülür. Render hatası raporu düşürmez. Panel seçimi backend proxy endpoint + frontend dropdown ile.

**Tech Stack:** FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2, httpx (async + MockTransport test), openpyxl, WeasyPrint + Jinja2, React 19 + TanStack Query, pytest-asyncio.

## Global Constraints

- Python 3.14; `just check` (ruff + mypy + format) temiz olmalı.
- Testler `just test` (pytest-xdist `-n auto`, randomized) — sıra bağımsız, başka testin verisine güvenme.
- DB: dev/test SQLite (in-memory, autouse tablo temizleme). Migration **additive**, default `"[]"`.
- Tüm yeni endpoint + UI `require_feature("grafana")` arkasında.
- i18n: yeni kullanıcıya görünür metin 5 dile (en/tr/ru/de/ar) eklenir.
- httpx test deseni: `httpx.MockTransport(handler)` (bkz. `tests/test_grafana_sync.py`).
- Render görseli teması sabit `light`.
- Commit mesajları sonunda: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Veri modeli — `grafana_panels` alanı + migration

**Files:**
- Modify: `scada-reporter/backend/app/models/report_template.py`
- Test: `scada-reporter/backend/tests/test_report_template_model.py` (create)

**Interfaces:**
- Produces: `ReportTemplate.grafana_panels: Mapped[str]` — JSON string, default `"[]"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_template_model.py
import json

import pytest
from sqlalchemy import select

from app.models.report_template import ReportTemplate


@pytest.mark.asyncio
async def test_grafana_panels_defaults_to_empty_list(db_session):
    tpl = ReportTemplate(name="t1", tag_ids="[1]")
    db_session.add(tpl)
    await db_session.commit()
    row = await db_session.scalar(select(ReportTemplate).where(ReportTemplate.name == "t1"))
    assert json.loads(row.grafana_panels) == []


@pytest.mark.asyncio
async def test_grafana_panels_round_trips_json(db_session):
    panels = [{"dashboard_uid": "scada-watchlist", "panel_id": 1, "title": "Debi"}]
    tpl = ReportTemplate(name="t2", tag_ids="[1]", grafana_panels=json.dumps(panels))
    db_session.add(tpl)
    await db_session.commit()
    row = await db_session.scalar(select(ReportTemplate).where(ReportTemplate.name == "t2"))
    assert json.loads(row.grafana_panels) == panels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_template_model.py -v -n0`
Expected: FAIL — `TypeError: 'grafana_panels' is an invalid keyword argument` veya AttributeError.

- [ ] **Step 3: Add the column**

`report_template.py` içinde `show_raw_data` satırından sonra ekle:

```python
    grafana_panels: Mapped[str] = mapped_column(Text, default="[]")
    # JSON: [{"dashboard_uid": "scada-watchlist", "panel_id": 1, "title": "Debi"}]
```

(`Text` zaten import edili.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_report_template_model.py -v -n0`
Expected: PASS (2 passed).

- [ ] **Step 5: Create the migration**

Run: `just makemigration msg="add grafana_panels to report_templates"`
Migration dosyasını aç; `op.add_column` satırının `server_default="[]"` içerdiğini doğrula (yoksa elle ekle), aksi halde mevcut satırlar NULL kalır:

```python
op.add_column(
    "report_templates",
    sa.Column("grafana_panels", sa.Text(), nullable=False, server_default="[]"),
)
```

Sonra: `just migrate`

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/models/report_template.py scada-reporter/backend/tests/test_report_template_model.py scada-reporter/backend/alembic/
git commit -m "feat(reports): add grafana_panels field to report templates"
```

---

### Task 2: Pydantic şemalar + create/update serileştirme

**Files:**
- Modify: `scada-reporter/backend/app/api/advanced_reports.py`
- Test: `scada-reporter/backend/tests/test_grafana_panels_schema.py` (create)

**Interfaces:**
- Consumes: `ReportTemplate.grafana_panels` (Task 1).
- Produces:
  - `GrafanaPanelRef(BaseModel)` = `{dashboard_uid: str, panel_id: int, title: str}`
  - `TemplateCreate.grafana_panels: list[GrafanaPanelRef] = []`
  - `TemplateResponse.grafana_panels: list[GrafanaPanelRef]`
  - `TemplateResponse.from_orm` `grafana_panels`'i `json.loads` eder.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grafana_panels_schema.py
import pytest


@pytest.mark.asyncio
async def test_create_template_with_grafana_panels_round_trips(client):
    payload = {
        "name": "gf-tpl",
        "tag_ids": [1],
        "grafana_panels": [
            {"dashboard_uid": "scada-watchlist", "panel_id": 1, "title": "Debi"}
        ],
    }
    r = await client.post("/api/advanced-reports/templates", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["grafana_panels"] == payload["grafana_panels"]

    got = await client.get(f"/api/advanced-reports/templates/{body['id']}")
    assert got.json()["grafana_panels"] == payload["grafana_panels"]


@pytest.mark.asyncio
async def test_create_template_without_panels_defaults_empty(client):
    r = await client.post("/api/advanced-reports/templates", json={"name": "no-gf", "tag_ids": [1]})
    assert r.status_code == 201, r.text
    assert r.json()["grafana_panels"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_panels_schema.py -v -n0`
Expected: FAIL — response'ta `grafana_panels` yok (KeyError) veya create alanı yok sayıyor.

- [ ] **Step 3: Add schema + serialization**

`advanced_reports.py`'de `TemplateCreate`'ten önce ekle:

```python
class GrafanaPanelRef(BaseModel):
    dashboard_uid: str
    panel_id: int
    title: str
```

`TemplateCreate`'e (son alan olarak) ekle:

```python
    grafana_panels: list[GrafanaPanelRef] = []
```

`TemplateResponse`'a (`show_raw_data`'dan sonra) ekle:

```python
    grafana_panels: list[GrafanaPanelRef]
```

`TemplateResponse.from_orm` içinde, `data["percentile_levels"] = ...` satırından sonra ekle:

```python
        data["grafana_panels"] = json.loads(obj.grafana_panels)
```

Create endpoint'inde (`POST /templates`) `ReportTemplate(...)` oluşturulurken `tag_ids=json.dumps(...)` deseni nasılsa, aynı şekilde grafana_panels'i yaz. Create handler'ında ORM nesnesi kurulan yere ekle:

```python
        grafana_panels=json.dumps([p.model_dump() for p in body.grafana_panels]),
```

Update endpoint'inde (`PUT /templates/{id}`) diğer alanların set edildiği yere ekle (yalnız payload'da geldiyse): mevcut update deseni `template.field = body.field` ise:

```python
    template.grafana_panels = json.dumps([p.model_dump() for p in body.grafana_panels])
```

> NOT: Create/update handler'larındaki tam satırları implementer dosyada `tag_ids` set edilen satırın yanına koyar — aynı JSON-dump desenini izle.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_panels_schema.py -v -n0`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/advanced_reports.py scada-reporter/backend/tests/test_grafana_panels_schema.py
git commit -m "feat(reports): grafana_panels in template create/update/response schemas"
```

---

### Task 3: Config alanları

**Files:**
- Modify: `scada-reporter/backend/app/core/config.py`
- Test: `scada-reporter/backend/tests/test_grafana_render_config.py` (create)

**Interfaces:**
- Produces: `settings.GRAFANA_SA_TOKEN: str`, `GRAFANA_RENDER_TIMEOUT: float`, `GRAFANA_RENDER_WIDTH: int`, `GRAFANA_RENDER_HEIGHT: int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grafana_render_config.py
from app.core.config import settings


def test_render_config_defaults():
    assert settings.GRAFANA_SA_TOKEN == ""
    assert settings.GRAFANA_RENDER_TIMEOUT == 30.0
    assert settings.GRAFANA_RENDER_WIDTH == 1000
    assert settings.GRAFANA_RENDER_HEIGHT == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_render_config.py -v -n0`
Expected: FAIL — AttributeError.

- [ ] **Step 3: Add config fields**

`config.py`'de `GRAFANA_PASSWORD` satırından sonra ekle:

```python
    GRAFANA_SA_TOKEN: str = ""  # render için service-account token; boşsa basic-auth fallback
    GRAFANA_RENDER_TIMEOUT: float = 30.0
    GRAFANA_RENDER_WIDTH: int = 1000
    GRAFANA_RENDER_HEIGHT: int = 500
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_render_config.py -v -n0`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/core/config.py scada-reporter/backend/tests/test_grafana_render_config.py
git commit -m "feat(config): grafana render auth + size settings"
```

---

### Task 4: Render servisi `grafana_render.py`

**Files:**
- Create: `scada-reporter/backend/app/services/grafana_render.py`
- Test: `scada-reporter/backend/tests/test_grafana_render.py` (create)

**Interfaces:**
- Consumes: `settings` (Task 3).
- Produces:
  - `build_render_auth(http_kwargs) ` — değil; bunun yerine basit yardımcı `render_headers() -> dict[str, str]` ve `render_auth() -> tuple[str, str] | None`.
  - `async def render_panel(*, dashboard_uid: str, panel_id: int, from_ms: int, to_ms: int, http: httpx.AsyncClient, theme: str = "light", width: int = 1000, height: int = 500, tz: str = "UTC") -> bytes` — başarıda PNG bytes, hata/HTTP≥400'de `b""` (exception fırlatmaz).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grafana_render.py
import httpx
import pytest

from app.services.grafana_render import render_panel


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"fakepngdata"


@pytest.mark.asyncio
async def test_render_panel_returns_png_and_builds_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, content=_png(), headers={"content-type": "image/png"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://gf") as http:
        out = await render_panel(
            dashboard_uid="scada-watchlist", panel_id=2,
            from_ms=1000, to_ms=2000, http=http,
        )

    assert out == _png()
    assert seen["path"] == "/render/d-solo/scada-watchlist/_"
    assert seen["params"]["panelId"] == "2"
    assert seen["params"]["from"] == "1000"
    assert seen["params"]["to"] == "2000"
    assert seen["params"]["theme"] == "light"


@pytest.mark.asyncio
async def test_render_panel_swallows_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://gf") as http:
        out = await render_panel(
            dashboard_uid="x", panel_id=1, from_ms=0, to_ms=1, http=http
        )
    assert out == b""


@pytest.mark.asyncio
async def test_render_panel_swallows_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://gf") as http:
        out = await render_panel(
            dashboard_uid="x", panel_id=1, from_ms=0, to_ms=1, http=http
        )
    assert out == b""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_render.py -v -n0`
Expected: FAIL — ModuleNotFoundError: `app.services.grafana_render`.

- [ ] **Step 3: Implement the service**

```python
# app/services/grafana_render.py
from __future__ import annotations

import httpx

from app.core.config import settings


def render_auth() -> tuple[str, str] | None:
    """Basic-auth fallback; SA token varsa None (header ile gider)."""
    if settings.GRAFANA_SA_TOKEN:
        return None
    return (settings.GRAFANA_USER, settings.GRAFANA_PASSWORD)


def render_headers() -> dict[str, str]:
    if settings.GRAFANA_SA_TOKEN:
        return {"Authorization": f"Bearer {settings.GRAFANA_SA_TOKEN}"}
    return {}


async def render_panel(
    *,
    dashboard_uid: str,
    panel_id: int,
    from_ms: int,
    to_ms: int,
    http: httpx.AsyncClient,
    theme: str = "light",
    width: int = 1000,
    height: int = 500,
    tz: str = "UTC",
) -> bytes:
    """Grafana /render/d-solo'dan panel PNG'si çek. Hata olursa b"" döner (raporu düşürmez)."""
    params = {
        "panelId": panel_id,
        "from": from_ms,
        "to": to_ms,
        "width": width,
        "height": height,
        "theme": theme,
        "tz": tz,
        "kiosk": "",
    }
    try:
        r = await http.get(
            f"/render/d-solo/{dashboard_uid}/_",
            params=params,
            headers=render_headers(),
        )
        if r.status_code >= 400:
            return b""
        return r.content
    except httpx.HTTPError:
        return b""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_render.py -v -n0`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/grafana_render.py scada-reporter/backend/tests/test_grafana_render.py
git commit -m "feat(reports): grafana panel render service (error-tolerant)"
```

---

### Task 5: PDF builder — Grafana bölümü

**Files:**
- Modify: `scada-reporter/backend/app/services/pdf_builder.py`
- Modify: `scada-reporter/backend/app/templates/report.html.j2`
- Test: `scada-reporter/backend/tests/test_pdf_grafana_section.py` (create)

**Interfaces:**
- Produces: `build_pdf(..., grafana_charts: list[dict] | None = None)` — `grafana_charts` öğeleri `{"title": str, "png": bytes, "error": str | None}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pdf_grafana_section.py
from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.pdf_builder import build_pdf


def _tpl():
    return SimpleNamespace(
        show_summary_stats=False, show_trend_charts=False,
        show_anomaly_table=False, show_raw_data=False,
        include_percentiles=False,
    )


def test_build_pdf_accepts_grafana_charts_without_error():
    archive = SimpleNamespace(id=1)
    out = build_pdf(
        archive, [], _tpl(), "Tesis", datetime.now(UTC), lang="en",
        grafana_charts=[{"title": "Debi", "png": b"", "error": "render edilemedi"}],
    )
    assert out[:4] == b"%PDF"


def test_build_pdf_grafana_charts_defaults_none():
    archive = SimpleNamespace(id=1)
    out = build_pdf(archive, [], _tpl(), "Tesis", datetime.now(UTC), lang="en")
    assert out[:4] == b"%PDF"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_pdf_grafana_section.py -v -n0`
Expected: FAIL — `build_pdf() got an unexpected keyword argument 'grafana_charts'`.

- [ ] **Step 3: Update builder + template**

`pdf_builder.py` — imzayı ve render context'ini güncelle:

```python
def build_pdf(
    archive,
    per_tag_data: list[dict],
    template,
    facility_name: str,
    generated_at: datetime,
    lang: str = "en",
    grafana_charts: list[dict] | None = None,
) -> bytes:
    L = get_labels(lang)  # noqa: N806

    for td in per_tag_data:
        td["chart_b64"] = base64.b64encode(td.get("chart_png", b"")).decode()

    gf_charts = []
    for gc in grafana_charts or []:
        gf_charts.append(
            {
                "title": gc["title"],
                "b64": base64.b64encode(gc.get("png", b"") or b"").decode(),
                "error": gc.get("error"),
            }
        )

    html_str = _env.get_template("report.html.j2").render(
        archive=archive,
        template=template,
        per_tag_data=per_tag_data,
        facility_name=facility_name,
        generated_at=generated_at,
        L=L,
        lang=lang,
        grafana_charts=gf_charts,
    )
    return HTML(string=html_str).write_pdf()
```

`report.html.j2` — dosyanın sonuna (kapanış `</body>` öncesi) ekle:

```jinja
{% if grafana_charts %}
<section class="grafana-panels">
  <h2>{{ L.get('grafana_panels_heading', 'Grafana Panelleri') }}</h2>
  {% for gc in grafana_charts %}
    <div class="grafana-panel">
      <h3>{{ gc.title }}</h3>
      {% if gc.error %}
        <p class="render-error">{{ gc.error }}</p>
      {% else %}
        <img src="data:image/png;base64,{{ gc.b64 }}" style="max-width:100%;" />
      {% endif %}
    </div>
  {% endfor %}
</section>
{% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_pdf_grafana_section.py -v -n0`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/pdf_builder.py scada-reporter/backend/app/templates/report.html.j2 scada-reporter/backend/tests/test_pdf_grafana_section.py
git commit -m "feat(reports): embed grafana panels in PDF output"
```

---

### Task 6: Excel builder — Grafana sheet

**Files:**
- Modify: `scada-reporter/backend/app/services/excel_builder.py`
- Test: `scada-reporter/backend/tests/test_excel_grafana_sheet.py` (create)

**Interfaces:**
- Produces: `build_advanced_excel(..., grafana_charts: list[dict] | None = None)` — aynı öğe yapısı (`{title, png, error}`). PNG dolu öğeler "Grafana" sheet'ine `_embed_image` ile gömülür.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_excel_grafana_sheet.py
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.services.excel_builder import build_advanced_excel

# 1x1 PNG (geçerli) — openpyxl image yüklemesi için
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8cfc0f01f0005010101a5f6457c0000000049454e44ae426082"
)


def _tpl():
    return SimpleNamespace(
        show_summary_stats=False, show_raw_data=False,
    )


def test_excel_adds_grafana_sheet_with_image():
    archive = SimpleNamespace(id=1)
    out = build_advanced_excel(
        archive, [], _tpl(), b"", lang="en",
        grafana_charts=[{"title": "Debi", "png": _PNG_1x1, "error": None}],
    )
    wb = load_workbook(BytesIO(out))
    assert "Grafana" in wb.sheetnames


def test_excel_no_grafana_sheet_when_empty():
    archive = SimpleNamespace(id=1)
    out = build_advanced_excel(archive, [], _tpl(), b"", lang="en")
    wb = load_workbook(BytesIO(out))
    assert "Grafana" not in wb.sheetnames
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_excel_grafana_sheet.py -v -n0`
Expected: FAIL — `build_advanced_excel() got an unexpected keyword argument 'grafana_charts'`.

- [ ] **Step 3: Update builder**

`excel_builder.py` — imzaya parametre ekle:

```python
def build_advanced_excel(
    archive,
    per_tag_data: list[dict],
    template,
    summary_chart_png: bytes,
    lang: str = "en",
    grafana_charts: list[dict] | None = None,
) -> bytes:
```

`buf = BytesIO()` satırından **hemen önce** (raw data sheet'inden sonra) ekle:

```python
    # --- Grafana panels sheet ---
    gf = [g for g in (grafana_charts or [])]
    if gf:
        ws_gf = wb.create_sheet(title="Grafana")
        row = 1
        for gc in gf:
            ws_gf.cell(row=row, column=1, value=gc["title"]).font = HEADER_FONT
            row += 1
            if gc.get("png"):
                _embed_image(ws_gf, gc["png"], f"A{row}")
                row += 15  # görsel için satır ayır
            else:
                ws_gf.cell(row=row, column=1, value=gc.get("error") or "render edilemedi")
                row += 2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_excel_grafana_sheet.py -v -n0`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/excel_builder.py scada-reporter/backend/tests/test_excel_grafana_sheet.py
git commit -m "feat(reports): embed grafana panels in Excel output"
```

---

### Task 7: Generator entegrasyonu — render edip builder'lara geçir

**Files:**
- Modify: `scada-reporter/backend/app/services/report_generator.py`
- Test: `scada-reporter/backend/tests/test_report_generator_grafana.py` (create)

**Interfaces:**
- Consumes: `render_panel` (Task 4), `build_pdf`/`build_advanced_excel` yeni imzalar (Task 5/6), `ReportTemplate.grafana_panels` (Task 1).
- Produces: generator, `template.grafana_panels` dolu olduğunda her ref için `render_panel` çağırıp `grafana_charts=[{title, png, error}]` üretir ve builder'lara geçirir. Bir panelin render hatası raporu düşürmez (`status="completed"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_generator_grafana.py
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.report_archive import ReportArchive
from app.models.report_template import ReportTemplate
from app.services.report_generator import generate_report_from_template


@pytest.mark.asyncio
async def test_generator_renders_panels_and_passes_to_pdf(db_session):
    tpl = ReportTemplate(
        name="gf", tag_ids="[]", output_format="pdf",
        show_summary_stats=False, show_trend_charts=False,
        show_anomaly_table=False, anomaly_enabled=False,
        grafana_panels=json.dumps(
            [{"dashboard_uid": "d1", "panel_id": 1, "title": "Debi"}]
        ),
    )
    db_session.add(tpl)
    await db_session.commit()
    archive = ReportArchive(template_id=tpl.id, status="pending")
    db_session.add(archive)
    await db_session.commit()

    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)

    captured = {}

    def fake_build_pdf(*args, **kwargs):
        captured["grafana_charts"] = kwargs.get("grafana_charts")
        return b"%PDF-1.4 fake"

    with patch(
        "app.services.report_generator.render_panel",
        new=AsyncMock(return_value=b"PNGBYTES"),
    ), patch("app.services.report_generator.build_pdf", side_effect=fake_build_pdf):
        result = await generate_report_from_template(tpl, start, end, db_session, archive.id)

    assert result.status == "completed"
    assert captured["grafana_charts"][0]["title"] == "Debi"
    assert captured["grafana_charts"][0]["png"] == b"PNGBYTES"
    assert captured["grafana_charts"][0]["error"] is None


@pytest.mark.asyncio
async def test_generator_tolerates_render_failure(db_session):
    tpl = ReportTemplate(
        name="gf2", tag_ids="[]", output_format="pdf",
        show_summary_stats=False, show_trend_charts=False,
        show_anomaly_table=False, anomaly_enabled=False,
        grafana_panels=json.dumps(
            [{"dashboard_uid": "d1", "panel_id": 1, "title": "Debi"}]
        ),
    )
    db_session.add(tpl)
    await db_session.commit()
    archive = ReportArchive(template_id=tpl.id, status="pending")
    db_session.add(archive)
    await db_session.commit()

    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)

    captured = {}

    def fake_build_pdf(*args, **kwargs):
        captured["grafana_charts"] = kwargs.get("grafana_charts")
        return b"%PDF-1.4 fake"

    with patch(
        "app.services.report_generator.render_panel",
        new=AsyncMock(return_value=b""),  # render başarısız
    ), patch("app.services.report_generator.build_pdf", side_effect=fake_build_pdf):
        result = await generate_report_from_template(tpl, start, end, db_session, archive.id)

    assert result.status == "completed"  # rapor düşmedi
    assert captured["grafana_charts"][0]["png"] == b""
    assert captured["grafana_charts"][0]["error"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_report_generator_grafana.py -v -n0`
Expected: FAIL — `grafana_charts` None (henüz geçirilmiyor) → `captured["grafana_charts"]` None, AssertionError.

- [ ] **Step 3: Implement integration**

`report_generator.py` üst importlara ekle:

```python
import httpx

from app.core.config import settings
from app.services.grafana_render import render_panel
```

`summary_chart = ...` satırından sonra, `# Build output` bloğundan **önce** ekle:

```python
        # --- Grafana panels (render-on-generate, hata toleranslı) ---
        grafana_charts: list[dict] = []
        panel_refs = json.loads(template.grafana_panels or "[]")
        if panel_refs:
            from_ms = int(start.timestamp() * 1000)
            to_ms = int(end.timestamp() * 1000)
            auth = render_auth_or_none()
            async with httpx.AsyncClient(
                base_url=settings.GRAFANA_URL,
                auth=auth,
                timeout=settings.GRAFANA_RENDER_TIMEOUT,
            ) as gf_http:
                for ref in panel_refs:
                    png = await render_panel(
                        dashboard_uid=ref["dashboard_uid"],
                        panel_id=ref["panel_id"],
                        from_ms=from_ms,
                        to_ms=to_ms,
                        http=gf_http,
                        width=settings.GRAFANA_RENDER_WIDTH,
                        height=settings.GRAFANA_RENDER_HEIGHT,
                    )
                    grafana_charts.append(
                        {
                            "title": ref["title"],
                            "png": png,
                            "error": None if png else "Grafana paneli render edilemedi",
                        }
                    )
```

`render_auth_or_none` için importa ekle: `from app.services.grafana_render import render_auth, render_panel` ve yukarıdaki `auth = render_auth_or_none()` satırını `auth = render_auth()` yap (Task 4'teki `render_auth()` basic-auth tuple veya None döner).

Sonra builder çağrılarına `grafana_charts` geçir:

```python
        if template.output_format == "excel":
            content = build_advanced_excel(
                archive, per_tag_data, template, summary_chart, lang=lang,
                grafana_charts=grafana_charts,
            )
            ext = "xlsx"
        elif template.output_format == "pdf":
            from app.core.config import settings as _s  # zaten settings importlu; mevcut satırı koru

            generated_at = datetime.now(UTC)
            content = build_pdf(
                archive, per_tag_data, template, settings.FACILITY_NAME, generated_at, lang=lang,
                grafana_charts=grafana_charts,
            )
            ext = "pdf"
```

> NOT: `settings` artık dosya başında importlu olduğundan PDF bloğundaki yerel `from app.core.config import settings` satırı kaldırılabilir; bırakılırsa da zarar yok. İmplementer mevcut satırı koruyup yalnız `grafana_charts=` ekleyebilir.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_report_generator_grafana.py -v -n0`
Expected: PASS (2 passed).

- [ ] **Step 5: Run full report suite (regression)**

Run: `.venv/Scripts/python -m pytest tests/test_report_generator.py tests/test_report_i18n.py -v -n0`
Expected: PASS (mevcut testler bozulmadı — boş `grafana_charts` default'u sayesinde).

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/services/report_generator.py scada-reporter/backend/tests/test_report_generator_grafana.py
git commit -m "feat(reports): render grafana panels during report generation"
```

---

### Task 8: Backend grafana router (dashboard + panel listesi)

**Files:**
- Create: `scada-reporter/backend/app/api/grafana.py`
- Modify: `scada-reporter/backend/app/main.py` (router'ı dahil et)
- Test: `scada-reporter/backend/tests/test_grafana_api.py` (create)

**Interfaces:**
- Consumes: `require_feature("grafana")`, `render_auth`/`render_headers` (Task 4), `settings`.
- Produces:
  - `GET /api/grafana/dashboards` → `[{"uid": str, "title": str}]`
  - `GET /api/grafana/dashboards/{uid}/panels` → `[{"id": int, "title": str}]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grafana_api.py
import httpx
import pytest


@pytest.mark.asyncio
async def test_list_dashboards(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search":
            return httpx.Response(200, json=[
                {"uid": "d1", "title": "Ops", "type": "dash-db"},
            ])
        return httpx.Response(404)

    import app.api.grafana as gapi
    monkeypatch.setattr(gapi, "_transport", httpx.MockTransport(handler))

    r = await client.get("/api/grafana/dashboards")
    assert r.status_code == 200, r.text
    assert r.json() == [{"uid": "d1", "title": "Ops"}]


@pytest.mark.asyncio
async def test_list_panels(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/dashboards/uid/d1":
            return httpx.Response(200, json={"dashboard": {"panels": [
                {"id": 1, "title": "Debi", "type": "timeseries"},
                {"id": 2, "title": "", "type": "row"},  # row → elenir
                {"id": 3, "title": "Basınç", "type": "stat"},
            ]}})
        return httpx.Response(404)

    import app.api.grafana as gapi
    monkeypatch.setattr(gapi, "_transport", httpx.MockTransport(handler))

    r = await client.get("/api/grafana/dashboards/d1/panels")
    assert r.status_code == 200, r.text
    assert r.json() == [{"id": 1, "title": "Debi"}, {"id": 3, "title": "Basınç"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_api.py -v -n0`
Expected: FAIL — 404 (router yok).

- [ ] **Step 3: Implement router**

```python
# app/api/grafana.py
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.api.license_guard import require_feature
from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import User
from app.services.grafana_render import render_auth, render_headers

router = APIRouter(prefix="/api/grafana", tags=["grafana"])

# Test enjeksiyonu için override edilebilir transport (prod'da None → gerçek ağ).
_transport: httpx.MockTransport | None = None


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.GRAFANA_URL,
        auth=render_auth(),
        headers=render_headers(),
        timeout=10.0,
        transport=_transport,
    )


@router.get("/dashboards")
async def list_dashboards(
    _user: User = Depends(get_current_user),
    _=Depends(require_feature("grafana")),
) -> list[dict]:
    try:
        async with _client() as http:
            r = await http.get("/api/search", params={"type": "dash-db"})
            r.raise_for_status()
            rows = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None
    return [{"uid": d["uid"], "title": d["title"]} for d in rows if d.get("uid")]


@router.get("/dashboards/{uid}/panels")
async def list_panels(
    uid: str,
    _user: User = Depends(get_current_user),
    _=Depends(require_feature("grafana")),
) -> list[dict]:
    try:
        async with _client() as http:
            r = await http.get(f"/api/dashboards/uid/{uid}")
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None
    panels = body.get("dashboard", {}).get("panels", [])
    return [
        {"id": p["id"], "title": p["title"]}
        for p in panels
        if p.get("type") != "row" and p.get("title")
    ]
```

`main.py` — diğer `app.include_router(...)` satırlarının yanına ekle:

```python
from app.api import grafana as grafana_api  # üst importlara

app.include_router(grafana_api.router)
```

> NOT: `get_current_user` import yolu projede `app.core.security`. Mevcut bir router'da (örn. `watchlist_groups.py`) hangi yoldan import edildiğini doğrula ve aynısını kullan.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_api.py -v -n0`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/grafana.py scada-reporter/backend/app/main.py scada-reporter/backend/tests/test_grafana_api.py
git commit -m "feat(api): grafana dashboard + panel list endpoints"
```

---

### Task 9: Frontend — şablon editörü panel seçimi + i18n

**Files:**
- Modify: `scada-reporter/frontend/src/pages/AdvancedReports.tsx` (veya şablon editör bileşeni — implementer dosyada doğrular)
- Modify: `scada-reporter/frontend/src/api/client.ts` (yeni helper'lar)
- Regenerate: `scada-reporter/frontend/src/api/generated/*` (`just gen-client`)
- Modify: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/advancedReports.json`

**Interfaces:**
- Consumes: `/api/grafana/dashboards`, `/api/grafana/dashboards/{uid}/panels` (Task 8); template create/update `grafana_panels` alanı (Task 2).

- [ ] **Step 1: Regenerate TS client (backend çalışırken)**

Backend'i başlat (zaten EkontBackend servisi ayakta; değilse `just run-backend`), sonra:

Run: `just gen-client`
Beklenen: `types.gen.ts` içinde `grafana_panels` ve yeni grafana endpoint'leri belirir.

- [ ] **Step 2: Add API helpers**

`client.ts` içine (mevcut `syncGrafana` yanına) ekle:

```ts
export interface GrafanaDashboardOpt { uid: string; title: string }
export interface GrafanaPanelOpt { id: number; title: string }

export const listGrafanaDashboards = () =>
  api.get<GrafanaDashboardOpt[]>(`/api/grafana/dashboards`)

export const listGrafanaPanels = (uid: string) =>
  api.get<GrafanaPanelOpt[]>(`/api/grafana/dashboards/${encodeURIComponent(uid)}/panels`)
```

> NOT: `api` nesnesinin gerçek metod imzasını (`api.get`/`api.post` dönüş tipi) mevcut `client.ts` desenine göre eşle.

- [ ] **Step 3: Add i18n keys (5 dil)**

Her `advancedReports.json`'a şu anahtarları ekle (değerler dile çevrili):

```json
"grafana_panels": "...",
"grafana_add_panel": "...",
"grafana_select_dashboard": "...",
"grafana_select_panel": "...",
"grafana_remove": "..."
```

TR örnek değerler: `"Grafana Panelleri"`, `"Panel Ekle"`, `"Dashboard seç"`, `"Panel seç"`, `"Kaldır"`.
EN: `"Grafana Panels"`, `"Add Panel"`, `"Select dashboard"`, `"Select panel"`, `"Remove"`.
(ru/de/ar için eşdeğer çeviriler.)

- [ ] **Step 4: Add editor UI section**

Şablon editör formuna "Grafana Panelleri" bölümü ekle (feature gate: yalnız lisans `grafana` özelliği açıkken göster — mevcut feature-flag deseni neyse onu kullan):
- `useQuery(['grafana-dashboards'], listGrafanaDashboards)` ile dashboard `<select>`.
- Seçili `uid` için `useQuery(['grafana-panels', uid], () => listGrafanaPanels(uid), { enabled: !!uid })`.
- "Ekle" butonu seçili `{dashboard_uid, panel_id, title}`'i form state'indeki `grafanaPanels` listesine push eder; her satır "Kaldır" ile silinir.
- Form submit payload'ına `grafana_panels: grafanaPanels` eklenir (create + update).

- [ ] **Step 5: Verify build + typecheck**

Run: `cd scada-reporter/frontend && pnpm exec tsc --noEmit`
Expected: `No errors found`.

Run: `pnpm build`
Expected: başarılı build.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/frontend/src
git commit -m "feat(frontend): grafana panel picker in report template editor"
```

---

### Task 10: Dokümantasyon + ortam örnekleri

**Files:**
- Create: `docs/grafana-report-panels.md`
- Modify: `scada-reporter/backend/.env.example`
- Modify: `CLAUDE.md` (Notes bölümüne tek satır)

**Interfaces:** yok (dokümantasyon).

- [ ] **Step 1: Write the doc**

`docs/grafana-report-panels.md` — içerik:
- Özellik özeti (şablona Grafana paneli ekleme → PDF/Excel'e gömme).
- Service-account token oluşturma adımları: Grafana → Administration → Service accounts → "Add service account" → rol **Viewer** (render yeterli) → "Add token" → kopyala.
- `.env`: `GRAFANA_SA_TOKEN=...` (boşsa `GRAFANA_USER`/`GRAFANA_PASSWORD` basic-auth fallback).
- Renderer servisi (`:8081`, `EkontRenderer`) çalışır olmalı; `custom.ini [rendering]` ayarı.
- Kısıtlar: render teması `light`, time range şablondan, panel başına ayrı aralık yok.

- [ ] **Step 2: Update `.env.example`**

`GRAFANA_PASSWORD` satırının altına ekle:

```
# Grafana panel render (raporlara gömme) — boşsa GRAFANA_USER/PASSWORD basic-auth kullanılır
GRAFANA_SA_TOKEN=
GRAFANA_RENDER_TIMEOUT=30.0
GRAFANA_RENDER_WIDTH=1000
GRAFANA_RENDER_HEIGHT=500
```

- [ ] **Step 3: Update CLAUDE.md**

`## Notes` bölümüne tek satır ekle:

```
- **Grafana panelleri raporlarda**: şablona Grafana paneli eklenebilir; rapor üretiminde `app/services/grafana_render.py` panel PNG'sini Grafana `/render`'dan çekip PDF/Excel'e gömer. Auth: `GRAFANA_SA_TOKEN` (yoksa basic-auth). Renderer servisi (`:8081`) gerekir. Detay: `docs/grafana-report-panels.md`.
```

- [ ] **Step 4: Commit**

```bash
git add docs/grafana-report-panels.md scada-reporter/backend/.env.example CLAUDE.md
git commit -m "docs: grafana report panels setup + env vars"
```

---

### Task 11: Uçtan uca doğrulama + tam test

**Files:** yok (doğrulama).

- [ ] **Step 1: Full backend suite**

Run: `cd scada-reporter/backend && just test`
Expected: tümü PASS (yeni testler + regresyon yok).

- [ ] **Step 2: Lint + types**

Run: `just check`
Expected: ruff + mypy + format temiz.

- [ ] **Step 3: Manuel smoke (opsiyonel, servisler ayaktayken)**

- Frontend → Advanced Reports → şablon oluştur, "Grafana Panelleri"nden bir panel ekle (örn. `scada-watchlist`).
- Şablonu PDF formatında çalıştır → arşivden indir → son sayfada Grafana paneli görseli görünmeli.
- Excel formatında çalıştır → "Grafana" sheet'inde görsel.

- [ ] **Step 4: Final commit (gerekirse)**

Kalan düzeltmeler varsa commit et.

---

## Self-Review Notları

- **Spec kapsamı:** Bölüm 1→Task 1/2, Bölüm 2→Task 3/4, Bölüm 3→Task 5/6/7, Bölüm 4→Task 8/9, Bölüm 5→Task 10/11. Tüm bölümler kapsandı.
- **Tip tutarlılığı:** `GrafanaPanelRef{dashboard_uid,panel_id,title}` ve `grafana_charts{title,png,error}` tüm task'larda aynı. `render_panel(...)` imzası Task 4'te tanımlı, Task 7'de aynı kullanılıyor. `render_auth()`/`render_headers()` Task 4 → Task 7/8.
- **Render auth:** SA token → Bearer header (auth=None); yoksa basic-auth tuple. Hem render servisinde hem API client'ta aynı `render_auth()`/`render_headers()`.
- **Geriye dönük uyumluluk:** builder'larda `grafana_charts` default `None`/`[]` → mevcut testler bozulmaz (Task 5/6/7 regresyon adımları).
- **DB:** migration additive `server_default="[]"`.
