# Spec 2 — Uygulama-İçi Yazma Yetenekleri

**Tarih:** 2026-06-20
**Durum:** Tasarım onaylandı, uygulama planı bekliyor
**Önkoşul:** Spec 1 (ortak `scada-core` çekirdeği + FastMCP `mcp-scada`) tamamlandı.
**Kapsam:** Okuma + uygulama-içi yazma. PLC/saha kontrolü (setpoint vb.) **kapsam dışı**.

---

## 1. Amaç ve Bağlam

Spec 1 agent-yüzlerini tek bir `scada-core` paketinde birleştirdi; ancak tüm yetenekler **salt-okunur** (`mcp-scada` kataloğundaki 10 tool `read`). Backend ise zengin bir yazma yüzeyine sahip (tag/PLC/grup/şablon/zamanlanmış/annotation/watchlist/kullanıcı CRUD) ve bunların hepsi **server-side RBAC** ile korunuyor (`require_perm`/`require_role`).

Spec 2 bu yazma yeteneklerini ortak çekirdeğe ekler ve agent CLI + MCP üzerinden, risk-katmanlı bir kapı arkasında açar. **Yeni yetkilendirme mantığı yoktur**: API tek kapıdır; `scada-core` HTTP hatalarını `Result(ok=False)`'a normalize ettiği için yetkisiz çağrı doğal olarak `error.status=403` döner.

### RBAC modeli (mevcut, değişmez)
- Roller: `admin`, `operator`, `viewer`.
- İzinler: `tag:create`, `plc:manage`, `report_template:create|edit|delete` + kullanıcı bazlı `permission_overrides`.
- `admin` tüm izinlere sahip; `operator` `report_template:delete` hariç çoğuna; `viewer` hiçbirine.

### Kapsam dışı (sonraki spec'ler)
- Spec 3: `ai_service.py` sezgisel parser yerine gerçek LLM tool-using asistanı.
- PLC/saha kontrolü.

---

## 2. Yetenek Risk Sınıflandırması

`scada_core.catalog.Capability`'deki `read_only: bool` alanı, üç-değerli bir `tier` ile değiştirilir:

```python
tier: Literal["read", "write", "destructive"] = "read"
```

- **read** — mevcut 10 salt-okunur yetenek (davranış değişmez; `read_only=True` yerine `tier="read"`).
- **write** — geri-dönüşü kolay veya kapsamlı olmayan yazmalar.
- **destructive** — kalıcı silmeler + kullanıcı yönetimi.

Tier; MCP'de tool kayıt kapısını (§4) ve CLI'de `--confirm` zorunluluğunu (§5) sürer.

---

## 3. Yeni Yazma Yetenekleri

Her yetenek `scada-core` `AsyncScadaClient`'a ince bir metod + `endpoints.py`'ye sabit + katalog girdisi olur. Backend yolları (hepsi `/api` önekli; `advanced-reports` **tire** ile):

| Alan | Yetenek | Tier | Metod & yol |
|---|---|---|---|
| **Tag** | `update_tag`* | write | PATCH `tags/{id}` |
| | `delete_tag`* | destructive | DELETE `tags/{id}` |
| | `import_csv_tags` | destructive | POST `tags/import_csv` |
| **Watchlist** | `watchlist_add` | write | POST `dashboard/watchlist/{tag_id}` |
| | `watchlist_remove` | write | DELETE `dashboard/watchlist/{tag_id}` |
| **Annotation** | `annotation_add` | write | POST `annotations/` |
| | `annotation_delete` | write | DELETE `annotations/{id}` |
| **Rapor şablonu** | `template_create` | write | POST `advanced-reports/templates` |
| | `template_update` | write | PUT `advanced-reports/templates/{id}` |
| | `template_run` | write | POST `advanced-reports/templates/{id}/run` |
| | `template_delete` | destructive | DELETE `advanced-reports/templates/{id}` |
| **Zamanlanmış** | `scheduled_create` | write | POST `advanced-reports/scheduled` |
| | `scheduled_update` | write | PUT `advanced-reports/scheduled/{id}` |
| | `scheduled_toggle` | write | PATCH `advanced-reports/scheduled/{id}/toggle` |
| | `scheduled_delete` | destructive | DELETE `advanced-reports/scheduled/{id}` |
| | `archive_delete` | destructive | DELETE `advanced-reports/archive/{id}` |
| **Grup** | `group_create` | write | POST `groups/` |
| | `group_update` | write | PATCH `groups/{id}` |
| | `group_assign` | write | POST `groups/{id}/assign` |
| | `group_unassign` | write | POST `groups/unassign` |
| | `group_delete` | destructive | DELETE `groups/{id}` |
| **PLC** | `plc_create` | write | POST `plc/` |
| | `plc_update` | write | PATCH `plc/{name}` |
| | `plc_delete` | destructive | DELETE `plc/{name}` |
| **Kullanıcı** | `user_create` | destructive | POST `users/` |
| | `user_update` | destructive | PATCH `users/{id}` |
| | `user_set_password` | destructive | POST `users/{id}/password` |
| | `user_delete` | destructive | DELETE `users/{id}` |

(*`update_tag`/`delete_tag` çekirdekte Spec 1'de zaten var — yalnız katalog girdisi + tier eklenir.)

Tam istek gövdesi şemaları (alan adları, zorunlu/opsiyonel) uygulama planında, backend Pydantic modellerine bakılarak netleştirilir.

---

## 4. MCP Açılması (env-flag kapısı)

`mcp-scada/server.py`, katalogtaki her yeteneği tier'ına göre kaydeder. Tek bir yardımcı izin verilen tier kümesini hesaplar:

```python
def _allowed_tiers() -> set[str]:
    tiers = {"read"}
    if os.environ.get("SCADA_MCP_ALLOW_WRITES") == "1":
        tiers.add("write")
        if os.environ.get("SCADA_MCP_ALLOW_DESTRUCTIVE") == "1":
            tiers.add("destructive")
    return tiers
```

- Varsayılan: yalnız `read` — **mevcut davranış korunur**, `mcp.json` değişmez.
- `SCADA_MCP_ALLOW_WRITES=1` → `write` tool'ları da kayıtlı.
- `+ SCADA_MCP_ALLOW_DESTRUCTIVE=1` → `destructive` tool'ları da kayıtlı (destructive, writes olmadan açılmaz).

Kayıt döngüsü `if cap.tier in _allowed_tiers()` ile filtrelenir. Kapalı tier'lar `list_tools`'ta görünmez; LLM onları seçemez. Tool gövdeleri yine §3'teki `call_capability` → `to_json` yolundan gider; 403 (RBAC) / 4xx'ler `{"ok": false, ...}` JSON olur. Prompts/resources değişmez.

---

## 5. CLI Komutları + Yıkıcı-İşlem Onayı

Agent CLI **tüm** tier'ları açar (CLI açıkça operatör/agent tarafından çalıştırılır). Yeni komut grupları, mevcut Click yapısına uyumlu:

- `scada watchlist add|remove <tag_id>`
- `scada annotations add|delete ...`
- `scada templates create|update|run|delete ...`
- `scada scheduled create|update|toggle|delete ...`
- `scada groups create|update|assign|unassign|delete ...`
- `scada plc create|update|delete ...`
- `scada users create|update|set-password|delete ...`
- (mevcut `scada tags create|update|delete` korunur)

**Yıkıcı-işlem koruması (zorunlu):** `destructive` tier'daki her CLI komutu, `--confirm` bayrağı **olmadan** işlemi yürütmez. Bayrak yoksa: ne yapacağını açıklayan bir JSON (`{"would": "<op>", "target": <id>, "hint": "re-run with --confirm"}`) yazdırır ve **sıfır olmayan çıkış koduyla** çıkar (gerçek çağrı yapılmaz). Bu, agent'ların kazara silmesini önler. Tüm komutlar `--json` çıktısını ve `Result.legacy()` hata zarfını korur.

---

## 6. Hata Yönetimi & Test (TDD)

- **scada-core:** her yeni client metodu için `httpx.MockTransport` ile happy-path + hata-path (403/404) testi; katalog bütünlüğü testi `tier` alanını ve geçerli değerleri doğrular.
- **MCP:** `_allowed_tiers()` ve kayıt filtresinin testleri — üç flag-kombinasyonu (varsayılan read-only; +writes; +destructive) için kayıtlı tool kümesi; bir yazma tool'unun 403'te `ok:false` döndüğü test.
- **CLI:** her yeni komut için davranış testi (`get_client` mock); yıkıcı komutun `--confirm` olmadan çağrı yapmadığı + sıfır-olmayan kod döndürdüğü, bayrakla yürüdüğü testleri.

---

## 7. Uygulama Fazları (tek plan, sıralı)

Yüzey büyük ama desen tek tip — tek spec, üç faz:

1. **Faz A — Çekirdek + tier altyapısı:** `Capability.tier` geçişi (`read_only` → `tier`), tüm yeni endpoint sabitleri + `AsyncScadaClient` metodları (+ `SyncScadaClient` otomatik kapsar), katalog girdileri. En çok iş; temel.
2. **Faz B — MCP açılması:** `_allowed_tiers()` kapısı + tier-filtreli kayıt + testleri.
3. **Faz C — CLI komutları:** yeni komut grupları + `--confirm` koruması + testleri.

---

## 8. Geriye Uyum & Riskler

| Risk | Önlem |
|---|---|
| `read_only` → `tier` geçişi mevcut katalog testlerini kırar | Mevcut 10 yeteneği `tier="read"` yap; katalog testini tier'a göre güncelle (meşru sözleşme değişikliği) |
| Varsayılan MCP'nin yanlışlıkla yazmaya açılması | Flag yoksa yalnız `read`; `mcp.json` değişmez; testle kilitlenir |
| Agent'ın kazara yıkıcı işlemi | MCP'de çift-flag kapısı; CLI'de zorunlu `--confirm` |
| Yetkisiz yazma | API'nin RBAC'ı (403); çekirdek 403'ü `Result(ok=False)` olarak yüzeyler |
| İstek gövdesi uyuşmazlığı | Plan, her metodun gövdesini backend Pydantic modeline bakarak netleştirir + MockTransport testiyle doğrular |

---

## 9. Başarı Ölçütü

- `scada-core` kataloğu `tier` ile sınıflanmış; §3'teki tüm yazma yetenekleri çekirdekte mevcut ve testli.
- MCP varsayılan salt-okunur; `SCADA_MCP_ALLOW_WRITES` / `SCADA_MCP_ALLOW_DESTRUCTIVE` ile katmanlı açılıyor; testle doğrulanmış.
- CLI tüm yazma komutlarını sunuyor; yıkıcılar `--confirm` olmadan yürümüyor.
- 403/404 yolları `ok:false` / `legacy()` zarfıyla tutarlı.
- Mevcut Spec 1 testleri (scada-core/mcp/CLI) yeşil kalır.
