# Watchlist Grupları + Grafana Entegrasyonu — Tasarım

**Tarih:** 2026-06-22
**Durum:** Onaylandı (tasarım)
**Kapsam:** Backend (model + migration + API), Frontend (WatchlistTab), Grafana (templated dashboard + grup-başına üretilen dashboard'lar, manuel senkron).

---

## 1. Amaç

Dashboard watchlist'teki tag'ler kullanıcı tarafından **gruplara** ayrılabilsin. Gruplar oluşturulabilsin / yeniden adlandırılabilsin / silinebilsin; tag'ler gruplara eklenip çıkarılabilsin. Her grup Grafana'da:
- (a) tek bir **templated dashboard** içinde "Grup" açılır menüsüyle, ve
- (b) **grup başına üretilen ayrı bir dashboard** olarak

takip edilebilsin. Grup başına dashboard'lar **manuel "Grafana'ya senkronla"** butonuyla yazılır.

Mevcut sistem: `watchlists(user_id, tag_id)` düz, per-user liste. Grafana native binary olarak çalışıyor (bkz. `native-monitoring-stack` hafızası); SCADA tag değerleri `frser-sqlite-datasource` (uid `scadadb`) ile `tag_readings`'ten okunuyor. Bu tasarım onun üstüne kuruluyor.

---

## 2. Veri modeli

İki yeni tablo. Mevcut `watchlists` tablosu **değişmeden korunur** — "tag bu kullanıcının watchlist'inde mi" gerçeği orada kalır; gruplar bunun üstünde bir organizasyon katmanıdır.

### `watchlist_groups`
| kolon | tip | not |
|---|---|---|
| id | int PK | |
| user_id | int FK users(id) ON DELETE CASCADE, indexed, not null | per-user |
| name | str(255) not null | |
| sort_order | int default 0 | UI sıralaması |
| created_at | datetime default now(UTC) | |

`UNIQUE(user_id, name)` — aynı kullanıcıda aynı isimde iki grup olamaz.

### `watchlist_group_members`
| kolon | tip | not |
|---|---|---|
| id | int PK | |
| group_id | int FK watchlist_groups(id) ON DELETE CASCADE, indexed, not null | |
| tag_id | int FK tags(id) ON DELETE CASCADE, not null | |

`UNIQUE(group_id, tag_id)` — bir tag bir grupta en fazla bir kez. M:N: aynı tag birden çok grupta olabilir (grup kullanıcısı `group.user_id` ile örtük).

### Kurallar / kenar durumlar
- **"Gruplanmamış"**: kullanıcının watchlist'inde olup (`watchlists`) hiçbir grubunun üyesi olmayan tag'ler. Sanal kategori (tablo değil); `GET` yanıtında türetilir.
- **Watchlist'ten tag çıkınca**: `remove_watchlist` artık aynı işlemde o kullanıcının gruplarındaki o tag üyeliklerini de siler (app-level; FK `tags`'a olduğu için watchlist satırı silinince otomatik düşmez).
- **Gruba tag ekleme önkoşulu**: tag, kullanıcının `watchlists`'inde olmalı (404/400 değilse). UI yalnız watchlist tag'lerini gruplamaya izin verir; API de doğrular.
- **Grup silme**: üyelikler cascade ile silinir; tag'ler watchlist'te kalır.

---

## 3. Backend API

Router prefix: `/api/dashboard/watchlist-groups` (mevcut dashboard router'ına eklenir veya ayrı router; ayrı `app/api/watchlist_groups.py` tercih). Tümü `get_current_user` ile, yalnız çağıranın kendi grupları.

| Method | Path | Gövde | Yanıt |
|---|---|---|---|
| GET | `/` | — | Zarf: `{groups:[{id, name, sort_order, tag_count, tags:[{tag_id, name}]}], ungrouped:[{tag_id, name}]}` |
| POST | `/` | `{name}` | 201 `{id, name, ...}` (dup isim → 409) |
| PATCH | `/{id}` | `{name}` | 200 `{id, name}` (yoksa 404, dup → 409) |
| DELETE | `/{id}` | — | 204 |
| POST | `/{id}/tags/{tag_id}` | — | 201 `{status:"added"|"already_exists"}` (tag watchlist'te değilse 400) |
| DELETE | `/{id}/tags/{tag_id}` | — | 204 |
| POST | `/sync-grafana` | — | 200 `{written:int, deleted:int, errors:[...]}` |

Sahiplik: her `{id}` işleminde `group.user_id == current_user.id` doğrulanır; değilse 404 (bilgi sızdırmamak için).

### `remove_watchlist` değişikliği
`DELETE /api/dashboard/watchlist/{tag_id}` (mevcut): watchlist satırını silerken aynı işlemde
`DELETE FROM watchlist_group_members WHERE tag_id=? AND group_id IN (SELECT id FROM watchlist_groups WHERE user_id=?)`.

---

## 4. Grafana entegrasyonu

İki yol; ikisi de mevcut `frser-sqlite-datasource` (uid `scadadb`) üzerinden `tag_readings`'i okur. Zaman sütunu **epoch saniye** (`strftime('%s', timestamp)`), `timeColumns:["time"]`, `queryType:"time series"`, long format (`time, metric, value`) → metric başına seri. (Bkz. `native-monitoring-stack` — ms verince "outside time range" olur.)

### (a) Templated tek dashboard — `scada-watchlist-groups` (provisioned, kalıcı)
- `grafana-provisioning/dashboards` üzerinden dosya ile provision edilir (statik; senkron gerektirmez).
- **Variable** `group` (type=query, datasource=scadadb): `SELECT name AS __text, id AS __value FROM watchlist_groups ORDER BY sort_order, name`. (Tek kullanıcılı dev; çok-kullanıcı için ileride `user_id` filtresi — YAGNI şimdilik.)
- Panel sorgusu:
  ```sql
  SELECT CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time, t.name AS metric, tr.value AS value
  FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id
  WHERE tr.tag_id IN (SELECT tag_id FROM watchlist_group_members WHERE group_id = $group)
    AND tr.timestamp >= datetime('now','-6 hours')
  ORDER BY time
  ```
- Grup ekleme/değiştirme anında variable listesine yansır (canlı SQL). Refresh 10s.

### (b) Grup başına üretilen dashboard — manuel senkron
- `POST /sync-grafana` → backend, kullanıcının her grubu için bir Grafana dashboard'u **Grafana HTTP API** ile yazar:
  - `POST {GRAFANA_URL}/api/dashboards/db`, gövde `{dashboard:{uid:"wl-group-<id>", title:"Watchlist — <name>", panels:[...]}, overwrite:true}`.
  - Panel sorgusu yukarıdakiyle aynı ama **sabit** `group_id = <id>` (variable yok).
  - Auth: HTTP Basic `GRAFANA_USER:GRAFANA_PASSWORD`.
- **Silme**: senkronda, `wl-group-` öneki taşıyıp artık mevcut grup id'lerine karşılık gelmeyen dashboard'lar `DELETE {GRAFANA_URL}/api/dashboards/uid/<uid>`. (Önce `GET /api/search?tag=watchlist-group` ile mevcut üretilmişler listelenir.)
- Üretilen dashboard'lar `tags:["scada","watchlist-group"]` ile etiketlenir (arama/temizlik için).
- Grafana erişilemezse: endpoint 502 + `{errors:[...]}` döner; kısmi başarı `written/deleted` sayılarıyla raporlanır. Çekirdek grup CRUD'u Grafana'ya bağlı DEĞİL — yalnız bu endpoint.

### Config (backend `app/core/config.py` settings)
- `GRAFANA_URL` (vars. `http://localhost:3000`)
- `GRAFANA_USER` (vars. `admin`)
- `GRAFANA_PASSWORD` (vars. `admin123`)
- `.env.example`'a eklenir. Prod'da override.

### Dashboard JSON üretimi
- Backend'de saf bir builder fonksiyonu: `build_group_dashboard(group_id, group_name, datasource_uid) -> dict`. Tek panel (timeseries), CK2 gibi özel eksen YOK (genel); legend table last/min/max. Birim testlenebilir (Grafana'sız).

---

## 5. Frontend (WatchlistTab)

- **Grup yönetim bölümü**: grup listesi (isim + tag sayısı), `+ Yeni grup` (isim input), her grupta rename (inline) + sil (onay).
- **Tag → grup atama**: M:N olduğu için her watchlist tag satırında "gruplar" çoklu-seçim (mevcut grupların rozetleri; tıkla ekle/çıkar). "Gruplanmamış" tag'ler ayrı görünür.
- **"Grafana'ya senkronla"** butonu → `POST /sync-grafana`; sonuç toast (`N dashboard yazıldı, M silindi` veya hata). Buton yanında templated dashboard'a link (`/d/scada-watchlist-groups`).
- API: `client.ts`'e grup fonksiyonları (manuel; bu endpoint'ler generated client'ta da çıkar — `just gen-client`). i18n 5 dil (`dashboard` veya yeni `watchlistGroups` namespace).

---

## 6. Test (TDD)

### Backend (pytest)
- Model + migration: tablolar, FK cascade, unique kısıtları.
- Grup CRUD: create (dup→409), rename, delete (üyelik cascade), sahiplik (başka kullanıcının grubu→404).
- Üyelik: ekle (watchlist'te değilse→400; tekrar→already_exists), çıkar.
- `remove_watchlist` artık grup üyeliklerini de siliyor.
- `GET /` zarfı: groups + ungrouped doğru türetiliyor.
- `sync-grafana`: Grafana HTTP **mock'lu** (httpx mock/transport) — yazılan/silinen sayıları, silme-için-eşleştirme, Grafana-down→502+errors. Gerçek Grafana'ya bağlanmaz.
- `build_group_dashboard`: saf birim test (uid, title, sorgu group_id'yi içeriyor, datasource uid).

### Frontend (vitest)
- Grup state helper(ları) saf birim test.
- WatchlistTab: grup oluştur/rename/sil, tag ekle/çıkar, sync butonu (API mock) — temel etkileşimler.

---

## 7. Kapsam dışı (YAGNI)

- Çok-kullanıcılı Grafana variable filtresi (tek kullanıcılı dev; sonra eklenebilir).
- Grup başına özel panel düzeni / eksen (genel tek panel yeterli).
- Otomatik (gerçek-zamanlı) Grafana senkronu — kasıtlı olarak manuel buton.
- Grup paylaşımı / global gruplar — per-user.
- Dashboard klasörleri (folder) — kök yeterli.

---

## 8. Riskler

- **frser zaman sütunu**: epoch saniye olmalı (ms → "outside time range"). Builder + provisioned JSON buna uymalı.
- **Grafana erişimi**: senkron Grafana ayakta + creds doğru olmalı; değilse 502, çekirdek CRUD etkilenmez.
- **`watchlists`↔grup tutarlılığı**: watchlist'ten çıkan tag grup üyeliklerinden de düşmeli (app-level; testle garanti).
- **frser variable desteği**: templated dashboard variable'ı SQL datasource'tan beslenir; plugin query-variable destekliyor (doğrulanacak; değilse fallback: variable'ı manuel/textbox veya per-grup dashboard'lara güven).
