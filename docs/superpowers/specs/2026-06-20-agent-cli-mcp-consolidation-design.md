# Spec 1 — Ortak Yetenek Çekirdeği + MCP Modernizasyonu

**Tarih:** 2026-06-20
**Durum:** Tasarım onaylandı, uygulama planı bekliyor
**Kapsam:** Agent CLI + MCP tarafı — birleştirme, kalite ve agent-UX temeli

---

## 1. Amaç ve Bağlam

EKONT SMART REPORT'un agent-yüzü bugün dört ayrı yerde benzer SCADA mantığını tekrar ediyor:

| Yüzey | Erişim yolu | Sorun |
|-------|-------------|-------|
| `agent-harness` (CLI) | Senkron `httpx.Client` → REST API | Kendi client + komut tanımları |
| `mcp-scada` | Async `httpx` (her çağrıda yeni client) → REST API | Ayrı client, ayrı tool tanımları, farklı hata davranışı |
| `mcp-db` | Doğrudan DB SQL (API'yi baypas) | Auth'suz paralel erişim yolu |
| `ai_service.py` | Servisleri doğrudan çağıran sezgisel parser | Bu spec'in dışında (Spec 3) |

`mcp-scada` ve agent CLI **aynı** REST endpoint'lerine iki ayrı HTTP client ile vuruyor; tool/komut açıklamaları ayrı tutuluyor; hata zarfı tutarsız (CLI `{error: true, ...}`, MCP `raise_for_status`). MCP tarafında test yok; `prompts`/`resources` boş.

Bu spec, tüm agent-yüzlerinin paylaştığı **tek bir çekirdek** kurar ve MCP sunucusunu modern, test edilmiş, keşfedilebilir hâle getirir. Yeni saha/yazma yeteneği eklemez — o Spec 2'dir. Bu, üzerine oturulacak sağlam zemindir.

### Bu spec'in dışında (sonraki spec'ler)
- **Spec 2:** Uygulama-içi yazma yetenekleri (tag/PLC config, rapor şablonu, watchlist) — RBAC kapılı.
- **Spec 3:** `ai_service.py` sezgisel parser'ı yerine gerçek LLM tool-using asistanı.
- PLC/saha kontrolü (setpoint yazma vb.) — bu projenin kapsamı dışı.

---

## 2. Mimari

Yeni kurulabilir paket: **`scada-core`** — `scada-reporter/packages/scada-core/`.

```
scada-reporter/packages/scada-core/
  pyproject.toml
  src/scada_core/
    __init__.py
    endpoints.py     # Tüm REST yol sabitleri — tek kaynak
    envelope.py      # Result zarfı {ok, data, error} + HTTP hata normalizasyonu
    client.py        # AsyncScadaClient (doğru kaynak) + SyncScadaClient facade
    catalog.py       # Bildirimsel yetenek kataloğu
    formatting.py    # Ortak JSON/tablo çıktı yardımcıları
    prompts.py       # MCP prompt tanımları
    resources.py     # MCP resource tanımları
  tests/
```

**Bağımlılık yönü:**

```
agent-harness ─┐
               ├─► scada-core ─► REST API (:8001)
mcp-scada ─────┘
```

**Geriye uyum (sözleşme):**
- `scada ...` CLI komut arayüzü ve `--json` çıktı şekli **değişmez**.
- `mcp.json` yapısı korunur (yalnız `scada-db` girdisi kaldırılır — bkz. §6).
- Mevcut 34 CLI testi geçişten sonra **yeşil kalmalı** (regresyon kanıtı).

### Async/sync köprüsü
`AsyncScadaClient` tek doğru kaynaktır. CLI senkron Click yapısını korur ve `SyncScadaClient` facade'ı üzerinden çekirdeği çağırır (facade içte `asyncio.run` / tek `httpx.Client` paylaşımı). Endpoint yolları, zarf ve hata davranışı yalnız çekirdekte tanımlanır.

---

## 3. Bileşenler

### 3.1 `endpoints.py`
Tüm REST yolları adlandırılmış sabitler olarak (ör. `TAGS = "api/tags/"`, `QUERY_RUN = "api/query/run"`). Bugün CLI `client.py` ve `mcp-scada/server.py`'de string olarak dağınık duran yollar buraya toplanır.

### 3.2 `envelope.py`
Tek normalize sonuç biçimi:

```python
@dataclass
class Result:
    ok: bool
    data: Any | None = None
    error: dict | None = None   # {status, detail, kind}
```

- HTTP başarısızlıkları (`4xx/5xx`), bağlantı hataları ve timeout'lar tek yerde `Result(ok=False, ...)`'a çevrilir.
- CLI'nin eski `{error: true, status, detail}` çıktısı bu zarftan **birebir aynı şekilde** türetilir (geriye uyum).
- MCP tarafında hatalar düzgün `isError` tool-sonucuna dönüşür; ham exception sızmaz.

### 3.3 `client.py`
`AsyncScadaClient`: auth (login/token/me), tags, dashboard (current-values/trend/overview), reports, query, explore, ai-passthrough metodları — bugün CLI `ScadaClient`'ta olan tüm yüzey, ama tek doğru kaynak ve `Result` döndürerek. `SyncScadaClient` ince facade.

### 3.4 `catalog.py` — işin kalbi
Her yetenek tek bildirim:

```python
@dataclass
class Capability:
    name: str                    # "query_trend"
    description: str             # LLM için zengin açıklama (UX hedefi)
    input_schema: dict           # JSON Schema — MCP tool + opsiyonel CLI doğrulaması
    handler: Callable            # AsyncScadaClient metodu
    read_only: bool = True       # Spec 2'de yazma yetenekleri için ayrım
```

- **MCP-scada** tool'larını bu katalogdan otomatik üretir (10 tool'u elle tanımlamak yerine).
- **Agent CLI**'nin mevcut Click komutları yapısal olarak kalır ama kendi client kopyasını silip çekirdeği çağırır; tool açıklamaları katalogdan paylaşılır.
- Mevcut 10 MCP tool'u (query_current_values, query_trend, generate_report, list_tags, list_plcs, run_sql_query, detect_anomalies, predict_trend, get_system_health, resolve_tag) katalog girdilerine birebir taşınır — davranış aynı kalır.

### 3.5 `formatting.py`
Ortak JSON / ASCII-tablo çıktı yardımcıları (CLI'nin `--json` ve insan-okunur modları için).

---

## 4. MCP Modernizasyonu

Düşük seviye `mcp.server.Server` → **`mcp.server.fastmcp.FastMCP`**:

- Yetenekler katalogdan FastMCP'ye kaydedilir; `inputSchema` ve açıklamalar tek yerden.
- **Tek paylaşılan async client** sunucu ömrü boyunca yaşar (FastMCP lifespan) — her çağrıda yeni `AsyncClient` açma israfı biter.
- **Prompts** (şu an boş → eklenir): hazır iş akışları
  - `analyze_tag` — bir tag'i anomali + trend açısından incele
  - `daily_report` — günlük özet rapor akışı
  - `system_health_check` — PLC/tag/DB sağlık taraması
- **Resources** (şu an boş → eklenir): salt-okunur bağlam
  - `scada://tags` — tag kataloğu
  - `scada://schema` — DB şeması
  - `scada://plcs` — PLC durumu
- Tool hataları düzgün `isError` sonucu olur.

---

## 5. Test Stratejisi (TDD — proje kuralı)

- **`scada-core` birim testleri:** zarf normalizasyonu (4xx/5xx/timeout), endpoint eşlemeleri, katalog bütünlüğü (her capability'nin geçerli şeması + çağrılabilir handler'ı var).
- **MCP testleri:** katalogdan tool üretimi, `call_tool` happy-path + hata-path (httpx mock), prompts/resources listeleme.
- **CLI regresyon:** mevcut 34 test çekirdeğe geçişten sonra değişiklik gerektirmeden yeşil kalmalı.
- Her yeni capability/araç için önce test yazılır.

---

## 6. mcp-db'nin kaldırılması

`mcp-db` (doğrudan-DB SQL sunucusu) **kaldırılır**:
- SQL ihtiyacı zaten `mcp-scada`'daki `run_sql_query` → API'nin read-only `/api/query/run` ucu ile karşılanıyor.
- Tek erişim yolu = API = tek auth/yetki kapısı (güvenlik + birleştirme hedefi).
- `mcp.json`'dan `scada-db` girdisi çıkar; `mcp-servers/mcp-db/` silinir.
- README/TOOL.md/CLAUDE.md referansları güncellenir.

---

## 7. Riskler ve Önlemler

| Risk | Önlem |
|------|-------|
| CLI davranış regresyonu | Mevcut 34 test değişmeden geçmeli; `--json` çıktı şekli bit-bazlı korunur |
| Async/sync köprü karmaşıklığı | Facade tek yerde; CLI'nin senkron yüzeyi dışarıdan aynı |
| FastMCP geçişinde tool şema farkı | Tool'lar katalogdan üretilir; mevcut 10 tool'un şeması birebir taşınır + testle doğrulanır |
| `mcp-db` kullananlar | run_sql_query eşdeğer; kaldırma dokümanlara işlenir |

---

## 8. Başarı Ölçütü

- Tek `scada-core` paketi; CLI ve mcp-scada kendi HTTP client/endpoint kopyalarını **içermez**.
- MCP FastMCP üzerinde; prompts + resources dolu; hata davranışı düzgün.
- `mcp-db` kaldırılmış, `mcp.json` tek SCADA MCP sunucusu içeriyor.
- CLI 34 testi + yeni scada-core/MCP testleri yeşil.
- `scada ...` ve `mcp.json` dış sözleşmesi (mcp-db hariç) değişmemiş.
