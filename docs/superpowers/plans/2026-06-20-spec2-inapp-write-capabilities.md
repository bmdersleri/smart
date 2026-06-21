# Spec 2 — In-App Write Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SCADA uygulama-içi yazma yeteneklerini (tag/watchlist/annotation/şablon/zamanlanmış/grup/PLC/kullanıcı) risk-katmanlı (read/write/destructive) olarak `scada-core`'a ekle; MCP'de env-flag arkasında, CLI'de zorunlu `--confirm` ile aç.

**Architecture:** Her yazma endpoint'i `scada-core`'da ince bir `AsyncScadaClient` metodu (`Result` döner) + bir katalog girdisi (`tier` etiketli) olur. MCP sunucusu yeni write/destructive tool'ları yalnız `SCADA_MCP_ALLOW_WRITES` / `SCADA_MCP_ALLOW_DESTRUCTIVE` env flag'leriyle kaydeder. CLI tüm yazmaları sunar; destructive komutlar `--confirm` olmadan yürümez. Yetkilendirme tamamen API'nin RBAC'ında (403 → `Result(ok=False)`).

**Tech Stack:** Python 3.14, httpx (async + sync facade), `mcp` SDK v1.28 (FastMCP), Click (CLI), pytest + pytest-asyncio, uv.

## Global Constraints

- **Python sürümü:** 3.14, uv-managed. scada-core testleri `scada-reporter/packages/scada-core` içinde; mcp-scada testleri `mcp-servers/mcp-scada` içinde; CLI testleri `scada-reporter/agent-harness` içinde çalışır. `asyncio_mode="auto"` her üçünde ayarlı (`async def test_...` dekoratör gerektirmez; mcp-scada testleri `@pytest.mark.asyncio` kullanır — mevcut desene uy).
- **Endpoint sabitleri:** Hiçbir URL yolu çekirdek dışında string yazılmaz; hepsi `endpoints.py`'den gelir. Sabitler TAM `api/...` öneki taşır; `_request` yola yalnız `"/"` ekler.
- **Hata zarfı:** Tüm yeni client metodları `Result` döner; HTTP 4xx/403/404 → `Result(ok=False)`. Çekirdekte yeni auth mantığı YOK.
- **Geriye uyum:** Spec 1 testleri (scada-core 35, mcp-scada 8, agent-harness 27) yeşil kalmalı. İki meşru sözleşme güncellemesi vardır: (1) `tier` migrasyonunun dokunduğu `test_catalog.py`'deki tek assertion (Task 1); (2) `mcp-scada/tests/test_server.py`'deki `test_all_catalog_tools_registered` — artık varsayılan kayıt yalnız **read-tier** alt kümesi olduğundan, `names == set(CATALOG)` yerine "kayıtlı isimler = read-tier capability'leri" assert eder (Task 6). Başka hiçbir test assertion'ı değişmez. `mcp.json` değişmez; varsayılan MCP salt-okunur kalır.
- **Tier değerleri:** `"read"` | `"write"` | `"destructive"`. Sınıflandırma spec §3 tablosundan birebir alınır.
- **Lint:** ruff line-length=100, mypy temiz. Pre-commit hooks aktif; reformat ederlerse yeniden stage'le.
- **Commit:** Her commit mesajı `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer'ı ile biter.
- **Backend yolları (doğrulanmış, `advanced-reports` TİRE ile):**
  - Tag import: POST `api/tags/import_csv`
  - Watchlist: POST/DELETE `api/dashboard/watchlist/{tag_id}`
  - Annotation: POST `api/annotations/`, DELETE `api/annotations/{annotation_id}`
  - Şablon: POST `api/advanced-reports/templates`, PUT/DELETE `.../templates/{template_id}`, POST `.../templates/{template_id}/run`
  - Zamanlanmış: POST `api/advanced-reports/scheduled`, PUT/DELETE `.../scheduled/{scheduled_id}`, PATCH `.../scheduled/{scheduled_id}/toggle`
  - Arşiv: DELETE `api/advanced-reports/archive/{archive_id}`
  - Grup: POST `api/groups/`, PATCH/DELETE `.../groups/{group_id}`, POST `.../groups/{group_id}/assign`, POST `api/groups/unassign`
  - PLC: POST `api/plc/` (mevcut `ep.PLC`), PATCH/DELETE `api/plc/{name}`
  - Kullanıcı: POST `api/users/`, PATCH/DELETE `.../users/{user_id}`, POST `.../users/{user_id}/password`

---

## PHASE A — Çekirdek + tier altyapısı

### Task 1: `Capability.read_only` → `tier` migrasyonu

**Files:**
- Modify: `scada-reporter/packages/scada-core/src/scada_core/catalog.py`
- Modify: `scada-reporter/packages/scada-core/tests/test_catalog.py`

**Interfaces:**
- Produces: `Capability` dataclass alanı `tier: str = "read"` (eski `read_only: bool` kaldırılır). Mevcut 10 yetenek varsayılan `tier="read"` kullanır (yapıcı çağrıları değişmez).

- [ ] **Step 1: Testi güncelle (kırmızı yap)**

`tests/test_catalog.py` içindeki `test_lookup_by_name`'de `read_only` satırını `tier`'a çevir ve tier-bütünlük kontrolü ekle:

```python
def test_lookup_by_name():
    assert CATALOG["run_sql_query"].name == "run_sql_query"
    assert CATALOG["run_sql_query"].tier == "read"


def test_all_existing_capabilities_are_read_tier():
    for cap in CAPABILITIES:
        assert cap.tier == "read"


def test_tier_values_are_valid():
    for cap in CAPABILITIES:
        assert cap.tier in {"read", "write", "destructive"}
```

`test_catalog.py`'nin üstünde `from scada_core.catalog import CAPABILITIES, CATALOG` zaten var (varsa dokunma).

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `cd scada-reporter/packages/scada-core && python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `AttributeError: 'Capability' object has no attribute 'tier'`

- [ ] **Step 3: `catalog.py`'de alanı değiştir**

`Capability` dataclass'ında:
```python
    read_only: bool = True
```
satırını şununla değiştir:
```python
    tier: str = "read"  # "read" | "write" | "destructive"
```
Başka değişiklik yok — mevcut 10 yetenek `tier`'ı vermez, varsayılan `"read"` kalır.

- [ ] **Step 4: Testin geçtiğini doğrula + tam suite**

Run: `cd scada-reporter/packages/scada-core && python -m pytest -q`
Expected: tümü PASS (35 + yeni testler).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/catalog.py scada-reporter/packages/scada-core/tests/test_catalog.py
git commit -m "refactor(scada-core): Capability.read_only -> tier (read/write/destructive)"
```

---

### Task 2: Yeni endpoint sabitleri

**Files:**
- Modify: `scada-reporter/packages/scada-core/src/scada_core/endpoints.py`
- Test: `scada-reporter/packages/scada-core/tests/test_endpoints_write.py`

**Interfaces:**
- Produces: yazma yolları sabitleri (aşağıda).

- [ ] **Step 1: Testi yaz**

```python
# tests/test_endpoints_write.py
from scada_core import endpoints as ep


def test_write_endpoint_constants():
    assert ep.TAG_IMPORT_CSV == "api/tags/import_csv"
    assert ep.WATCHLIST_ITEM == "api/dashboard/watchlist/{tag_id}"
    assert ep.ANNOTATIONS == "api/annotations/"
    assert ep.ANNOTATION_ITEM == "api/annotations/{annotation_id}"
    assert ep.ADV_TEMPLATES == "api/advanced-reports/templates"
    assert ep.ADV_TEMPLATE_ITEM == "api/advanced-reports/templates/{template_id}"
    assert ep.ADV_TEMPLATE_RUN == "api/advanced-reports/templates/{template_id}/run"
    assert ep.ADV_SCHEDULED == "api/advanced-reports/scheduled"
    assert ep.ADV_SCHEDULED_ITEM == "api/advanced-reports/scheduled/{scheduled_id}"
    assert ep.ADV_SCHEDULED_TOGGLE == "api/advanced-reports/scheduled/{scheduled_id}/toggle"
    assert ep.ADV_ARCHIVE_ITEM == "api/advanced-reports/archive/{archive_id}"
    assert ep.GROUPS == "api/groups/"
    assert ep.GROUP_ITEM == "api/groups/{group_id}"
    assert ep.GROUP_ASSIGN == "api/groups/{group_id}/assign"
    assert ep.GROUP_UNASSIGN == "api/groups/unassign"
    assert ep.PLC_ITEM == "api/plc/{name}"
    assert ep.USERS == "api/users/"
    assert ep.USER_ITEM == "api/users/{user_id}"
    assert ep.USER_PASSWORD == "api/users/{user_id}/password"
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_endpoints_write.py -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: `endpoints.py` sonuna ekle**

```python
# --- Spec 2: write endpoints ---
TAG_IMPORT_CSV = "api/tags/import_csv"

WATCHLIST_ITEM = "api/dashboard/watchlist/{tag_id}"

ANNOTATIONS = "api/annotations/"
ANNOTATION_ITEM = "api/annotations/{annotation_id}"

ADV_TEMPLATES = "api/advanced-reports/templates"
ADV_TEMPLATE_ITEM = "api/advanced-reports/templates/{template_id}"
ADV_TEMPLATE_RUN = "api/advanced-reports/templates/{template_id}/run"
ADV_SCHEDULED = "api/advanced-reports/scheduled"
ADV_SCHEDULED_ITEM = "api/advanced-reports/scheduled/{scheduled_id}"
ADV_SCHEDULED_TOGGLE = "api/advanced-reports/scheduled/{scheduled_id}/toggle"
ADV_ARCHIVE_ITEM = "api/advanced-reports/archive/{archive_id}"

GROUPS = "api/groups/"
GROUP_ITEM = "api/groups/{group_id}"
GROUP_ASSIGN = "api/groups/{group_id}/assign"
GROUP_UNASSIGN = "api/groups/unassign"

PLC_ITEM = "api/plc/{name}"

USERS = "api/users/"
USER_ITEM = "api/users/{user_id}"
USER_PASSWORD = "api/users/{user_id}/password"
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `python -m pytest tests/test_endpoints_write.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/packages/scada-core/src/scada_core/endpoints.py scada-reporter/packages/scada-core/tests/test_endpoints_write.py
git commit -m "feat(scada-core): write endpoint constants (Spec 2)"
```

---

### Task 3: Client + katalog — Tag/Watchlist/Annotation

**Files:**
- Modify: `scada-reporter/packages/scada-core/src/scada_core/client.py` (yeni metodlar `aclose`'dan önce)
- Modify: `scada-reporter/packages/scada-core/src/scada_core/catalog.py` (yeni katalog girdileri)
- Test: `scada-reporter/packages/scada-core/tests/test_writes_tag_watch_anno.py`

**Interfaces:**
- Consumes: `AsyncScadaClient._request`, `endpoints as ep`, `catalog.Capability`
- Produces (client metodları, hepsi `-> Result`):
  - `import_csv_tags(payload: dict)` → POST `ep.TAG_IMPORT_CSV`
  - `watchlist_add(tag_id: int)` → POST `ep.WATCHLIST_ITEM`
  - `watchlist_remove(tag_id: int)` → DELETE `ep.WATCHLIST_ITEM`
  - `annotation_add(ts: str, text: str, tag_id: int | None = None)` → POST `ep.ANNOTATIONS`
  - `annotation_delete(annotation_id: int)` → DELETE `ep.ANNOTATION_ITEM`
- Produces (katalog): `import_csv_tags`(destructive), `watchlist_add`/`watchlist_remove`/`annotation_add`/`annotation_delete`(write); ayrıca mevcut `update_tag`/`delete_tag` için katalog girdileri (`update_tag`=write, `delete_tag`=destructive).

- [ ] **Step 1: Testi yaz**

```python
# tests/test_writes_tag_watch_anno.py
import httpx
from scada_core.client import AsyncScadaClient
from scada_core.catalog import CATALOG


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_watchlist_add_posts_to_item_path():
    def handler(req):
        assert req.method == "POST" and req.url.path == "/api/dashboard/watchlist/5"
        return httpx.Response(201, json={"ok": True})

    c = _client(handler)
    assert (await c.watchlist_add(5)).ok
    await c.aclose()


async def test_watchlist_remove_deletes():
    def handler(req):
        assert req.method == "DELETE" and req.url.path == "/api/dashboard/watchlist/5"
        return httpx.Response(204)

    c = _client(handler)
    assert (await c.watchlist_remove(5)).ok
    await c.aclose()


async def test_annotation_add_body():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["body"] = req.read().decode()
        return httpx.Response(201, json={"id": 1})

    c = _client(handler)
    r = await c.annotation_add(ts="2026-06-20T00:00:00Z", text="note", tag_id=3)
    assert r.ok and seen["path"] == "/api/annotations/"
    assert '"text"' in seen["body"] and '"tag_id"' in seen["body"]
    await c.aclose()


async def test_annotation_delete_403_becomes_result():
    def handler(req):
        return httpx.Response(403, json={"detail": "forbidden"})

    c = _client(handler)
    r = await c.annotation_delete(9)
    assert r.ok is False and r.error["status"] == 403
    await c.aclose()


def test_catalog_tiers_for_tag_watch_anno():
    assert CATALOG["watchlist_add"].tier == "write"
    assert CATALOG["annotation_delete"].tier == "write"
    assert CATALOG["delete_tag"].tier == "destructive"
    assert CATALOG["import_csv_tags"].tier == "destructive"
    assert CATALOG["update_tag"].tier == "write"
```

- [ ] **Step 2: Testi çalıştır, başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_writes_tag_watch_anno.py -v`
Expected: FAIL.

- [ ] **Step 3: `client.py`'ye metodları ekle** (`aclose`'dan önce)

```python
    # -- Spec 2: tag / watchlist / annotation writes -----------------------
    async def import_csv_tags(self, payload: dict) -> Result:
        return await self._request("POST", ep.TAG_IMPORT_CSV, json=payload)

    async def watchlist_add(self, tag_id: int) -> Result:
        return await self._request("POST", ep.WATCHLIST_ITEM.format(tag_id=tag_id))

    async def watchlist_remove(self, tag_id: int) -> Result:
        return await self._request("DELETE", ep.WATCHLIST_ITEM.format(tag_id=tag_id))

    async def annotation_add(
        self, ts: str, text: str, tag_id: int | None = None
    ) -> Result:
        return await self._request(
            "POST", ep.ANNOTATIONS, json={"ts": ts, "text": text, "tag_id": tag_id}
        )

    async def annotation_delete(self, annotation_id: int) -> Result:
        return await self._request(
            "DELETE", ep.ANNOTATION_ITEM.format(annotation_id=annotation_id)
        )
```

- [ ] **Step 4: `catalog.py`'ye girdileri ekle** (`CAPABILITIES` listesinin sonuna, `]`'den önce)

```python
    Capability(
        "update_tag", "Bir tag'in alanlarını güncelle (unit/device/channel/alarm).",
        _obj({"tag_id": {"type": "integer"}, "unit": {"type": "string"},
              "device": {"type": "string"}, "channel": {"type": "string"},
              "description": {"type": "string"}, "min_alarm": {"type": "number"},
              "max_alarm": {"type": "number"}}, ["tag_id"]),
        lambda c, a: c.update_tag(
            a["tag_id"], a.get("unit"), a.get("device"), a.get("channel"),
            a.get("description"), a.get("min_alarm"), a.get("max_alarm")),
        tier="write",
    ),
    Capability(
        "delete_tag", "Bir tag'i kalıcı olarak sil.",
        _obj({"tag_id": {"type": "integer"}}, ["tag_id"]),
        lambda c, a: c.delete_tag(a["tag_id"]), tier="destructive",
    ),
    Capability(
        "import_csv_tags", "CSV gövdesinden toplu tag içe aktar.",
        _obj({"payload": {"type": "object"}}, ["payload"]),
        lambda c, a: c.import_csv_tags(a["payload"]), tier="destructive",
    ),
    Capability(
        "watchlist_add", "Bir tag'i izleme listesine ekle.",
        _obj({"tag_id": {"type": "integer"}}, ["tag_id"]),
        lambda c, a: c.watchlist_add(a["tag_id"]), tier="write",
    ),
    Capability(
        "watchlist_remove", "Bir tag'i izleme listesinden çıkar.",
        _obj({"tag_id": {"type": "integer"}}, ["tag_id"]),
        lambda c, a: c.watchlist_remove(a["tag_id"]), tier="write",
    ),
    Capability(
        "annotation_add", "Bir zaman damgasına (opsiyonel tag'e) not ekle.",
        _obj({"ts": {"type": "string"}, "text": {"type": "string"},
              "tag_id": {"type": "integer"}}, ["ts", "text"]),
        lambda c, a: c.annotation_add(a["ts"], a["text"], a.get("tag_id")),
        tier="write",
    ),
    Capability(
        "annotation_delete", "Bir annotation'ı sil.",
        _obj({"annotation_id": {"type": "integer"}}, ["annotation_id"]),
        lambda c, a: c.annotation_delete(a["annotation_id"]), tier="write",
    ),
```

- [ ] **Step 5: Testi + tam suite çalıştır**

Run: `python -m pytest -q`
Expected: tümü PASS.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/packages/scada-core
git commit -m "feat(scada-core): tag/watchlist/annotation write capabilities (tiered)"
```

---

### Task 4: Client + katalog — Şablon/Zamanlanmış

**Files:**
- Modify: `scada-reporter/packages/scada-core/src/scada_core/client.py`
- Modify: `scada-reporter/packages/scada-core/src/scada_core/catalog.py`
- Test: `scada-reporter/packages/scada-core/tests/test_writes_templates.py`

**Interfaces:**
- Produces (client, `-> Result`):
  - `template_create(payload: dict)` → POST `ep.ADV_TEMPLATES`
  - `template_update(template_id: int, payload: dict)` → PUT `ep.ADV_TEMPLATE_ITEM`
  - `template_run(template_id: int, start: str | None = None, end: str | None = None)` → POST `ep.ADV_TEMPLATE_RUN`
  - `template_delete(template_id: int)` → DELETE `ep.ADV_TEMPLATE_ITEM`
  - `scheduled_create(payload: dict)` → POST `ep.ADV_SCHEDULED`
  - `scheduled_update(scheduled_id: int, payload: dict)` → PUT `ep.ADV_SCHEDULED_ITEM`
  - `scheduled_toggle(scheduled_id: int)` → PATCH `ep.ADV_SCHEDULED_TOGGLE`
  - `scheduled_delete(scheduled_id: int)` → DELETE `ep.ADV_SCHEDULED_ITEM`
  - `archive_delete(archive_id: int)` → DELETE `ep.ADV_ARCHIVE_ITEM`
- Produces (katalog): `template_create`/`template_update`/`template_run`/`scheduled_create`/`scheduled_update`/`scheduled_toggle`(write); `template_delete`/`scheduled_delete`/`archive_delete`(destructive).

- [ ] **Step 1: Testi yaz**

```python
# tests/test_writes_templates.py
import httpx
from scada_core.client import AsyncScadaClient
from scada_core.catalog import CATALOG


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_template_create_posts_payload():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["body"] = req.read().decode()
        return httpx.Response(201, json={"id": 1})

    c = _client(handler)
    r = await c.template_create({"name": "T1", "tag_ids": [1, 2]})
    assert r.ok and seen["path"] == "/api/advanced-reports/templates"
    assert '"name"' in seen["body"]
    await c.aclose()


async def test_template_run_path_and_body():
    def handler(req):
        assert req.url.path == "/api/advanced-reports/templates/7/run"
        assert '"start"' in req.read().decode()
        return httpx.Response(202, json={"archive_id": 3})

    c = _client(handler)
    assert (await c.template_run(7, start="2026-06-01T00:00:00Z")).ok
    await c.aclose()


async def test_scheduled_toggle_patch():
    def handler(req):
        assert req.method == "PATCH"
        assert req.url.path == "/api/advanced-reports/scheduled/4/toggle"
        return httpx.Response(200, json={"enabled": False})

    c = _client(handler)
    assert (await c.scheduled_toggle(4)).ok
    await c.aclose()


async def test_template_delete_204():
    def handler(req):
        assert req.method == "DELETE"
        assert req.url.path == "/api/advanced-reports/templates/9"
        return httpx.Response(204)

    c = _client(handler)
    assert (await c.template_delete(9)).ok
    await c.aclose()


def test_catalog_tiers_for_templates():
    assert CATALOG["template_create"].tier == "write"
    assert CATALOG["template_run"].tier == "write"
    assert CATALOG["scheduled_toggle"].tier == "write"
    assert CATALOG["template_delete"].tier == "destructive"
    assert CATALOG["scheduled_delete"].tier == "destructive"
    assert CATALOG["archive_delete"].tier == "destructive"
```

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_writes_templates.py -v`
Expected: FAIL.

- [ ] **Step 3: `client.py`'ye metodları ekle** (`aclose`'dan önce)

```python
    # -- Spec 2: report templates / scheduled ------------------------------
    async def template_create(self, payload: dict) -> Result:
        return await self._request("POST", ep.ADV_TEMPLATES, json=payload)

    async def template_update(self, template_id: int, payload: dict) -> Result:
        return await self._request(
            "PUT", ep.ADV_TEMPLATE_ITEM.format(template_id=template_id), json=payload
        )

    async def template_run(
        self, template_id: int, start: str | None = None, end: str | None = None
    ) -> Result:
        return await self._request(
            "POST", ep.ADV_TEMPLATE_RUN.format(template_id=template_id),
            json={"start": start, "end": end},
        )

    async def template_delete(self, template_id: int) -> Result:
        return await self._request(
            "DELETE", ep.ADV_TEMPLATE_ITEM.format(template_id=template_id)
        )

    async def scheduled_create(self, payload: dict) -> Result:
        return await self._request("POST", ep.ADV_SCHEDULED, json=payload)

    async def scheduled_update(self, scheduled_id: int, payload: dict) -> Result:
        return await self._request(
            "PUT", ep.ADV_SCHEDULED_ITEM.format(scheduled_id=scheduled_id), json=payload
        )

    async def scheduled_toggle(self, scheduled_id: int) -> Result:
        return await self._request(
            "PATCH", ep.ADV_SCHEDULED_TOGGLE.format(scheduled_id=scheduled_id)
        )

    async def scheduled_delete(self, scheduled_id: int) -> Result:
        return await self._request(
            "DELETE", ep.ADV_SCHEDULED_ITEM.format(scheduled_id=scheduled_id)
        )

    async def archive_delete(self, archive_id: int) -> Result:
        return await self._request(
            "DELETE", ep.ADV_ARCHIVE_ITEM.format(archive_id=archive_id)
        )
```

- [ ] **Step 4: `catalog.py`'ye girdileri ekle** (`CAPABILITIES` sonuna)

```python
    Capability(
        "template_create", "Rapor şablonu oluştur (name + tag_ids zorunlu).",
        _obj({"payload": {"type": "object"}}, ["payload"]),
        lambda c, a: c.template_create(a["payload"]), tier="write",
    ),
    Capability(
        "template_update", "Rapor şablonunu güncelle.",
        _obj({"template_id": {"type": "integer"}, "payload": {"type": "object"}},
             ["template_id", "payload"]),
        lambda c, a: c.template_update(a["template_id"], a["payload"]), tier="write",
    ),
    Capability(
        "template_run", "Rapor şablonunu çalıştır (opsiyonel start/end).",
        _obj({"template_id": {"type": "integer"}, "start": {"type": "string"},
              "end": {"type": "string"}}, ["template_id"]),
        lambda c, a: c.template_run(a["template_id"], a.get("start"), a.get("end")),
        tier="write",
    ),
    Capability(
        "template_delete", "Rapor şablonunu sil.",
        _obj({"template_id": {"type": "integer"}}, ["template_id"]),
        lambda c, a: c.template_delete(a["template_id"]), tier="destructive",
    ),
    Capability(
        "scheduled_create", "Zamanlanmış rapor oluştur.",
        _obj({"payload": {"type": "object"}}, ["payload"]),
        lambda c, a: c.scheduled_create(a["payload"]), tier="write",
    ),
    Capability(
        "scheduled_update", "Zamanlanmış raporu güncelle.",
        _obj({"scheduled_id": {"type": "integer"}, "payload": {"type": "object"}},
             ["scheduled_id", "payload"]),
        lambda c, a: c.scheduled_update(a["scheduled_id"], a["payload"]), tier="write",
    ),
    Capability(
        "scheduled_toggle", "Zamanlanmış raporu etkinleştir/devre dışı bırak.",
        _obj({"scheduled_id": {"type": "integer"}}, ["scheduled_id"]),
        lambda c, a: c.scheduled_toggle(a["scheduled_id"]), tier="write",
    ),
    Capability(
        "scheduled_delete", "Zamanlanmış raporu sil.",
        _obj({"scheduled_id": {"type": "integer"}}, ["scheduled_id"]),
        lambda c, a: c.scheduled_delete(a["scheduled_id"]), tier="destructive",
    ),
    Capability(
        "archive_delete", "Bir arşiv kaydını sil.",
        _obj({"archive_id": {"type": "integer"}}, ["archive_id"]),
        lambda c, a: c.archive_delete(a["archive_id"]), tier="destructive",
    ),
```

- [ ] **Step 5: Tam suite**

Run: `python -m pytest -q`
Expected: tümü PASS.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/packages/scada-core
git commit -m "feat(scada-core): report template + scheduled write capabilities (tiered)"
```

---

### Task 5: Client + katalog — Grup/PLC/Kullanıcı

**Files:**
- Modify: `scada-reporter/packages/scada-core/src/scada_core/client.py`
- Modify: `scada-reporter/packages/scada-core/src/scada_core/catalog.py`
- Test: `scada-reporter/packages/scada-core/tests/test_writes_group_plc_user.py`

**Interfaces:**
- Produces (client, `-> Result`):
  - `group_create(name: str, parent_id: int | None = None, sort_order: int = 0)` → POST `ep.GROUPS`
  - `group_update(group_id: int, name=None, parent_id=None, sort_order=None)` → PATCH `ep.GROUP_ITEM` (None alanlar atlanır)
  - `group_assign(group_id: int, tag_ids: list[int])` → POST `ep.GROUP_ASSIGN`
  - `group_unassign(tag_ids: list[int])` → POST `ep.GROUP_UNASSIGN`
  - `group_delete(group_id: int)` → DELETE `ep.GROUP_ITEM`
  - `plc_create(name: str, ip: str = "", rack: int = 0, slot: int = 1)` → POST `ep.PLC`
  - `plc_update(name: str, ip: str, rack: int = 0, slot: int = 1)` → PATCH `ep.PLC_ITEM`
  - `plc_delete(name: str)` → DELETE `ep.PLC_ITEM`
  - `user_create(username, email, password, full_name="", role="operator", permission_overrides=None)` → POST `ep.USERS`
  - `user_update(user_id, email=None, full_name=None, role=None, is_active=None, permission_overrides=None)` → PATCH `ep.USER_ITEM` (None atlanır)
  - `user_set_password(user_id: int, password: str)` → POST `ep.USER_PASSWORD`
  - `user_delete(user_id: int)` → DELETE `ep.USER_ITEM`
- Produces (katalog): group_create/update/assign/unassign, plc_create/update = write; group_delete, plc_delete, user_create/update/set_password/delete = destructive.

- [ ] **Step 1: Testi yaz**

```python
# tests/test_writes_group_plc_user.py
import httpx
from scada_core.client import AsyncScadaClient
from scada_core.catalog import CATALOG


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_group_update_omits_none_fields():
    seen = {}

    def handler(req):
        seen["body"] = req.read().decode()
        assert req.url.path == "/api/groups/3"
        return httpx.Response(200, json={"id": 3})

    c = _client(handler)
    r = await c.group_update(3, name="X")
    assert r.ok
    assert '"name"' in seen["body"] and '"parent_id"' not in seen["body"]
    await c.aclose()


async def test_group_assign_body():
    def handler(req):
        assert req.url.path == "/api/groups/3/assign"
        assert '"tag_ids"' in req.read().decode()
        return httpx.Response(200, json={"assigned": 2})

    c = _client(handler)
    assert (await c.group_assign(3, [1, 2])).ok
    await c.aclose()


async def test_plc_update_patch_path():
    def handler(req):
        assert req.method == "PATCH" and req.url.path == "/api/plc/PLC1"
        return httpx.Response(200, json={"name": "PLC1"})

    c = _client(handler)
    assert (await c.plc_update("PLC1", ip="10.0.0.1")).ok
    await c.aclose()


async def test_user_create_body():
    def handler(req):
        assert req.url.path == "/api/users/"
        body = req.read().decode()
        assert '"username"' in body and '"role"' in body
        return httpx.Response(201, json={"id": 1})

    c = _client(handler)
    assert (await c.user_create("u1", "u1@x.com", "secret6")).ok
    await c.aclose()


async def test_user_delete_403():
    def handler(req):
        return httpx.Response(403, text="forbidden")

    c = _client(handler)
    r = await c.user_delete(2)
    assert r.ok is False and r.error["status"] == 403
    await c.aclose()


def test_catalog_tiers_group_plc_user():
    assert CATALOG["group_create"].tier == "write"
    assert CATALOG["plc_update"].tier == "write"
    assert CATALOG["group_delete"].tier == "destructive"
    assert CATALOG["plc_delete"].tier == "destructive"
    assert CATALOG["user_create"].tier == "destructive"
    assert CATALOG["user_delete"].tier == "destructive"
```

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_writes_group_plc_user.py -v`
Expected: FAIL.

- [ ] **Step 3: `client.py`'ye metodları ekle** (`aclose`'dan önce)

```python
    # -- Spec 2: group / plc / user writes ---------------------------------
    async def group_create(
        self, name: str, parent_id: int | None = None, sort_order: int = 0
    ) -> Result:
        return await self._request(
            "POST", ep.GROUPS,
            json={"name": name, "parent_id": parent_id, "sort_order": sort_order},
        )

    async def group_update(
        self, group_id: int, name: str | None = None,
        parent_id: int | None = None, sort_order: int | None = None,
    ) -> Result:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if sort_order is not None:
            payload["sort_order"] = sort_order
        if not payload:
            raise ValueError("group_update: at least one field required")
        return await self._request(
            "PATCH", ep.GROUP_ITEM.format(group_id=group_id), json=payload
        )

    async def group_assign(self, group_id: int, tag_ids: list[int]) -> Result:
        return await self._request(
            "POST", ep.GROUP_ASSIGN.format(group_id=group_id), json={"tag_ids": tag_ids}
        )

    async def group_unassign(self, tag_ids: list[int]) -> Result:
        return await self._request("POST", ep.GROUP_UNASSIGN, json={"tag_ids": tag_ids})

    async def group_delete(self, group_id: int) -> Result:
        return await self._request("DELETE", ep.GROUP_ITEM.format(group_id=group_id))

    async def plc_create(
        self, name: str, ip: str = "", rack: int = 0, slot: int = 1
    ) -> Result:
        return await self._request(
            "POST", ep.PLC, json={"name": name, "ip": ip, "rack": rack, "slot": slot}
        )

    async def plc_update(
        self, name: str, ip: str, rack: int = 0, slot: int = 1
    ) -> Result:
        return await self._request(
            "PATCH", ep.PLC_ITEM.format(name=name),
            json={"ip": ip, "rack": rack, "slot": slot},
        )

    async def plc_delete(self, name: str) -> Result:
        return await self._request("DELETE", ep.PLC_ITEM.format(name=name))

    async def user_create(
        self, username: str, email: str, password: str,
        full_name: str = "", role: str = "operator",
        permission_overrides: dict | None = None,
    ) -> Result:
        return await self._request(
            "POST", ep.USERS,
            json={"username": username, "email": email, "password": password,
                  "full_name": full_name, "role": role,
                  "permission_overrides": permission_overrides or {}},
        )

    async def user_update(
        self, user_id: int, email: str | None = None, full_name: str | None = None,
        role: str | None = None, is_active: bool | None = None,
        permission_overrides: dict | None = None,
    ) -> Result:
        payload: dict[str, Any] = {}
        if email is not None:
            payload["email"] = email
        if full_name is not None:
            payload["full_name"] = full_name
        if role is not None:
            payload["role"] = role
        if is_active is not None:
            payload["is_active"] = is_active
        if permission_overrides is not None:
            payload["permission_overrides"] = permission_overrides
        if not payload:
            raise ValueError("user_update: at least one field required")
        return await self._request(
            "PATCH", ep.USER_ITEM.format(user_id=user_id), json=payload
        )

    async def user_set_password(self, user_id: int, password: str) -> Result:
        return await self._request(
            "POST", ep.USER_PASSWORD.format(user_id=user_id), json={"password": password}
        )

    async def user_delete(self, user_id: int) -> Result:
        return await self._request("DELETE", ep.USER_ITEM.format(user_id=user_id))
```

- [ ] **Step 4: `catalog.py`'ye girdileri ekle** (`CAPABILITIES` sonuna)

```python
    Capability(
        "group_create", "Tag grubu oluştur.",
        _obj({"name": {"type": "string"}, "parent_id": {"type": "integer"},
              "sort_order": {"type": "integer"}}, ["name"]),
        lambda c, a: c.group_create(a["name"], a.get("parent_id"),
                                    a.get("sort_order", 0)), tier="write",
    ),
    Capability(
        "group_update", "Tag grubunu güncelle.",
        _obj({"group_id": {"type": "integer"}, "name": {"type": "string"},
              "parent_id": {"type": "integer"}, "sort_order": {"type": "integer"}},
             ["group_id"]),
        lambda c, a: c.group_update(a["group_id"], a.get("name"),
                                    a.get("parent_id"), a.get("sort_order")),
        tier="write",
    ),
    Capability(
        "group_assign", "Tag'leri bir gruba ata.",
        _obj({"group_id": {"type": "integer"},
              "tag_ids": {"type": "array", "items": {"type": "integer"}}},
             ["group_id", "tag_ids"]),
        lambda c, a: c.group_assign(a["group_id"], a["tag_ids"]), tier="write",
    ),
    Capability(
        "group_unassign", "Tag'lerin grup atamasını kaldır.",
        _obj({"tag_ids": {"type": "array", "items": {"type": "integer"}}}, ["tag_ids"]),
        lambda c, a: c.group_unassign(a["tag_ids"]), tier="write",
    ),
    Capability(
        "group_delete", "Tag grubunu sil.",
        _obj({"group_id": {"type": "integer"}}, ["group_id"]),
        lambda c, a: c.group_delete(a["group_id"]), tier="destructive",
    ),
    Capability(
        "plc_create", "PLC bağlantı yapılandırması oluştur.",
        _obj({"name": {"type": "string"}, "ip": {"type": "string"},
              "rack": {"type": "integer"}, "slot": {"type": "integer"}}, ["name"]),
        lambda c, a: c.plc_create(a["name"], a.get("ip", ""),
                                  a.get("rack", 0), a.get("slot", 1)), tier="write",
    ),
    Capability(
        "plc_update", "PLC bağlantı yapılandırmasını güncelle.",
        _obj({"name": {"type": "string"}, "ip": {"type": "string"},
              "rack": {"type": "integer"}, "slot": {"type": "integer"}}, ["name", "ip"]),
        lambda c, a: c.plc_update(a["name"], a["ip"], a.get("rack", 0),
                                  a.get("slot", 1)), tier="write",
    ),
    Capability(
        "plc_delete", "PLC yapılandırmasını sil.",
        _obj({"name": {"type": "string"}}, ["name"]),
        lambda c, a: c.plc_delete(a["name"]), tier="destructive",
    ),
    Capability(
        "user_create", "Kullanıcı oluştur (admin).",
        _obj({"username": {"type": "string"}, "email": {"type": "string"},
              "password": {"type": "string"}, "full_name": {"type": "string"},
              "role": {"type": "string"}}, ["username", "email", "password"]),
        lambda c, a: c.user_create(a["username"], a["email"], a["password"],
                                   a.get("full_name", ""), a.get("role", "operator"),
                                   a.get("permission_overrides")), tier="destructive",
    ),
    Capability(
        "user_update", "Kullanıcıyı güncelle (admin).",
        _obj({"user_id": {"type": "integer"}, "email": {"type": "string"},
              "full_name": {"type": "string"}, "role": {"type": "string"},
              "is_active": {"type": "boolean"}}, ["user_id"]),
        lambda c, a: c.user_update(a["user_id"], a.get("email"), a.get("full_name"),
                                   a.get("role"), a.get("is_active"),
                                   a.get("permission_overrides")), tier="destructive",
    ),
    Capability(
        "user_set_password", "Kullanıcı parolasını değiştir (admin).",
        _obj({"user_id": {"type": "integer"}, "password": {"type": "string"}},
             ["user_id", "password"]),
        lambda c, a: c.user_set_password(a["user_id"], a["password"]),
        tier="destructive",
    ),
    Capability(
        "user_delete", "Kullanıcıyı sil (admin).",
        _obj({"user_id": {"type": "integer"}}, ["user_id"]),
        lambda c, a: c.user_delete(a["user_id"]), tier="destructive",
    ),
```

- [ ] **Step 5: Tam suite**

Run: `python -m pytest -q`
Expected: tümü PASS.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/packages/scada-core
git commit -m "feat(scada-core): group/plc/user write capabilities (tiered)"
```

---

## PHASE B — MCP açılması (env-flag kapısı)

### Task 6: MCP write/destructive tool'ları + tier kapısı

**Files:**
- Modify: `mcp-servers/mcp-scada/src/mcp_scada/server.py`
- Test: `mcp-servers/mcp-scada/tests/test_write_gating.py`

**Interfaces:**
- Consumes: `scada_core.catalog.CATALOG` (her capability'nin `tier`'ı), mevcut `call_capability`, `_make_client`.
- Produces: `_allowed_tiers() -> set[str]`; her yeni write/destructive capability için tipli tool fonksiyonu; tier'a göre filtreli kayıt.

**Background (mevcut yapı):** `server.py`'de `_TOOL_REGISTRY` = `(fn, cap_name)` çiftleri listesi; bir döngü `mcp.add_tool(fn, name=cap_name, description=CATALOG[cap_name].description)` çağırır. Spec 2'de bu döngü `if CATALOG[cap_name].tier in _allowed_tiers()` ile filtrelenir ve registry yeni write/destructive tool fonksiyonlarıyla genişler.

- [ ] **Step 1: Testi yaz**

```python
# tests/test_write_gating.py
import importlib
import pytest


def _reload_server(monkeypatch, writes=None, destructive=None):
    if writes is None:
        monkeypatch.delenv("SCADA_MCP_ALLOW_WRITES", raising=False)
    else:
        monkeypatch.setenv("SCADA_MCP_ALLOW_WRITES", writes)
    if destructive is None:
        monkeypatch.delenv("SCADA_MCP_ALLOW_DESTRUCTIVE", raising=False)
    else:
        monkeypatch.setenv("SCADA_MCP_ALLOW_DESTRUCTIVE", destructive)
    import mcp_scada.server as srv
    return importlib.reload(srv)


@pytest.mark.asyncio
async def test_default_is_read_only(monkeypatch):
    srv = _reload_server(monkeypatch)
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "watchlist_add" not in names
    assert "delete_tag" not in names
    assert "list_tags" in names  # read tools still present


@pytest.mark.asyncio
async def test_writes_flag_enables_write_not_destructive(monkeypatch):
    srv = _reload_server(monkeypatch, writes="1")
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "watchlist_add" in names       # write
    assert "template_create" in names     # write
    assert "delete_tag" not in names      # destructive still gated
    assert "user_delete" not in names


@pytest.mark.asyncio
async def test_destructive_requires_both_flags(monkeypatch):
    srv = _reload_server(monkeypatch, writes="1", destructive="1")
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "delete_tag" in names
    assert "user_delete" in names


@pytest.mark.asyncio
async def test_destructive_alone_does_nothing(monkeypatch):
    srv = _reload_server(monkeypatch, destructive="1")  # writes not set
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "watchlist_add" not in names
    assert "delete_tag" not in names


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    yield
    import importlib
    import mcp_scada.server as srv
    monkeypatch.delenv("SCADA_MCP_ALLOW_WRITES", raising=False)
    monkeypatch.delenv("SCADA_MCP_ALLOW_DESTRUCTIVE", raising=False)
    importlib.reload(srv)
```

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `cd mcp-servers/mcp-scada && python -m pytest tests/test_write_gating.py -v`
Expected: FAIL (write tools not registered / `_allowed_tiers` yok).

- [ ] **Step 3: `server.py`'ye tier kapısı + tipli write/destructive tool fonksiyonları ekle**

`import os` ve `from scada_core.catalog import CATALOG` zaten var (yoksa ekle). `_allowed_tiers` yardımcısını ekle:

```python
def _allowed_tiers() -> set[str]:
    tiers = {"read"}
    if os.environ.get("SCADA_MCP_ALLOW_WRITES") == "1":
        tiers.add("write")
        if os.environ.get("SCADA_MCP_ALLOW_DESTRUCTIVE") == "1":
            tiers.add("destructive")
    return tiers
```

Yeni tipli tool fonksiyonlarını ekle (her biri `call_capability` üzerinden gider). Karmaşık gövdeler (`payload`) `dict` alır:

```python
async def update_tag(tag_id: int, unit: str | None = None, device: str | None = None,
                     channel: str | None = None, description: str | None = None,
                     min_alarm: float | None = None, max_alarm: float | None = None) -> str:
    return await call_capability("update_tag", {
        "tag_id": tag_id, "unit": unit, "device": device, "channel": channel,
        "description": description, "min_alarm": min_alarm, "max_alarm": max_alarm})

async def delete_tag(tag_id: int) -> str:
    return await call_capability("delete_tag", {"tag_id": tag_id})

async def import_csv_tags(payload: dict) -> str:
    return await call_capability("import_csv_tags", {"payload": payload})

async def watchlist_add(tag_id: int) -> str:
    return await call_capability("watchlist_add", {"tag_id": tag_id})

async def watchlist_remove(tag_id: int) -> str:
    return await call_capability("watchlist_remove", {"tag_id": tag_id})

async def annotation_add(ts: str, text: str, tag_id: int | None = None) -> str:
    return await call_capability("annotation_add", {"ts": ts, "text": text, "tag_id": tag_id})

async def annotation_delete(annotation_id: int) -> str:
    return await call_capability("annotation_delete", {"annotation_id": annotation_id})

async def template_create(payload: dict) -> str:
    return await call_capability("template_create", {"payload": payload})

async def template_update(template_id: int, payload: dict) -> str:
    return await call_capability("template_update", {"template_id": template_id, "payload": payload})

async def template_run(template_id: int, start: str | None = None, end: str | None = None) -> str:
    return await call_capability("template_run", {"template_id": template_id, "start": start, "end": end})

async def template_delete(template_id: int) -> str:
    return await call_capability("template_delete", {"template_id": template_id})

async def scheduled_create(payload: dict) -> str:
    return await call_capability("scheduled_create", {"payload": payload})

async def scheduled_update(scheduled_id: int, payload: dict) -> str:
    return await call_capability("scheduled_update", {"scheduled_id": scheduled_id, "payload": payload})

async def scheduled_toggle(scheduled_id: int) -> str:
    return await call_capability("scheduled_toggle", {"scheduled_id": scheduled_id})

async def scheduled_delete(scheduled_id: int) -> str:
    return await call_capability("scheduled_delete", {"scheduled_id": scheduled_id})

async def archive_delete(archive_id: int) -> str:
    return await call_capability("archive_delete", {"archive_id": archive_id})

async def group_create(name: str, parent_id: int | None = None, sort_order: int = 0) -> str:
    return await call_capability("group_create", {"name": name, "parent_id": parent_id, "sort_order": sort_order})

async def group_update(group_id: int, name: str | None = None,
                       parent_id: int | None = None, sort_order: int | None = None) -> str:
    return await call_capability("group_update", {"group_id": group_id, "name": name,
                                                  "parent_id": parent_id, "sort_order": sort_order})

async def group_assign(group_id: int, tag_ids: list[int]) -> str:
    return await call_capability("group_assign", {"group_id": group_id, "tag_ids": tag_ids})

async def group_unassign(tag_ids: list[int]) -> str:
    return await call_capability("group_unassign", {"tag_ids": tag_ids})

async def group_delete(group_id: int) -> str:
    return await call_capability("group_delete", {"group_id": group_id})

async def plc_create(name: str, ip: str = "", rack: int = 0, slot: int = 1) -> str:
    return await call_capability("plc_create", {"name": name, "ip": ip, "rack": rack, "slot": slot})

async def plc_update(name: str, ip: str, rack: int = 0, slot: int = 1) -> str:
    return await call_capability("plc_update", {"name": name, "ip": ip, "rack": rack, "slot": slot})

async def plc_delete(name: str) -> str:
    return await call_capability("plc_delete", {"name": name})

async def user_create(username: str, email: str, password: str,
                      full_name: str = "", role: str = "operator") -> str:
    return await call_capability("user_create", {"username": username, "email": email,
                                                 "password": password, "full_name": full_name, "role": role})

async def user_update(user_id: int, email: str | None = None, full_name: str | None = None,
                      role: str | None = None, is_active: bool | None = None) -> str:
    return await call_capability("user_update", {"user_id": user_id, "email": email,
                                                 "full_name": full_name, "role": role, "is_active": is_active})

async def user_set_password(user_id: int, password: str) -> str:
    return await call_capability("user_set_password", {"user_id": user_id, "password": password})

async def user_delete(user_id: int) -> str:
    return await call_capability("user_delete", {"user_id": user_id})
```

Bu fonksiyonların `(fn, "cap_name")` çiftlerini mevcut `_TOOL_REGISTRY` listesine ekle (read tool'larının yanına). Sonra kayıt döngüsünü tier'a göre filtrele:

```python
def _register() -> None:
    allowed = _allowed_tiers()
    for fn, cap_name in _TOOL_REGISTRY:
        if CATALOG[cap_name].tier in allowed:
            mcp.add_tool(fn, name=cap_name, description=CATALOG[cap_name].description)
```

> Not: `_register()` modül yükleme zamanında bir kez çağrılır; testler `importlib.reload` ile env değişiklikleri sonrası yeniden kayıt tetikler. Eğer mevcut yapı kayıt döngüsünü modül gövdesinde inline yapıyorsa, onu `_register()` fonksiyonuna sarıp en altta çağır — böylece reload doğru çalışır.

- [ ] **Step 4: Spec 1'in registration testini tier-gating'e göre güncelle**

`mcp-servers/mcp-scada/tests/test_server.py`'deki `test_all_catalog_tools_registered` artık `names == set(CATALOG)` varsayamaz (CATALOG write/destructive de içeriyor ama varsayılan kayıt yalnız read-tier). Onu read-tier alt kümesini doğrulayacak şekilde güncelle:

```python
@pytest.mark.asyncio
async def test_all_catalog_tools_registered():
    tools = await srv.mcp.list_tools()
    names = {t.name for t in tools}
    read_names = {n for n, c in CATALOG.items() if c.tier == "read"}
    assert names == read_names
```

(Test dosyasının üstünde `from scada_core.catalog import CATALOG` import'unun olduğundan emin ol; yoksa ekle. Bu, varsayılan ortamda — write flag'leri set değilken — çalışır; gating testleri ayrı `test_write_gating.py`'de.)

- [ ] **Step 5: Testi + mevcut testleri çalıştır**

Run: `cd mcp-servers/mcp-scada && python -m pytest -v`
Expected: yeni gating testleri PASS; güncellenen + diğer mevcut testler PASS (varsayılan read-only davranış korunur).

- [ ] **Step 6: Commit**

```bash
git add mcp-servers/mcp-scada
git commit -m "feat(mcp-scada): env-flag-gated write/destructive tools by capability tier"
```

---

## PHASE C — CLI komutları

### Task 7: CLI `--confirm` koruması + watchlist/annotation komutları

**Files:**
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/utils/client_helper.py` (confirm helper)
- Create: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/watchlist.py`
- Create: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/annotations.py`
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/cli.py` (komutları kaydet)
- Test: `scada-reporter/agent-harness/tests/test_cli_writes.py`

**Interfaces:**
- Consumes: `client_helper.get_client`, `unwrap` (Spec 1), `SyncScadaClient` yazma metodları.
- Produces: `require_confirm(confirm: bool, op: str, target) -> bool` yardımcısı; `watchlist` ve `annotations` komut grupları; `cli.add_command(...)` kayıtları.

**Confirm sözleşmesi:** Destructive komut `--confirm` olmadan: `{"would": "<op>", "target": <id>, "hint": "re-run with --confirm"}` JSON'unu yazdırır ve `sys.exit(2)` ile çıkar (gerçek çağrı yok).

- [ ] **Step 1: Testi yaz**

```python
# tests/test_cli_writes.py
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from scada_reporter_cli.cli import cli

runner = CliRunner()


def _mock_client():
    mc = MagicMock()
    return mc


def test_watchlist_add_calls_client():
    mc = _mock_client()
    mc.watchlist_add.return_value = {"ok": True}
    with patch("scada_reporter_cli.commands.watchlist.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["watchlist", "add", "5"])
    assert result.exit_code == 0
    mc.watchlist_add.assert_called_once_with(5)


def test_annotation_delete_requires_confirm():
    mc = _mock_client()
    with patch("scada_reporter_cli.commands.annotations.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["annotations", "delete", "9"])
    # annotation_delete is write-tier (not destructive) -> no confirm needed
    assert result.exit_code == 0
    mc.annotation_delete.assert_called_once_with(9)
```

> Not: `annotation_delete` write-tier'dır (destructive değil), bu yüzden `--confirm` gerekmez. Destructive komutların confirm davranışı Task 9'da (delete'ler) test edilir; bu task confirm yardımcısını kurar ve write-tier komutlarını doğrular.

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `cd scada-reporter/agent-harness && python -m pytest tests/test_cli_writes.py -v`
Expected: FAIL (komutlar yok).

- [ ] **Step 3: `client_helper.py`'ye confirm yardımcısını ekle**

```python
import sys
import json as _json


def require_confirm(confirm: bool, op: str, target) -> bool:
    """Destructive komut koruması. confirm yoksa JSON uyarı yazıp exit(2)."""
    if confirm:
        return True
    click.echo(_json.dumps({"would": op, "target": target,
                            "hint": "re-run with --confirm"}, ensure_ascii=False))
    sys.exit(2)
```

- [ ] **Step 4: `commands/watchlist.py` yaz**

```python
import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap


@click.group(name="watchlist")
def watchlist_cmd():
    """İzleme listesi yönetimi."""


@watchlist_cmd.command()
@click.argument("tag_id", type=int)
def add(tag_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.watchlist_add(tag_id)), default=str, ensure_ascii=False))


@watchlist_cmd.command()
@click.argument("tag_id", type=int)
def remove(tag_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.watchlist_remove(tag_id)), default=str, ensure_ascii=False))
```

- [ ] **Step 5: `commands/annotations.py` yaz**

```python
import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap


@click.group(name="annotations")
def annotations_cmd():
    """Annotation yönetimi."""


@annotations_cmd.command()
@click.option("--ts", required=True, help="ISO 8601 zaman damgası")
@click.option("--text", required=True)
@click.option("--tag-id", type=int, default=None)
def add(ts, text, tag_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.annotation_add(ts, text, tag_id)),
                          default=str, ensure_ascii=False))


@annotations_cmd.command()
@click.argument("annotation_id", type=int)
def delete(annotation_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.annotation_delete(annotation_id)),
                          default=str, ensure_ascii=False))
```

- [ ] **Step 6: `cli.py`'ye kaydet**

`cli.py`'de import ve `cli.add_command` satırlarını ekle (mevcut `add_command` bloğunun yanına):
```python
from scada_reporter_cli.commands.watchlist import watchlist_cmd
from scada_reporter_cli.commands.annotations import annotations_cmd
cli.add_command(watchlist_cmd)
cli.add_command(annotations_cmd)
```

- [ ] **Step 7: Testi + mevcut CLI suite çalıştır**

Run: `cd scada-reporter/agent-harness && python -m pytest -q`
Expected: yeni testler PASS; mevcut 27 test PASS.

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/agent-harness
git commit -m "feat(cli): watchlist + annotations commands; --confirm guard helper"
```

---

### Task 8: CLI komutları — Şablon/Zamanlanmış/Grup

**Files:**
- Create: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/templates.py`
- Create: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/scheduled.py`
- Create: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/groups.py`
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/cli.py`
- Test: `scada-reporter/agent-harness/tests/test_cli_writes_b.py`

**Interfaces:**
- Consumes: `get_client`, `unwrap`, `require_confirm`, SyncScadaClient template/scheduled/group metodları.
- Produces: `templates`, `scheduled`, `groups` komut grupları; destructive alt-komutlar (`templates delete`, `scheduled delete`, `groups delete`) `--confirm` zorunlu.

- [ ] **Step 1: Testi yaz**

```python
# tests/test_cli_writes_b.py
import json
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from scada_reporter_cli.cli import cli

runner = CliRunner()


def test_template_create_passes_payload():
    mc = MagicMock()
    mc.template_create.return_value = {"id": 1}
    with patch("scada_reporter_cli.commands.templates.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["templates", "create", "--payload",
                                     json.dumps({"name": "T", "tag_ids": [1]})])
    assert result.exit_code == 0
    mc.template_create.assert_called_once()


def test_template_delete_blocked_without_confirm():
    mc = MagicMock()
    with patch("scada_reporter_cli.commands.templates.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["templates", "delete", "9"])
    assert result.exit_code == 2
    mc.template_delete.assert_not_called()
    assert "re-run with --confirm" in result.output


def test_template_delete_runs_with_confirm():
    mc = MagicMock()
    mc.template_delete.return_value = {"ok": True}
    with patch("scada_reporter_cli.commands.templates.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["templates", "delete", "9", "--confirm"])
    assert result.exit_code == 0
    mc.template_delete.assert_called_once_with(9)


def test_group_delete_blocked_without_confirm():
    mc = MagicMock()
    with patch("scada_reporter_cli.commands.groups.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["groups", "delete", "3"])
    assert result.exit_code == 2
    mc.group_delete.assert_not_called()
```

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_cli_writes_b.py -v`
Expected: FAIL.

- [ ] **Step 3: `commands/templates.py` yaz**

```python
import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="templates")
def templates_cmd():
    """Rapor şablonu yönetimi."""


@templates_cmd.command()
@click.option("--payload", required=True, help="JSON şablon gövdesi")
def create(payload):
    client, ok = get_client()
    if not ok:
        return
    body = json.loads(payload)
    click.echo(json.dumps(unwrap(client.template_create(body)), default=str, ensure_ascii=False))


@templates_cmd.command()
@click.argument("template_id", type=int)
@click.option("--payload", required=True, help="JSON güncelleme gövdesi")
def update(template_id, payload):
    client, ok = get_client()
    if not ok:
        return
    body = json.loads(payload)
    click.echo(json.dumps(unwrap(client.template_update(template_id, body)),
                          default=str, ensure_ascii=False))


@templates_cmd.command()
@click.argument("template_id", type=int)
@click.option("--start", default=None)
@click.option("--end", default=None)
def run(template_id, start, end):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.template_run(template_id, start, end)),
                          default=str, ensure_ascii=False))


@templates_cmd.command()
@click.argument("template_id", type=int)
@click.option("--confirm", is_flag=True, default=False)
def delete(template_id, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "template_delete", template_id)
    click.echo(json.dumps(unwrap(client.template_delete(template_id)),
                          default=str, ensure_ascii=False))
```

- [ ] **Step 4: `commands/scheduled.py` yaz**

```python
import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="scheduled")
def scheduled_cmd():
    """Zamanlanmış rapor yönetimi."""


@scheduled_cmd.command()
@click.option("--payload", required=True, help="JSON zamanlanmış gövdesi")
def create(payload):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.scheduled_create(json.loads(payload))),
                          default=str, ensure_ascii=False))


@scheduled_cmd.command()
@click.argument("scheduled_id", type=int)
@click.option("--payload", required=True)
def update(scheduled_id, payload):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.scheduled_update(scheduled_id, json.loads(payload))),
                          default=str, ensure_ascii=False))


@scheduled_cmd.command()
@click.argument("scheduled_id", type=int)
def toggle(scheduled_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.scheduled_toggle(scheduled_id)),
                          default=str, ensure_ascii=False))


@scheduled_cmd.command()
@click.argument("scheduled_id", type=int)
@click.option("--confirm", is_flag=True, default=False)
def delete(scheduled_id, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "scheduled_delete", scheduled_id)
    click.echo(json.dumps(unwrap(client.scheduled_delete(scheduled_id)),
                          default=str, ensure_ascii=False))
```

- [ ] **Step 5: `commands/groups.py` yaz**

```python
import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="groups")
def groups_cmd():
    """Tag grubu yönetimi."""


@groups_cmd.command()
@click.argument("name")
@click.option("--parent-id", type=int, default=None)
@click.option("--sort-order", type=int, default=0)
def create(name, parent_id, sort_order):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.group_create(name, parent_id, sort_order)),
                          default=str, ensure_ascii=False))


@groups_cmd.command()
@click.argument("group_id", type=int)
@click.option("--name", default=None)
@click.option("--parent-id", type=int, default=None)
@click.option("--sort-order", type=int, default=None)
def update(group_id, name, parent_id, sort_order):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.group_update(group_id, name, parent_id, sort_order)),
                          default=str, ensure_ascii=False))


@groups_cmd.command()
@click.argument("group_id", type=int)
@click.option("--tag-ids", required=True, help="Virgülle ayrılmış tag id'leri")
def assign(group_id, tag_ids):
    client, ok = get_client()
    if not ok:
        return
    ids = [int(x) for x in tag_ids.split(",") if x.strip()]
    click.echo(json.dumps(unwrap(client.group_assign(group_id, ids)),
                          default=str, ensure_ascii=False))


@groups_cmd.command()
@click.option("--tag-ids", required=True, help="Virgülle ayrılmış tag id'leri")
def unassign(tag_ids):
    client, ok = get_client()
    if not ok:
        return
    ids = [int(x) for x in tag_ids.split(",") if x.strip()]
    click.echo(json.dumps(unwrap(client.group_unassign(ids)),
                          default=str, ensure_ascii=False))


@groups_cmd.command()
@click.argument("group_id", type=int)
@click.option("--confirm", is_flag=True, default=False)
def delete(group_id, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "group_delete", group_id)
    click.echo(json.dumps(unwrap(client.group_delete(group_id)),
                          default=str, ensure_ascii=False))
```

- [ ] **Step 6: `cli.py`'ye kaydet**

```python
from scada_reporter_cli.commands.templates import templates_cmd
from scada_reporter_cli.commands.scheduled import scheduled_cmd
from scada_reporter_cli.commands.groups import groups_cmd
cli.add_command(templates_cmd)
cli.add_command(scheduled_cmd)
cli.add_command(groups_cmd)
```

- [ ] **Step 7: Testi + tam CLI suite**

Run: `python -m pytest -q`
Expected: tümü PASS.

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/agent-harness
git commit -m "feat(cli): templates/scheduled/groups commands (--confirm on destructive)"
```

---

### Task 9: CLI komutları — PLC/Kullanıcı (+ tag import)

**Files:**
- Create: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/plc.py`
- Create: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/users.py`
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/cli.py`
- Test: `scada-reporter/agent-harness/tests/test_cli_writes_c.py`

**Interfaces:**
- Consumes: `get_client`, `unwrap`, `require_confirm`, SyncScadaClient plc/user metodları.
- Produces: `plc` ve `users` komut grupları; `plc delete`, `users delete` `--confirm` zorunlu.

- [ ] **Step 1: Testi yaz**

```python
# tests/test_cli_writes_c.py
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from scada_reporter_cli.cli import cli

runner = CliRunner()


def test_plc_create_calls_client():
    mc = MagicMock()
    mc.plc_create.return_value = {"name": "PLC1"}
    with patch("scada_reporter_cli.commands.plc.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["plc", "create", "PLC1", "--ip", "10.0.0.1"])
    assert result.exit_code == 0
    mc.plc_create.assert_called_once()


def test_plc_delete_requires_confirm():
    mc = MagicMock()
    with patch("scada_reporter_cli.commands.plc.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["plc", "delete", "PLC1"])
    assert result.exit_code == 2
    mc.plc_delete.assert_not_called()


def test_user_delete_runs_with_confirm():
    mc = MagicMock()
    mc.user_delete.return_value = {"ok": True}
    with patch("scada_reporter_cli.commands.users.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["users", "delete", "2", "--confirm"])
    assert result.exit_code == 0
    mc.user_delete.assert_called_once_with(2)
```

- [ ] **Step 2: Başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_cli_writes_c.py -v`
Expected: FAIL.

- [ ] **Step 3: `commands/plc.py` yaz**

```python
import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="plc")
def plc_cmd():
    """PLC bağlantı yapılandırması yönetimi."""


@plc_cmd.command()
@click.argument("name")
@click.option("--ip", default="")
@click.option("--rack", type=int, default=0)
@click.option("--slot", type=int, default=1)
def create(name, ip, rack, slot):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.plc_create(name, ip, rack, slot)),
                          default=str, ensure_ascii=False))


@plc_cmd.command()
@click.argument("name")
@click.option("--ip", required=True)
@click.option("--rack", type=int, default=0)
@click.option("--slot", type=int, default=1)
def update(name, ip, rack, slot):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.plc_update(name, ip, rack, slot)),
                          default=str, ensure_ascii=False))


@plc_cmd.command()
@click.argument("name")
@click.option("--confirm", is_flag=True, default=False)
def delete(name, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "plc_delete", name)
    click.echo(json.dumps(unwrap(client.plc_delete(name)), default=str, ensure_ascii=False))
```

- [ ] **Step 4: `commands/users.py` yaz**

```python
import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="users")
def users_cmd():
    """Kullanıcı yönetimi (admin)."""


@users_cmd.command()
@click.argument("username")
@click.option("--email", required=True)
@click.option("--password", required=True)
@click.option("--full-name", default="")
@click.option("--role", default="operator")
def create(username, email, password, full_name, role):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.user_create(username, email, password, full_name, role)),
                          default=str, ensure_ascii=False))


@users_cmd.command()
@click.argument("user_id", type=int)
@click.option("--email", default=None)
@click.option("--full-name", default=None)
@click.option("--role", default=None)
@click.option("--is-active", type=bool, default=None)
def update(user_id, email, full_name, role, is_active):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.user_update(user_id, email, full_name, role, is_active)),
                          default=str, ensure_ascii=False))


@users_cmd.command(name="set-password")
@click.argument("user_id", type=int)
@click.option("--password", required=True)
def set_password(user_id, password):
    client, ok = get_client()
    if not ok:
        return
    click.echo(json.dumps(unwrap(client.user_set_password(user_id, password)),
                          default=str, ensure_ascii=False))


@users_cmd.command()
@click.argument("user_id", type=int)
@click.option("--confirm", is_flag=True, default=False)
def delete(user_id, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "user_delete", user_id)
    click.echo(json.dumps(unwrap(client.user_delete(user_id)), default=str, ensure_ascii=False))
```

- [ ] **Step 5: `cli.py`'ye kaydet**

```python
from scada_reporter_cli.commands.plc import plc_cmd
from scada_reporter_cli.commands.users import users_cmd
cli.add_command(plc_cmd)
cli.add_command(users_cmd)
```

- [ ] **Step 6: Testi + tam CLI suite**

Run: `python -m pytest -q`
Expected: tümü PASS.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/agent-harness
git commit -m "feat(cli): plc + users commands (--confirm on destructive)"
```

---

## Final Doğrulama

- [ ] **scada-core:** `cd scada-reporter/packages/scada-core && python -m pytest -q` → tümü PASS (35 + yeni write testleri).
- [ ] **mcp-scada:** `cd mcp-servers/mcp-scada && python -m pytest -q` → tümü PASS (8 + gating testleri); varsayılan read-only doğrulanmış.
- [ ] **agent-harness:** `cd scada-reporter/agent-harness && python -m pytest -q` → tümü PASS (27 + write komut testleri).
- [ ] **Lint:** `ruff check` üç pakette de temiz.
- [ ] **Manuel duman (backend açıkken, admin token):** `scada plc create TEST --ip 1.2.3.4` → 201/JSON; `scada plc delete TEST` → exit 2 + uyarı; `scada plc delete TEST --confirm` → 204/JSON.

## Başarı Ölçütü (spec §9)

- Katalog `tier` ile sınıflanmış; §3'teki tüm yazma yetenekleri çekirdekte mevcut ve testli.
- MCP varsayılan salt-okunur; `SCADA_MCP_ALLOW_WRITES`/`SCADA_MCP_ALLOW_DESTRUCTIVE` ile katmanlı; testle doğrulanmış.
- CLI tüm yazma komutlarını sunuyor; yıkıcılar `--confirm` olmadan yürümüyor (exit 2).
- 403/404 yolları `ok:false`/`legacy()` ile tutarlı.
- Spec 1 testleri (scada-core/mcp/CLI) yeşil.
