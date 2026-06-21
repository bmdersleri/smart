# PLC Sağlık & Sorun İzleme — Tasarım Spec'i

**Tarih:** 2026-06-21
**Durum:** Onaylandı (brainstorming) — implementasyon planı bekliyor
**Branch hedefi:** yeni feature branch (`feat/plc-health-monitoring`)

## 1. Amaç

Operatörün PLC'lerin durumunu sürekli takip edebileceği ve bir sorun
oluştuğunda (bağlantı kopması, veri akışının durması vb.) **anında görebileceği**
bir izleme + uyarı özelliği.

Bugün PLC bağlantı durumu yalnızca anlık (`plc_manager.status()` → `{ip: bool}`)
ve `/health` ile sunuluyor; sorunlar sadece log'a (`logger` + `log_buffer`)
yazılıyor, kalıcı değil ve ekran/restart sonrası kayboluyor. Bu spec kalıcı
geçmiş + aktif uyarı ekler.

## 2. Kapsam (onaylanan kararlar)

- **Kapsam:** Geçmiş (kalıcı olay kaydı) **+** aktif uyarı.
- **"Sorun" tetikleyicileri (dördü de):** bağlantı kopması, bayat veri,
  kısmi okuma hatası, ardışık yeniden bağlanma (flapping).
- **Uyarı kanalları:** UI içi (banner/rozet) **+** e-posta **+** webhook.
- **Mimari:** Collector içi monitor (poller tick'ine bağlı), olaylar DB'ye
  yazılır — split deployment (`RUN_COLLECTOR=False` ayrı API process) uyumlu.

### Kapsam dışı (YAGNI / sonraki faz)
- Per-PLC özel eşik UI'ı (eşikler global, env ile ayarlanır).
- SSE/WebSocket push (UI polling yeterli).
- SMS / push notification.
- Incident'lar üzerinde yorum/atama akışı (sadece ack).

## 3. Mimari

Collector process (poller + plc_manager) bağlantı gerçeğine sahiptir. İzleme
her iki deployment biçiminde (tek process / ayrı collector) görünür olmalı →
**olaylar DB'ye yazılır, API DB'den okur.**

```
poll_loop tick ──► run_once ──► read_plc_group (per-PLC iyi/kötü sonuç)
       │                              │
       │                              ▼
       │                    PlcHealthTracker.record()   (in-memory sayaçlar)
       ▼
plc_monitor_loop (her PLC_MONITOR_INTERVAL sn):
   snapshot = tracker + plc_manager durumu
   (new_state, open[], resolve[]) = detector.evaluate(prev, snapshot, cfg, now)
   ──► plc_health upsert  +  plc_incident open/resolve  (DB)
   ──► notifier.dispatch(incidents)  → UI(implicit) / e-posta / webhook
```

### Birimler (izole, tek sorumluluk)

| Birim | Dosya | Sorumluluk | Bağımlılık |
|-------|-------|-----------|-----------|
| `PlcHealthTracker` | `collector/plc_health.py` | PLC başına in-memory sayaç (iyi/kötü okuma, son başarı zamanı, bağlan/kop geçişleri). Poller besler. | yok (saf veri yapısı) |
| `evaluate` | `monitor/detector.py` | Saf fonksiyon: `(prev_state, observations, cfg, now) → (new_state, to_open, to_resolve)`. PLC/DB yok. | yok |
| `plc_monitor_loop` | `monitor/monitor.py` | Periyodik: snapshot al → evaluate → DB persist → notifier çağır. | tracker, detector, models, notifier |
| `notifier` | `monitor/notifier.py` | Kanallara fan-out (UI-noop, e-posta, webhook), fire-and-forget. | settings, httpx, smtp |
| modeller | `models/plc_health.py`, `models/plc_incident.py` | ORM tabloları | Base |
| API | `api/plc.py` (ek) | health / incidents / summary / ack endpoint'leri | models, auth |
| Frontend | `pages/PlcHealth.tsx` + rozet | görünüm, polling | TanStack Query, generated client |

**İzolasyon testi:** `evaluate` saf fonksiyon — durum geçişlerini PLC veya DB
olmadan test eder (sistemin kalbi). `notifier` kanalları mock'lanır. Tracker
saf veri yapısı. Monitor loop ince orkestrasyon.

## 4. Veri modeli

İki yeni tablo (Alembic migration; SQLite dev + Postgres prod uyumlu, JSON
alan için SQLAlchemy `JSON` tipi).

### `plc_health` — anlık durum (PLC başına 1 satır, upsert)
| Kolon | Tip | Not |
|-------|-----|-----|
| `id` | int PK | |
| `plc_ip` | str | |
| `plc_name` | str | |
| `rack`, `slot` | int | |
| `connected` | bool | |
| `last_success_at` | datetime(UTC) null | son GOOD okuma |
| `consecutive_fail` | int | ardışık başarısız tick |
| `last_error` | str null | son hata mesajı |
| `good_last_cycle`, `bad_last_cycle` | int | son tick tag sayıları |
| `reconnects_last_min` | int | flapping göstergesi |
| `open_incident_count` | int | açık sorun (denormalize, hızlı badge) |
| `updated_at` | datetime(UTC) | |

Benzersiz: `(plc_ip, rack, slot)`.

### `plc_incident` — sorun geçmişi (append + resolve)
| Kolon | Tip | Not |
|-------|-----|-----|
| `id` | int PK | |
| `plc_ip`, `plc_name`, `rack`, `slot` | | |
| `kind` | str | `disconnected` \| `stale_data` \| `partial_bad` \| `flapping` |
| `severity` | str | `warning` \| `critical` |
| `message` | str | insan-okur özet |
| `detail` | JSON | sayımlar, last_error, eşik değerleri |
| `opened_at` | datetime(UTC) | |
| `resolved_at` | datetime(UTC) null | null = **açık sorun** |
| `acknowledged_by` | str null | onaylayan kullanıcı |
| `acknowledged_at` | datetime(UTC) null | |
| `notified` | bool | bildirim gönderildi mi |

İndeks: `(resolved_at)` (açık sorgusu), `(plc_ip, opened_at)`.
Kesinti süresi = `resolved_at - opened_at` (resolved ise).
De-dup kuralı: `(plc_ip, rack, slot, kind)` başına en fazla 1 açık incident.

## 5. Algılama kuralları

`detector.evaluate` saf fonksiyon. Eşikler `settings`'ten (`cfg`) gelir.

| Kural | Severity | Tetik | Eşik (env, varsayılan) |
|-------|----------|-------|------------------------|
| `disconnected` | critical | `connected=False`, 1 tick'ten uzun sürer | — |
| `stale_data` | critical | bağlı ama N sn GOOD okuma yok | `PLC_STALE_SECONDS=60` |
| `partial_bad` | warning | bağlı, BAD oran > R, M tick sürer | `PLC_PARTIAL_BAD_RATIO=0.5`, `PLC_PARTIAL_BAD_CYCLES=3` |
| `flapping` | warning | W sn içinde ≥ C bağlan/kop geçişi | `PLC_FLAP_WINDOW_SECONDS=120`, `PLC_FLAP_COUNT=3` |

- **Histerezis:** açık incident, koşul `PLC_RECOVER_CYCLES` (varsayılan 2) tick
  temiz kalınca auto-resolve. Açılış da `disconnected` için "1 tick'ten uzun"
  şartıyla anlık titremeyi eler.
- **De-dup:** (plc, kind) başına 1 açık incident; tekrar tetik yeni satır açmaz,
  mevcut `detail`'i günceller.
- **Monitor periyodu:** `PLC_MONITOR_INTERVAL=10` sn (poll tick'ten bağımsız).

## 6. Bildirim

`notifier.dispatch(incidents)` — incident **açılış ve çözülüş** anında çağrılır.
Tüm kanallar fire-and-forget, `try/except` ile sarılı (poller/monitor'ı asla
kırmaz). Başarıda `incident.notified=True`.

- **UI (implicit):** ayrı push yok. Frontend `/api/plc/incidents?open=true` ve
  `/incidents/summary` poll eder; açık sorunlar global rozet + listede görünür.
- **E-posta:** `ALERT_EMAIL_ENABLED=False` (vars.). Açıkken `SMTP_HOST/PORT/
  USER/PASS/FROM/TO` ile gönderir. `aiosmtplib` (async) veya executor'da stdlib
  `smtplib`.
- **Webhook:** `ALERT_WEBHOOK_URL` set ise generic JSON POST (httpx):
  `{plc, kind, severity, message, opened_at, resolved_at, detail}`. Slack/Teams/
  Telegram'a uyarlanabilir.
- **Severity kapısı:** `ALERT_MIN_SEVERITY=warning|critical` — e-posta/webhook
  gürültüsünü kıs. UI her zaman hepsini gösterir.

## 7. API (`plc` router'a ek)

| Endpoint | Yetki | Açıklama |
|----------|-------|----------|
| `GET /api/plc/health` | auth | zengin per-PLC durum (`plc_health`) |
| `GET /api/plc/incidents?open=&plc=&limit=` | auth | liste / geçmiş, filtreli |
| `GET /api/plc/incidents/summary` | auth | açık sorun sayıları (severity bazlı) — rozet |
| `POST /api/plc/incidents/{id}/ack` | `plc:manage` | operatör onayı (çözmez, susturur) |

Mevcut `GET /health` infra healthcheck olarak değişmeden kalır.

## 8. Frontend

- **Yeni sayfa "PLC Sağlık"** (route + nav öğesi):
  - Üst özet: `X/Y bağlı`, açık sorun sayıları (critical/warning).
  - Açık sorun kartları: PLC, tür, ne zamandır, mesaj, **ack** butonu.
  - Per-PLC sağlık tablosu: ad, ip, durum, son başarılı okuma, ardışık hata,
    reconnect/dk, son hata. Sortable (mevcut `useSortable`).
  - Çözülmüş geçmiş: süre, PLC/tarih filtresi.
  - `refetchInterval: 10000`.
- **Global alert rozeti** (layout üst çubuk): açık critical sayısı; tıkla → PLC
  Sağlık sayfası; yeni critical'da toast (önceki sayıyla karşılaştır).
- **i18n:** yeni `plcHealth` namespace, 4 dilde string.
- Generated client `just gen-client` ile güncellenir.

## 9. Config (`settings.py` ekleri)

Eşikler (bölüm 5) + kanal config (bölüm 6). E-posta/webhook **varsayılan kapalı**;
yalnız yapılandırılınca aktif. `config_warnings`: bir kanal `ENABLED` ama zorunlu
alanı eksikse uyarı üret (prod healthcheck).

## 10. Persistence & retention

- Alembic migration: iki tablo. Modelleri `alembic/env.py` ve `main.py`
  import listelerine ekle (Base.metadata kaydı için).
- Retention: scheduler'a günlük prune job — `resolved_at` `PLC_INCIDENT_
  RETENTION_DAYS` (vars. 90) günden eski resolved incident'ları siler. Açık
  incident'lar asla silinmez.

## 11. Test stratejisi (TDD)

| Katman | Test |
|--------|------|
| `detector.evaluate` (saf) | her kural aç/çöz; histerezis; de-dup; flap penceresi; çoklu PLC izolasyonu |
| `PlcHealthTracker` | iyi/kötü tally, stale clock, reconnect penceresi sayımı |
| `notifier` | kanal payload doğruluğu, severity kapısı, hata yutma (mock SMTP + httpx) |
| API | incidents liste/filtre, summary sayıları, ack (yetki dahil), health şekli |
| migration | tablolar oluşur, açık/resolved sorguları çalışır |

Mevcut test altyapısı: pytest async, in-memory SQLite StaticPool, autouse
table-clear fixture (sıra bağımsız).

## 12. Açık varsayımlar (implementasyonda netleşir)

- Eşik varsayılanları (60s stale, 0.5 bad ratio vb.) saha geri bildirimiyle
  ayarlanabilir; hepsi env ile override edilebilir.
- E-posta için `aiosmtplib` bağımlılığı eklenecek (yoksa executor'da `smtplib`).
- PLC kimliği `(plc_ip, rack, slot)` üçlüsü; `plc_name` PlcConfig'ten denormalize.
