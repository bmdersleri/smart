# Agent CLI + MCP Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tüm agent-yüzlerini (CLI + MCP) tek bir paylaşılan `scada-core` paketine dayandır; MCP'yi FastMCP'ye taşı, prompts+resources ekle, `mcp-db`'yi kaldır.

**Architecture:** Yeni kurulabilir `scada-core` paketi tek HTTP client + endpoint sabitleri + `Result` hata zarfı + bildirimsel yetenek kataloğu içerir. Agent CLI ve `mcp-scada` bu çekirdeğin ince sarmalayıcıları olur. MCP sunucusu tool'larını katalogdan üretir.

**Tech Stack:** Python 3.14, httpx (async + sync), `mcp` SDK (FastMCP), pytest + pytest-asyncio, uv.

## Global Constraints

- **Python sürümü:** 3.14 (proje venv'i, uv yönetimli).
- **Geriye uyum (sözleşme):** `scada ...` CLI komut arayüzü ve `--json` çıktı şekli **değişmez**. Mevcut 34 CLI testi değişiklik gerektirmeden yeşil kalmalı.
- **Kapsam:** Salt-okunur + uygulama-içi okuma. Bu spec'te **yeni yazma/PLC yeteneği yok**.
- **Hata zarfı:** Tüm çekirdek metodları `Result` döndürür; CLI eski `{error: true, status, detail}` çıktısını `Result.legacy()` üzerinden birebir üretir.
- **Endpoint sabitleri:** Hiçbir URL yolu çekirdek dışında string olarak yazılmaz; hepsi `endpoints.py`'den gelir.
- **Lint:** ruff line-length=100, mypy temiz.
- **Commit:** Her commit mesajı `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer'ı ile biter.
- **Doğrulanmış endpoint haritası** (mevcut koddaki drift düzeltilir):

  | Capability | Gerçek endpoint | Not |
  |---|---|---|
  | query_current_values | `GET api/dashboard/tags` | FIX: eski `dashboard/current-values` ucu yok |
  | query_trend | `POST api/ai/resolve` → `GET api/dashboard/trend_range` | FIX: isim→id çöz, sonra tag_ids+start+end |
  | generate_report | `POST api/ai/reports/generate` | gövde: tags(isim), start, end, format, aggregation |
  | list_tags | `GET api/tags/` | parametre yok; filtre client-side |
  | list_plcs | `GET api/plc/` | |
  | run_sql_query | `POST api/query/run` gövde `{sql, params, limit}` | FIX: eski `api/query/` + `{query}` yanlıştı |
  | detect_anomalies | `POST api/ai/anomalies` | {tag_name, window, threshold} |
  | predict_trend | `POST api/ai/predict` | {tag_name, horizon} |
  | resolve_tag | `POST api/ai/resolve` (gövde JSON listesi) | döner `{tag_ids, matched}` |
  | get_system_health | `GET health` + `GET api/plc/` + `GET api/tags/` | kompozisyon |

---

### Task 1: `scada-core` paketini iskeletle

**Files:**
- Create: `scada-reporter/packages/scada-core/pyproject.toml`
- Create: `scada-reporter/packages/scada-core/src/scada_core/__init__.py`
- Test: `scada-reporter/packages/scada-core/tests/test_smoke.py`

**Interfaces:**
- Produces: kurulabilir `scada_core` paketi; `scada_core.__version__`.

- [ ] **Step 1: pyproject.toml yaz**

```toml
[project]
name = "scada-core"
version = "0.1.0"
description = "Shared SCADA capability core for agent CLI and MCP servers"
requires-python = ">=3.14"
dependencies = ["httpx>=0.28"]

[project.optional-dependencies]
dev = ["pytest>=9", "pytest-asyncio>=1.4"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: `__init__.py` yaz**

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Smoke testi yaz**

```python
# tests/test_smoke.py
import scada_core


def test_package_imports():
    assert scada_core.__version__ == "0.1.0"
```

- [ ] **Step 4: Paketi kur ve test et**

Run: `cd scada-reporter/packages/scada-core && uv pip install -e ".[dev]" && python -m pytest tests/test_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core
git commit -m "feat(scada-core): scaffold shared capability package"
```

---

### Task 2: `endpoints.py` — doğrulanmış yol sabitleri

**Files:**
- Create: `scada-reporter/packages/scada-core/src/scada_core/endpoints.py`
- Test: `scada-reporter/packages/scada-core/tests/test_endpoints.py`

**Interfaces:**
- Produces: yol sabitleri (`AUTH_TOKEN`, `TAGS`, `TAG_READINGS`, `TAG_ITEM`, `DASHBOARD_TAGS`, `DASHBOARD_OVERVIEW`, `TREND`, `TREND_RANGE`, `PLC`, `QUERY_RUN`, `EXPLORE_SCHEMA`, `EXPLORE_SUMMARY`, `REPORTS_GENERATE`, `REPORTS_HISTORY`, `AI_ANOMALIES`, `AI_PREDICT`, `AI_RESOLVE`, `AI_REPORTS_GENERATE`, `HEALTH`).

- [ ] **Step 1: Testi yaz (drift düzeltmelerini kilitler)**

```python
# tests/test_endpoints.py
from scada_core import endpoints as ep


def test_query_run_path_is_fixed():
    # eski kod yanlışlıkla "api/query/" kullanıyordu
    assert ep.QUERY_RUN == "api/query/run"


def test_current_values_uses_dashboard_tags():
    # "dashboard/current-values" ucu yok
    assert ep.DASHBOARD_TAGS == "api/dashboard/tags"


def test_trend_range_path():
    assert ep.TREND_RANGE == "api/dashboard/trend_range"


def test_resolve_path():
    assert ep.AI_RESOLVE == "api/ai/resolve"
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_endpoints.py -v`
Expected: FAIL — `ModuleNotFoundError: scada_core.endpoints`

- [ ] **Step 3: `endpoints.py` yaz**

```python
# Tüm REST yolları — tek kaynak. Hiçbir başka modül URL stringi yazmaz.

AUTH_TOKEN = "api/auth/token"
AUTH_REGISTER = "api/auth/register"
AUTH_ME = "api/auth/me"

TAGS = "api/tags/"
TAG_ITEM = "api/tags/{tag_id}"
TAG_READINGS = "api/tags/{tag_id}/readings"

DASHBOARD_TAGS = "api/dashboard/tags"          # latest reading + quality (current values)
DASHBOARD_OVERVIEW = "api/dashboard/overview"
TREND = "api/dashboard/trend"                  # tag_ids + hours
TREND_RANGE = "api/dashboard/trend_range"      # tag_ids + start + end

PLC = "api/plc/"

QUERY_RUN = "api/query/run"                    # body {sql, params, limit}

EXPLORE_SCHEMA = "api/explore/schema"
EXPLORE_SUMMARY = "api/explore/summary"

REPORTS_GENERATE = "api/reports/generate"
REPORTS_HISTORY = "api/reports/history"

AI_ANOMALIES = "api/ai/anomalies"
AI_PREDICT = "api/ai/predict"
AI_RESOLVE = "api/ai/resolve"
AI_REPORTS_GENERATE = "api/ai/reports/generate"

HEALTH = "health"
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `python -m pytest tests/test_endpoints.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/endpoints.py scada-reporter/packages/scada-core/tests/test_endpoints.py
git commit -m "feat(scada-core): verified endpoint constants (fixes query/current/trend drift)"
```

---

### Task 3: `envelope.py` — `Result` zarfı + hata normalizasyonu

**Files:**
- Create: `scada-reporter/packages/scada-core/src/scada_core/envelope.py`
- Test: `scada-reporter/packages/scada-core/tests/test_envelope.py`

**Interfaces:**
- Produces:
  - `Result` dataclass: `ok: bool`, `data: Any = None`, `error: dict | None = None`
  - `ok(data) -> Result`
  - `fail(kind: str, detail, status: int | None = None) -> Result`
  - `from_http_error(resp: httpx.Response) -> Result`
  - `Result.legacy() -> Any` — CLI geriye-uyum: başarıda `data`, hatada `{"error": True, "status": ..., "detail": ...}`

- [ ] **Step 1: Testi yaz**

```python
# tests/test_envelope.py
import httpx
from scada_core.envelope import Result, ok, fail, from_http_error


def test_ok_wraps_data():
    r = ok({"a": 1})
    assert r.ok is True
    assert r.data == {"a": 1}
    assert r.error is None


def test_fail_sets_error():
    r = fail("connection", "refused")
    assert r.ok is False
    assert r.error == {"kind": "connection", "detail": "refused", "status": None}


def test_from_http_error_json_detail():
    resp = httpx.Response(400, json={"detail": "bad"})
    r = from_http_error(resp)
    assert r.ok is False
    assert r.error["status"] == 400
    assert r.error["detail"] == {"detail": "bad"}


def test_legacy_success_returns_data():
    assert ok([1, 2]).legacy() == [1, 2]


def test_legacy_error_shape_matches_old_cli():
    r = fail("http", "nope", status=404)
    assert r.legacy() == {"error": True, "status": 404, "detail": "nope"}
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_envelope.py -v`
Expected: FAIL — `ModuleNotFoundError: scada_core.envelope`

- [ ] **Step 3: `envelope.py` yaz**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Result:
    ok: bool
    data: Any = None
    error: dict | None = None

    def legacy(self) -> Any:
        """CLI geriye-uyum çıktısı: başarıda ham data, hatada eski hata sözlüğü."""
        if self.ok:
            return self.data
        err = self.error or {}
        return {"error": True, "status": err.get("status"), "detail": err.get("detail")}


def ok(data: Any) -> Result:
    return Result(ok=True, data=data)


def fail(kind: str, detail: Any, status: int | None = None) -> Result:
    return Result(ok=False, error={"kind": kind, "detail": detail, "status": status})


def from_http_error(resp: httpx.Response) -> Result:
    try:
        detail: Any = resp.json()
    except ValueError:
        detail = resp.text
    return Result(ok=False, error={"kind": "http", "status": resp.status_code, "detail": detail})
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `python -m pytest tests/test_envelope.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/envelope.py scada-reporter/packages/scada-core/tests/test_envelope.py
git commit -m "feat(scada-core): Result envelope with legacy CLI compatibility"
```

---

### Task 4: `AsyncScadaClient` — altyapı + basit metodlar

**Files:**
- Create: `scada-reporter/packages/scada-core/src/scada_core/client.py`
- Test: `scada-reporter/packages/scada-core/tests/test_client_basic.py`

**Interfaces:**
- Consumes: `endpoints`, `envelope.Result/ok/fail/from_http_error`
- Produces: `AsyncScadaClient`
  - `__init__(base_url: str = DEFAULT_BASE, token: str | None = None, transport: httpx.AsyncBaseTransport | None = None)`
  - `set_token(token: str) -> None`
  - `async _request(method: str, path: str, **kw) -> Result`
  - `async login(username, password) -> Result`
  - `async list_tags() -> Result`
  - `async list_plcs() -> Result`
  - `async run_sql(sql: str, params: dict | None = None, limit: int = 5000) -> Result`
  - `async detect_anomalies(tag_name, window="7d", threshold=3.0) -> Result`
  - `async predict_trend(tag_name, horizon="24h") -> Result`
  - `async generate_report(tags: list[str], start, end, fmt="excel", aggregation="raw") -> Result`
  - `async health() -> Result`
  - `async aclose() -> None`

- [ ] **Step 1: Testi yaz (httpx.MockTransport ile)**

```python
# tests/test_client_basic.py
import httpx
import pytest
from scada_core.client import AsyncScadaClient


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_list_tags_ok():
    def handler(req):
        assert req.url.path == "/api/tags/"
        return httpx.Response(200, json=[{"id": 1, "name": "PT-101"}])

    c = _client(handler)
    r = await c.list_tags()
    assert r.ok and r.data[0]["name"] == "PT-101"
    await c.aclose()


async def test_run_sql_posts_to_query_run_with_sql_field():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["body"] = req.read().decode()
        return httpx.Response(200, json={"rows": []})

    c = _client(handler)
    r = await c.run_sql("SELECT 1")
    assert r.ok
    assert seen["path"] == "/api/query/run"
    assert '"sql"' in seen["body"]   # FIX: alan adı "query" değil "sql"
    await c.aclose()


async def test_http_error_becomes_result():
    def handler(req):
        return httpx.Response(403, json={"detail": "forbidden"})

    c = _client(handler)
    r = await c.list_plcs()
    assert r.ok is False and r.error["status"] == 403
    await c.aclose()


async def test_login_sets_token():
    def handler(req):
        if req.url.path == "/api/auth/token":
            return httpx.Response(200, json={"access_token": "TK"})
        assert req.headers["Authorization"] == "Bearer TK"
        return httpx.Response(200, json=[])

    c = _client(handler)
    await c.login("admin", "x")
    r = await c.list_tags()
    assert r.ok
    await c.aclose()
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_client_basic.py -v`
Expected: FAIL — `ModuleNotFoundError: scada_core.client`

- [ ] **Step 3: `client.py` yaz**

```python
from __future__ import annotations

import os
from typing import Any

import httpx

from . import endpoints as ep
from .envelope import Result, from_http_error, ok, fail

DEFAULT_BASE = os.environ.get("SCADA_API_URL", "http://localhost:8001")


class AsyncScadaClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=30.0,
            transport=transport,
            follow_redirects=True,
        )

    def set_token(self, token: str) -> None:
        self._token = token
        self._client.headers["Authorization"] = f"Bearer {token}"

    async def _request(self, method: str, path: str, **kw: Any) -> Result:
        try:
            resp = await self._client.request(method, "/" + path.lstrip("/"), **kw)
        except httpx.HTTPError as exc:
            return fail("connection", str(exc))
        if resp.status_code >= 400:
            return from_http_error(resp)
        try:
            return ok(resp.json())
        except ValueError:
            return ok(resp.content)

    # -- Auth ----------------------------------------------------------------
    async def login(self, username: str, password: str) -> Result:
        res = await self._request(
            "POST", ep.AUTH_TOKEN, data={"username": username, "password": password}
        )
        if res.ok and isinstance(res.data, dict) and res.data.get("access_token"):
            self.set_token(res.data["access_token"])
        return res

    # -- Simple reads --------------------------------------------------------
    async def list_tags(self) -> Result:
        return await self._request("GET", ep.TAGS)

    async def list_plcs(self) -> Result:
        return await self._request("GET", ep.PLC)

    async def run_sql(self, sql: str, params: dict | None = None, limit: int = 5000) -> Result:
        return await self._request(
            "POST", ep.QUERY_RUN, json={"sql": sql, "params": params, "limit": limit}
        )

    async def detect_anomalies(
        self, tag_name: str, window: str = "7d", threshold: float = 3.0
    ) -> Result:
        return await self._request(
            "POST",
            ep.AI_ANOMALIES,
            json={"tag_name": tag_name, "window": window, "threshold": threshold},
        )

    async def predict_trend(self, tag_name: str, horizon: str = "24h") -> Result:
        return await self._request(
            "POST", ep.AI_PREDICT, json={"tag_name": tag_name, "horizon": horizon}
        )

    async def generate_report(
        self,
        tags: list[str],
        start: str,
        end: str,
        fmt: str = "excel",
        aggregation: str = "raw",
    ) -> Result:
        return await self._request(
            "POST",
            ep.AI_REPORTS_GENERATE,
            json={"tags": tags, "start": start, "end": end,
                  "format": fmt, "aggregation": aggregation},
        )

    async def health(self) -> Result:
        return await self._request("GET", ep.HEALTH)

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `python -m pytest tests/test_client_basic.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/client.py scada-reporter/packages/scada-core/tests/test_client_basic.py
git commit -m "feat(scada-core): AsyncScadaClient base + simple read methods"
```

---

### Task 5: `AsyncScadaClient` — birleşik (composed) yetenekler

**Files:**
- Modify: `scada-reporter/packages/scada-core/src/scada_core/client.py`
- Test: `scada-reporter/packages/scada-core/tests/test_client_composed.py`

**Interfaces:**
- Consumes: Task 4'teki `AsyncScadaClient._request`
- Produces (yeni metodlar):
  - `async resolve_ids(names: list[str]) -> Result` → `POST api/ai/resolve`, döner `{tag_ids, matched}`
  - `async current_values(tag_names: list[str] | None = None) -> Result` → `GET api/dashboard/tags`, opsiyonel client-side ada göre filtre
  - `async query_trend(tags: list[str], start: str, end: str) -> Result` → resolve_ids + `GET api/dashboard/trend_range`
  - `async resolve_tag(query: str) -> Result` → resolve_ids([query]) + tag detayları
  - `async system_health() -> Result` → `health` + `list_plcs` + `list_tags` kompozisyonu

- [ ] **Step 1: Testi yaz**

```python
# tests/test_client_composed.py
import httpx
from scada_core.client import AsyncScadaClient


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_query_trend_resolves_then_calls_range():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if req.url.path == "/api/ai/resolve":
            return httpx.Response(200, json={"tag_ids": [7], "matched": 1})
        if req.url.path == "/api/dashboard/trend_range":
            assert "tag_ids=7" in str(req.url)
            assert "start=" in str(req.url) and "end=" in str(req.url)
            return httpx.Response(200, json=[{"tag_id": 7, "series": []}])
        return httpx.Response(404)

    c = _client(handler)
    r = await c.query_trend(["debi"], "2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z")
    assert r.ok
    assert "/api/ai/resolve" in calls and "/api/dashboard/trend_range" in calls
    await c.aclose()


async def test_current_values_filters_by_name():
    def handler(req):
        assert req.url.path == "/api/dashboard/tags"
        return httpx.Response(200, json={"items": [
            {"name": "PT-101", "value": 1}, {"name": "FT-201", "value": 2}]})

    c = _client(handler)
    r = await c.current_values(["PT-101"])
    assert r.ok
    names = [row["name"] for row in r.data]
    assert names == ["PT-101"]
    await c.aclose()


async def test_system_health_composes_three_calls():
    def handler(req):
        if req.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if req.url.path == "/api/plc/":
            return httpx.Response(200, json=[{"id": 1}, {"id": 2}])
        if req.url.path == "/api/tags/":
            return httpx.Response(200, json=[{"id": 1}, {"id": 2}, {"id": 3}])
        return httpx.Response(404)

    c = _client(handler)
    r = await c.system_health()
    assert r.ok
    assert r.data["plc_count"] == 2
    assert r.data["tag_count"] == 3
    await c.aclose()
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_client_composed.py -v`
Expected: FAIL — `AttributeError: 'AsyncScadaClient' object has no attribute 'query_trend'`

- [ ] **Step 3: `client.py`'ye birleşik metodları ekle** (`aclose`'dan önce)

```python
    # -- Composed capabilities ----------------------------------------------
    async def resolve_ids(self, names: list[str]) -> Result:
        # /api/ai/resolve gövdesi düz JSON listesidir (descriptions: list[str])
        return await self._request("POST", ep.AI_RESOLVE, json=names)

    async def current_values(self, tag_names: list[str] | None = None) -> Result:
        res = await self._request("GET", ep.DASHBOARD_TAGS)
        if not res.ok:
            return res
        rows = res.data.get("items", res.data) if isinstance(res.data, dict) else res.data
        if tag_names:
            wanted = set(tag_names)
            rows = [r for r in rows if r.get("name") in wanted]
        return ok(rows)

    async def query_trend(self, tags: list[str], start: str, end: str) -> Result:
        resolved = await self.resolve_ids(tags)
        if not resolved.ok:
            return resolved
        tag_ids = resolved.data.get("tag_ids", [])
        if not tag_ids:
            return fail("not_found", f"No tags matched: {tags}")
        return await self._request(
            "GET", ep.TREND_RANGE,
            params={"tag_ids": tag_ids, "start": start, "end": end},
        )

    async def resolve_tag(self, query: str) -> Result:
        resolved = await self.resolve_ids([query])
        if not resolved.ok:
            return resolved
        tag_ids = set(resolved.data.get("tag_ids", []))
        listing = await self.list_tags()
        if not listing.ok:
            return listing
        matches = [t for t in listing.data if t.get("id") in tag_ids]
        return ok({"query": query, "matches": matches, "count": len(matches)})

    async def system_health(self) -> Result:
        health = await self.health()
        plcs = await self.list_plcs()
        tags = await self.list_tags()
        return ok({
            "health": health.data if health.ok else None,
            "plc_count": len(plcs.data) if plcs.ok and isinstance(plcs.data, list) else 0,
            "tag_count": len(tags.data) if tags.ok and isinstance(tags.data, list) else 0,
        })
```

`from .envelope import` satırına `fail`'in dahil olduğundan emin ol (Task 4'te eklendi).

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `python -m pytest tests/test_client_composed.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/client.py scada-reporter/packages/scada-core/tests/test_client_composed.py
git commit -m "feat(scada-core): composed capabilities (trend resolve, current-values, health)"
```

---

### Task 6: `SyncScadaClient` facade

**Files:**
- Modify: `scada-reporter/packages/scada-core/src/scada_core/client.py`
- Test: `scada-reporter/packages/scada-core/tests/test_sync_facade.py`

**Interfaces:**
- Consumes: `AsyncScadaClient`
- Produces: `SyncScadaClient` — `AsyncScadaClient`'in tüm public coroutine metodlarını senkron çağıran facade. Aynı imzalar, `Result` döndürür. `close() -> None`.

- [ ] **Step 1: Testi yaz**

```python
# tests/test_sync_facade.py
import httpx
from scada_core.client import SyncScadaClient


def test_sync_list_tags():
    def handler(req):
        return httpx.Response(200, json=[{"id": 1, "name": "PT-101"}])

    c = SyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))
    r = c.list_tags()
    assert r.ok and r.data[0]["name"] == "PT-101"
    c.close()


def test_sync_legacy_output_on_error():
    def handler(req):
        return httpx.Response(404, json={"detail": "no"})

    c = SyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))
    r = c.list_plcs()
    assert r.legacy() == {"error": True, "status": 404, "detail": {"detail": "no"}}
    c.close()
```

> Not: `MockTransport` senkron handler'ı async client'la da çalışır; facade içte `asyncio.run` kullanır.

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_sync_facade.py -v`
Expected: FAIL — `ImportError: cannot import name 'SyncScadaClient'`

- [ ] **Step 3: `client.py` sonuna `SyncScadaClient` ekle**

```python
import asyncio


class SyncScadaClient:
    """AsyncScadaClient üzerine senkron facade — CLI bunu kullanır."""

    def __init__(self, *args, **kwargs) -> None:
        self._async = AsyncScadaClient(*args, **kwargs)

    def _run(self, coro):
        return asyncio.run(coro)

    def set_token(self, token: str) -> None:
        self._async.set_token(token)

    def __getattr__(self, name: str):
        attr = getattr(self._async, name)
        if asyncio.iscoroutinefunction(attr):
            def wrapper(*a, **kw):
                return self._run(attr(*a, **kw))
            return wrapper
        return attr

    def close(self) -> None:
        self._run(self._async.aclose())
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `python -m pytest tests/test_sync_facade.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/client.py scada-reporter/packages/scada-core/tests/test_sync_facade.py
git commit -m "feat(scada-core): SyncScadaClient facade for CLI"
```

---

### Task 7: `catalog.py` — bildirimsel yetenek kataloğu

**Files:**
- Create: `scada-reporter/packages/scada-core/src/scada_core/catalog.py`
- Test: `scada-reporter/packages/scada-core/tests/test_catalog.py`

**Interfaces:**
- Consumes: `AsyncScadaClient` (handler imzası `async (client, args: dict) -> Result`)
- Produces:
  - `Capability` dataclass: `name`, `description`, `input_schema: dict`, `handler`, `read_only: bool = True`
  - `CAPABILITIES: list[Capability]` — 10 yetenek
  - `CATALOG: dict[str, Capability]`

- [ ] **Step 1: Testi yaz**

```python
# tests/test_catalog.py
import inspect
from scada_core.catalog import CAPABILITIES, CATALOG


EXPECTED = {
    "query_current_values", "query_trend", "generate_report", "list_tags",
    "list_plcs", "run_sql_query", "detect_anomalies", "predict_trend",
    "get_system_health", "resolve_tag",
}


def test_all_capabilities_present():
    assert {c.name for c in CAPABILITIES} == EXPECTED


def test_catalog_integrity():
    for cap in CAPABILITIES:
        assert cap.description.strip(), f"{cap.name} missing description"
        assert cap.input_schema.get("type") == "object", f"{cap.name} bad schema"
        assert inspect.iscoroutinefunction(cap.handler) or callable(cap.handler)


def test_lookup_by_name():
    assert CATALOG["run_sql_query"].name == "run_sql_query"
    assert CATALOG["run_sql_query"].read_only is True
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: scada_core.catalog`

- [ ] **Step 3: `catalog.py` yaz**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .client import AsyncScadaClient
from .envelope import Result

Handler = Callable[[AsyncScadaClient, dict], Awaitable[Result]]


@dataclass
class Capability:
    name: str
    description: str
    input_schema: dict
    handler: Handler
    read_only: bool = True


def _obj(props: dict, required: list[str] | None = None) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


CAPABILITIES: list[Capability] = [
    Capability(
        "query_current_values",
        "Aktif tag'lerin (veya verilen alt kümenin) en güncel okumasını döner: "
        "ad, değer, birim, zaman damgası, kalite.",
        _obj({"tag_names": {"type": "array", "items": {"type": "string"},
                            "description": "Filtrelenecek tag adları (boşsa tümü)"}}),
        lambda c, a: c.current_values(a.get("tag_names")),
    ),
    Capability(
        "query_trend",
        "Bir veya daha çok tag için bir zaman aralığında geçmiş trend verisi. "
        "Tag adları otomatik çözümlenir.",
        _obj({"tags": {"type": "array", "items": {"type": "string"}},
              "start": {"type": "string", "description": "ISO 8601 başlangıç"},
              "end": {"type": "string", "description": "ISO 8601 bitiş"}},
             ["tags", "start", "end"]),
        lambda c, a: c.query_trend(a["tags"], a["start"], a["end"]),
    ),
    Capability(
        "generate_report",
        "Veri raporu üret (excel/pdf/json/csv). Sonuç indirme URL'si döner.",
        _obj({"tags": {"type": "array", "items": {"type": "string"}},
              "start": {"type": "string"}, "end": {"type": "string"},
              "format": {"type": "string", "enum": ["excel", "pdf", "json", "csv"],
                         "default": "excel"},
              "aggregation": {"type": "string",
                              "enum": ["raw", "hourly", "daily", "monthly"],
                              "default": "raw"}},
             ["tags", "start", "end"]),
        lambda c, a: c.generate_report(a["tags"], a["start"], a["end"],
                                       a.get("format", "excel"),
                                       a.get("aggregation", "raw")),
    ),
    Capability(
        "list_tags",
        "Tüm yapılandırılmış tag'leri meta veriyle listele: ad, birim, cihaz, PLC, "
        "aktiflik, deadband.",
        _obj({}),
        lambda c, a: c.list_tags(),
    ),
    Capability(
        "list_plcs",
        "Tüm yapılandırılmış PLC'leri bağlantı durumu, IP, rack, slot ile listele.",
        _obj({}),
        lambda c, a: c.list_plcs(),
    ),
    Capability(
        "run_sql_query",
        "Zaman serisi veritabanında salt-okunur SQL çalıştır. Sadece SELECT/WITH/EXPLAIN.",
        _obj({"query": {"type": "string", "description": "SQL (SELECT/WITH/EXPLAIN)"}},
             ["query"]),
        lambda c, a: c.run_sql(a["query"]),
    ),
    Capability(
        "detect_anomalies",
        "Bir tag'in son verisinde z-score tabanlı anomali tespiti.",
        _obj({"tag_name": {"type": "string"},
              "window": {"type": "string", "default": "7d"},
              "threshold": {"type": "number", "default": 3.0}},
             ["tag_name"]),
        lambda c, a: c.detect_anomalies(a["tag_name"], a.get("window", "7d"),
                                        a.get("threshold", 3.0)),
    ),
    Capability(
        "predict_trend",
        "Lineer regresyonla bir tag için gelecek değer tahmini.",
        _obj({"tag_name": {"type": "string"},
              "horizon": {"type": "string", "default": "24h"}},
             ["tag_name"]),
        lambda c, a: c.predict_trend(a["tag_name"], a.get("horizon", "24h")),
    ),
    Capability(
        "get_system_health",
        "Genel sistem sağlığı: PLC bağlantısı, tag sayıları, DB durumu.",
        _obj({}),
        lambda c, a: c.system_health(),
    ),
    Capability(
        "resolve_tag",
        "Kısmi ada göre tag ara (fuzzy). Agent'ın tam tag adını bulması için.",
        _obj({"query": {"type": "string"}}, ["query"]),
        lambda c, a: c.resolve_tag(a["query"]),
    ),
]

CATALOG: dict[str, Capability] = {c.name: c for c in CAPABILITIES}
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/catalog.py scada-reporter/packages/scada-core/tests/test_catalog.py
git commit -m "feat(scada-core): declarative capability catalog (10 capabilities)"
```

---

### Task 8: `formatting.py` — ortak çıktı yardımcıları

**Files:**
- Create: `scada-reporter/packages/scada-core/src/scada_core/formatting.py`
- Test: `scada-reporter/packages/scada-core/tests/test_formatting.py`

**Interfaces:**
- Produces:
  - `to_json(result: Result, indent: int = 2) -> str` — `Result`'ı JSON metne çevirir (hata zarfı dahil)
  - `to_text(data: Any) -> str` — MCP tool çıktısı için kompakt JSON (repr değil)

- [ ] **Step 1: Testi yaz**

```python
# tests/test_formatting.py
import json
from scada_core.envelope import ok, fail
from scada_core.formatting import to_json, to_text


def test_to_json_success():
    s = to_json(ok({"a": 1}))
    assert json.loads(s) == {"ok": True, "data": {"a": 1}, "error": None}


def test_to_json_error():
    s = to_json(fail("http", "no", status=500))
    parsed = json.loads(s)
    assert parsed["ok"] is False and parsed["error"]["status"] == 500


def test_to_text_is_json_not_repr():
    s = to_text({"name": "PT-101"})
    assert s == '{"name": "PT-101"}'  # str()/repr değil, geçerli JSON
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_formatting.py -v`
Expected: FAIL — `ModuleNotFoundError: scada_core.formatting`

- [ ] **Step 3: `formatting.py` yaz**

```python
from __future__ import annotations

import json
from typing import Any

from .envelope import Result


def to_json(result: Result, indent: int = 2) -> str:
    return json.dumps(
        {"ok": result.ok, "data": result.data, "error": result.error},
        indent=indent, default=str, ensure_ascii=False,
    )


def to_text(data: Any) -> str:
    return json.dumps(data, default=str, ensure_ascii=False)
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `python -m pytest tests/test_formatting.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/formatting.py scada-reporter/packages/scada-core/tests/test_formatting.py
git commit -m "feat(scada-core): json/text output formatting helpers"
```

---

### Task 9: Agent CLI'yi `scada-core`'a taşı

**Files:**
- Modify: `scada-reporter/agent-harness/setup.py` (bağımlılık ekle)
- Delete: `scada-reporter/agent-harness/src/scada_reporter_cli/client.py`
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/utils/client_helper.py`
- Test: mevcut `scada-reporter/agent-harness/tests/test_cli.py` (değişmeden geçmeli)

**Interfaces:**
- Consumes: `scada_core.client.SyncScadaClient`, `scada_core.envelope.Result`
- Produces: CLI komutları `SyncScadaClient` kullanır; `Result.legacy()` ile eski çıktı korunur.

> **Önce keşfet:** `client_helper.py`'nin `ScadaClient`'ı nasıl kurduğunu ve komutların dönüş değerini nasıl yazdırdığını oku. Komutlar `client.method()` çağırıp sonucu `--json` ile `click.echo(json.dumps(...))` ediyor. Geçişte her `client.X()` çağrısının dönüşü artık `Result`; yazdırmadan önce `.legacy()` uygula (tek noktada helper ile).

- [ ] **Step 1: Karakterizasyon testini çalıştır (mevcut davranış yeşil mi)**

Run: `cd scada-reporter/agent-harness && python -m pytest tests/test_cli.py -v`
Expected: PASS (34 passed) — değişiklikten önceki taban çizgisi.

- [ ] **Step 2: `setup.py`'ye bağımlılık ekle**

`install_requires` listesine ekle:
```python
    "scada-core",
```
Ve geliştirme kurulumunu çalıştır:
Run: `cd /c/project/smart && uv pip install -e scada-reporter/packages/scada-core -e scada-reporter/agent-harness`
Expected: başarıyla kurulur.

- [ ] **Step 3: `client_helper.py`'yi `SyncScadaClient` üretecek + `.legacy()` uygulayacak şekilde güncelle**

`client_helper.py` içindeki `ScadaClient` importunu değiştir:
```python
from scada_core.client import SyncScadaClient


def get_client(...):              # mevcut imzayı koru
    client = SyncScadaClient(base_url=..., token=...)   # mevcut base_url/token mantığını koru
    return client


def unwrap(result):
    """scada_core.Result -> eski CLI çıktısı (geriye uyum)."""
    return result.legacy() if hasattr(result, "legacy") else result
```
Komut modüllerinde `client.X(...)` dönüşünü yazdırmadan önce `unwrap(...)` uygula. (Komut başına tek satır değişiklik; `commands/*.py` içinde `client.` çağrılarının döndüğü yerleri `unwrap()` ile sar.)

- [ ] **Step 4: Eski `client.py`'yi sil**

Run: `git rm scada-reporter/agent-harness/src/scada_reporter_cli/client.py`

- [ ] **Step 5: Tüm CLI testlerini çalıştır (regresyon yok)**

Run: `cd scada-reporter/agent-harness && python -m pytest tests/test_cli.py -v`
Expected: PASS (34 passed) — çıktı şekli değişmedi.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/agent-harness
git commit -m "refactor(cli): consume scada-core SyncScadaClient, drop duplicate client"
```

---

### Task 10: `mcp-scada`'yı FastMCP + katalog ile yeniden yaz

**Files:**
- Modify: `mcp-servers/mcp-scada/pyproject.toml` (scada-core bağımlılığı)
- Rewrite: `mcp-servers/mcp-scada/src/mcp_scada/server.py`
- Test: `mcp-servers/mcp-scada/tests/test_server.py`

**Interfaces:**
- Consumes: `scada_core.catalog.CATALOG`, `scada_core.client.AsyncScadaClient`, `scada_core.formatting.to_text`
- Produces: FastMCP `mcp` nesnesi; katalogdaki her capability bir tool olarak kayıtlı; paylaşılan async client lifespan.

- [ ] **Step 1: Testi yaz (katalogdan tool üretimi + çağrı)**

```python
# mcp-servers/mcp-scada/tests/test_server.py
import httpx
import pytest
from mcp_scada import server as srv
from scada_core.catalog import CATALOG


@pytest.mark.asyncio
async def test_all_catalog_tools_registered():
    tools = await srv.mcp.list_tools()
    names = {t.name for t in tools}
    assert names == set(CATALOG)


@pytest.mark.asyncio
async def test_call_tool_returns_json_text(monkeypatch):
    def handler(req):
        return httpx.Response(200, json=[{"id": 1, "name": "PT-101"}])

    monkeypatch.setattr(
        srv, "_make_client",
        lambda: __import__("scada_core.client", fromlist=["AsyncScadaClient"]).AsyncScadaClient(
            base_url="http://t", transport=httpx.MockTransport(handler)),
    )
    result = await srv.call_capability("list_tags", {})
    assert '"PT-101"' in result          # JSON, repr değil
    assert "isError" not in result


@pytest.mark.asyncio
async def test_call_tool_error_is_marked(monkeypatch):
    def handler(req):
        return httpx.Response(500, json={"detail": "boom"})

    monkeypatch.setattr(
        srv, "_make_client",
        lambda: __import__("scada_core.client", fromlist=["AsyncScadaClient"]).AsyncScadaClient(
            base_url="http://t", transport=httpx.MockTransport(handler)),
    )
    result = await srv.call_capability("list_plcs", {})
    assert '"ok": false' in result.lower()
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `cd mcp-servers/mcp-scada && python -m pytest tests/test_server.py -v`
Expected: FAIL — `AttributeError: module 'mcp_scada.server' has no attribute 'mcp'`

- [ ] **Step 3: `pyproject.toml`'a scada-core ekle**

`dependencies` listesine `"scada-core"` ekle; `[tool.pytest.ini_options]` altına `asyncio_mode = "auto"` ekle. Kur:
Run: `cd /c/project/smart && uv pip install -e scada-reporter/packages/scada-core -e mcp-servers/mcp-scada`

- [ ] **Step 4: `server.py`'yi yeniden yaz**

```python
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from scada_core.catalog import CAPABILITIES, CATALOG
from scada_core.client import AsyncScadaClient
from scada_core.formatting import to_json

SCADA_API_URL = os.environ.get("SCADA_API_URL", "http://localhost:8001")
SCADA_TOKEN = os.environ.get("SCADA_TOKEN", "") or None

mcp = FastMCP("ekont-scada")


def _make_client() -> AsyncScadaClient:
    return AsyncScadaClient(base_url=SCADA_API_URL, token=SCADA_TOKEN)


async def call_capability(name: str, args: dict) -> str:
    cap = CATALOG[name]
    client = _make_client()
    try:
        result = await cap.handler(client, args)
    finally:
        await client.aclose()
    return to_json(result)


def _register() -> None:
    for cap in CAPABILITIES:
        async def _tool(arguments: dict | None = None, _name: str = cap.name) -> str:
            return await call_capability(_name, arguments or {})

        mcp.add_tool(
            _tool, name=cap.name, description=cap.description,
        )


_register()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

> Not: FastMCP `add_tool` imzasını projedeki `mcp` SDK sürümüne göre doğrula (`Context7` ile `modelcontextprotocol/python-sdk` dokümanına bak). Şema, capability `input_schema`'sından gelir; gerekirse `add_tool(..., inputSchema=cap.input_schema)` veya eşdeğer parametre kullan.

- [ ] **Step 5: Testin geçtiğini doğrula**

Run: `cd mcp-servers/mcp-scada && python -m pytest tests/test_server.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add mcp-servers/mcp-scada
git commit -m "feat(mcp-scada): FastMCP server generated from scada-core catalog"
```

---

### Task 11: MCP prompts + resources ekle

**Files:**
- Create: `scada-reporter/packages/scada-core/src/scada_core/prompts.py`
- Modify: `mcp-servers/mcp-scada/src/mcp_scada/server.py`
- Test: `mcp-servers/mcp-scada/tests/test_prompts_resources.py`

**Interfaces:**
- Consumes: `mcp` (FastMCP), `AsyncScadaClient`
- Produces:
  - `scada_core.prompts.PROMPTS: dict[str, str]` — `analyze_tag`, `daily_report`, `system_health_check`
  - MCP resources: `scada://tags`, `scada://schema`, `scada://plcs`

- [ ] **Step 1: Testi yaz**

```python
# mcp-servers/mcp-scada/tests/test_prompts_resources.py
import pytest
from mcp_scada import server as srv


@pytest.mark.asyncio
async def test_prompts_registered():
    prompts = await srv.mcp.list_prompts()
    names = {p.name for p in prompts}
    assert {"analyze_tag", "daily_report", "system_health_check"} <= names


@pytest.mark.asyncio
async def test_resources_registered():
    resources = await srv.mcp.list_resources()
    uris = {str(r.uri) for r in resources}
    assert "scada://tags" in uris
    assert "scada://schema" in uris
    assert "scada://plcs" in uris
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `cd mcp-servers/mcp-scada && python -m pytest tests/test_prompts_resources.py -v`
Expected: FAIL — boş prompt/resource listesi.

- [ ] **Step 3: `prompts.py` yaz**

```python
PROMPTS: dict[str, str] = {
    "analyze_tag": (
        "'{tag}' tag'ini incele: önce resolve_tag ile doğrula, sonra son {window} "
        "için detect_anomalies ve predict_trend çağır, bulguları özetle."
    ),
    "daily_report": (
        "Son 24 saat için {tags} tag'lerine günlük rapor üret: query_trend ile veriyi "
        "çek, generate_report (format=excel, aggregation=hourly) ile raporla."
    ),
    "system_health_check": (
        "get_system_health çağır; PLC bağlantısı kopuk veya stale tag varsa işaretle "
        "ve list_plcs ile teşhis et."
    ),
}
```

- [ ] **Step 4: `server.py`'ye prompt + resource kaydı ekle** (`_register()` çağrısından sonra)

```python
from scada_core.prompts import PROMPTS
from scada_core import endpoints as ep


def _register_prompts() -> None:
    for pname, template in PROMPTS.items():
        @mcp.prompt(name=pname)
        def _p(_template: str = template, **kwargs) -> str:
            return _template.format(**kwargs)


def _register_resources() -> None:
    @mcp.resource("scada://tags")
    async def _tags() -> str:
        client = _make_client()
        try:
            return to_json(await client.list_tags())
        finally:
            await client.aclose()

    @mcp.resource("scada://plcs")
    async def _plcs() -> str:
        client = _make_client()
        try:
            return to_json(await client.list_plcs())
        finally:
            await client.aclose()

    @mcp.resource("scada://schema")
    async def _schema() -> str:
        client = _make_client()
        try:
            return to_json(await client._request("GET", ep.EXPLORE_SCHEMA))
        finally:
            await client.aclose()


_register_prompts()
_register_resources()
```

> Not: `@mcp.prompt`/`@mcp.resource` dekoratör imzalarını SDK sürümüne göre doğrula (Context7). Parametreli promptlarda FastMCP argümanları otomatik şemaya çevirir.

- [ ] **Step 5: Testin geçtiğini doğrula**

Run: `cd mcp-servers/mcp-scada && python -m pytest tests/test_prompts_resources.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/prompts.py mcp-servers/mcp-scada
git commit -m "feat(mcp-scada): add workflow prompts + read-only resources"
```

---

### Task 12: `mcp-db`'yi kaldır + dokümanları güncelle

**Files:**
- Delete: `mcp-servers/mcp-db/` (tüm dizin)
- Modify: `mcp.json`
- Modify: `README.md`, `TOOL.md`, `CLAUDE.md` (scada-db referansları)
- Test: `mcp-servers/mcp-scada/tests/test_mcp_config.py`

**Interfaces:**
- Produces: `mcp.json` yalnız `scada` + `filesystem` içerir; `scada-db` yok.

- [ ] **Step 1: Testi yaz**

```python
# mcp-servers/mcp-scada/tests/test_mcp_config.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_mcp_json_has_no_scada_db():
    cfg = json.loads((ROOT / "mcp.json").read_text(encoding="utf-8"))
    servers = cfg["mcpServers"]
    assert "scada-db" not in servers
    assert "scada" in servers


def test_mcp_db_dir_removed():
    assert not (ROOT / "mcp-servers" / "mcp-db").exists()
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `cd mcp-servers/mcp-scada && python -m pytest tests/test_mcp_config.py -v`
Expected: FAIL — `scada-db` hâlâ mevcut.

- [ ] **Step 3: `mcp.json`'dan `scada-db` girdisini çıkar**

`mcp.json` şu hâle gelir:
```json
{
  "mcpServers": {
    "scada": {
      "command": "uv",
      "args": ["run", "--directory", "mcp-servers/mcp-scada", "mcp-server-scada"],
      "env": {
        "SCADA_API_URL": "http://localhost:8001",
        "SCADA_TOKEN": ""
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    }
  }
}
```

- [ ] **Step 4: `mcp-db` dizinini sil ve doküman referanslarını güncelle**

Run: `git rm -r mcp-servers/mcp-db`
Sonra `README.md`, `TOOL.md`, `CLAUDE.md` içindeki `scada-db` / `mcp-db` / "Direct DB" referanslarını kaldır veya "read-only SQL artık `run_sql_query` (API) üzerinden" ifadesiyle değiştir. (`get_system_health` çıktısındaki `"mcp_servers": ["scada", "scada-db"]` listesi `ai_service.py:485`'te — onu `["scada"]` yap.)

- [ ] **Step 5: Testlerin geçtiğini doğrula**

Run: `cd mcp-servers/mcp-scada && python -m pytest tests/test_mcp_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore(mcp): remove mcp-db (read-only SQL served by API run_sql_query)"
```

---

## Final Doğrulama

- [ ] **Tüm scada-core testleri:** `cd scada-reporter/packages/scada-core && python -m pytest -v` → tümü PASS
- [ ] **Tüm MCP testleri:** `cd mcp-servers/mcp-scada && python -m pytest -v` → tümü PASS
- [ ] **CLI regresyon:** `cd scada-reporter/agent-harness && python -m pytest -v` → 34 PASS
- [ ] **Lint:** `cd /c/project/smart && just lint` (veya `ruff check`) → temiz
- [ ] **Manuel duman testi (backend açıkken):** `scada tags list --json` ve MCP `list_tags` aynı veriyi döner.

## Başarı Ölçütü (spec §8 ile)

- Tek `scada-core` paketi; CLI ve mcp-scada kendi HTTP client/endpoint kopyalarını içermez.
- MCP FastMCP üzerinde; prompts + resources dolu; hata davranışı `Result`/`ok:false` ile düzgün.
- `mcp-db` kaldırılmış; `mcp.json` tek SCADA MCP sunucusu içeriyor.
- 3 drift bug'ı (current-values, query_trend, run_sql_query) düzeltilmiş ve testle kilitlenmiş.
- CLI 34 testi + yeni scada-core/MCP testleri yeşil; dış sözleşme değişmemiş.
