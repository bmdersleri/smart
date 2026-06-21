# EKONT SMART REPORT — Project Hardening Roadmap

**Tarih:** 2026-06-21
**Tür:** Üst-düzey program yol haritası (her faz ayrı spec+plan'a dönüştürülecek)
**Kaynak:** `docs/project-improvement-recommendations.md` (22 bulgu) — tüm kritik/yüksek/Faz-1 iddiaları 2026-06-21'de mevcut repo'ya karşı **doğrulandı, geçerli**.
**Durum:** Planlama. Hiçbir kod değişikliği içermez. Faz 1 hazır olunca ayrı bir spec yazılıp subagent-driven-development ile yürütülür.

---

## 0. Bağlam & ilke

Mimari sağlam ve modüler; geniş yeniden-yazıma gerek yok. Amaç: **yerel geliştirme kolaylığını koruyarak production davranışını açık ve güvenli kılmak.** Tek Python tabanı, tek frontend paket yöneticisi, yeniden-üretilebilir bağımlılık kurulumları, ayrı API/collector topolojisi, Alembic-merkezli şema, güvenli secret politikası, operatöre-görünür izleme, belgeli kurtarma ve CI ile eşleşen yerel kalite kapısı.

**Spec 2 etkisi (yeni):** agent yüzeyi artık yazma/yıkıcı işlem yapabiliyor (scada-core tier'lı katalog + CLI --confirm + MCP env-flag). Bu, **5.2 secret validation** ve **5.9 RBAC sertleştirme**yi daha kritik kılar — bu yol haritası bunu Faz 2/3'te yansıtır.

**Sıralama ilkesi:** repo baseline + bağımlılık akışı + kalite kapısı stabil olana dek derin runtime değişikliğine girme (doküman §4 ile uyumlu).

---

## 1. Bulgu → Faz haritası (özet)

| # | Bulgu | Öncelik | Faz | Risk | Karar gerektirir? |
|---|---|---|---|---|---|
| 5.1 | Python sürüm hizalama (3.12) | Critical | 1 | Düşük | — |
| 5.7 | Frontend tek lockfile (pnpm) | Medium | 1 | Düşük | — |
| 5.11 | Backend runtime/dev bağımlılık ayrımı | Medium | 1 | Düşük | Desen (2 dosya mı pyproject mı) |
| 5.12 | Yeniden-üretilebilir Python lock | Medium | 1 | Düşük | — |
| 5.13 | `just check` ↔ CI hizalama | Medium | 1 | Düşük | — |
| 5.14 | CI reproducible install (frozen) | Medium | 1 | Düşük | — |
| 5.16 | MCP CI job | Medium | 1 | Düşük | — |
| 5.21 | Artifact/.gitignore politikası | Düşük | 1* | Düşük | xlsx/ örnek mi? |
| 5.2 | Production secret/credential validation | Critical | 2 | Orta | Hangi env'ler "prod" |
| 5.3 | Alembic şema otoritesi (create_all env-specific) | High | 2 | Orta | — |
| 5.4 | Collector ↔ API runtime ayrımı | High | 2 | Orta | Compose profilleri |
| 5.6 | JSON login wrapper (veya OAuth2 dok.) | Medium | 2 | Düşük | Wrapper mı sadece dok mu |
| 5.15a | Seed script path-hack kaldırma (`-m`) | Medium | 2 | Düşük | — |
| 5.22 | Local↔prod Docker topoloji ayrımı | Medium | 2/4 | Orta | Containerize destekleniyor mu |
| 5.5 | SSE query-token kaldırma | High | 3 | Orta-Yük | Kısa-ömürlü token mı cookie mi fetch mi |
| 5.9 | RBAC tip+DB constraint+audit+rate-limit | High | 3 | Orta | Audit kapsamı |
| 5.8 | Generated OpenAPI client'a geçiş | Medium | 3 | Orta | Kademeli geçiş onayı |
| 5.10 | /live /ready /health ayrımı | Medium | 3 | Orta | — |
| 5.17 | PLC bağlantı izleme + operatör uyarı | Medium | 3 | Orta | Email/webhook isteniyor mu |
| 5.15b | Test izolasyonu + kapsam (timeout, PG/testcontainers) | Medium | 3 | Orta | PG-backed test isteniyor mu |
| 5.18 | Backup/restore/DR dokümanı | Medium | 4 | Düşük | — |
| 5.19 | Grafana dashboard provisioning | Medium | 4 | Düşük | — |
| 5.20 | Agent dokümantasyon konsolidasyonu | Düşük | 4 | Düşük | — |
| — | Retention/rollup politikası dok. | Düşük | 4 | Düşük | — |
| — | Release/versioning politikası | Düşük | 4 | Düşük | — |

\* 5.21 küçük; Faz 1 ile birlikte hızlı-kazanım olarak yapılabilir.

---

## 2. FAZ 1 — Düşük-riskli hizalama (baseline + DX + CI)

**Hedef:** Tek Python tabanı, tek frontend paket yöneticisi, yeniden-üretilebilir kurulumlar, CI ile eşleşen yerel kalite kapısı. Runtime davranışına dokunmaz. **En düşük risk, en yüksek sinyal — ilk yürütülecek faz.**

**Görevler (üst düzey):**
1. **Python 3.12 hizalama (Critical):** `scada-core` `requires-python=">=3.12"`; agent-harness `python_requires=">=3.12"`; backend/CI zaten py312. README/AGENTS'a 3.12 notu. **CI smoke test:** backend+CLI+scada-core editable kurulumu tek Python'da temiz geçer. *(Not: bu repo'da venv 3.14.6 ile çalışıyor — metadata'yı `>=3.12` yap ki 3.12 CI'da editable kurulum kırılmasın; gerçek runtime 3.14 uyumlu kalır.)*
2. **pnpm tekleştirme:** `frontend/package-lock.json` sil; CI `pnpm install --frozen-lockfile`; kök dok'ta pnpm zorunlu paket yöneticisi.
3. **Bağımlılık ayrımı:** backend `requirements.txt` (runtime) + `requirements-dev.txt` (pytest/cov/xdist/randomly/ruff/mypy/bandit/safety). CI dev'i açıkça kurar.
4. **Python lock:** `uv pip compile` ile `requirements.lock` (veya pyproject+uv.lock yönüne geçiş). CI/deploy aynı grafiği çözer.
5. **`just check` genişlet:** `backend-check`/`frontend-check`/`cli-check`/`mcp-check` alt-recipe'ları + birleşik `check`. CI'daki tüm adımları kapsar (frontend tsc/lint/vitest, CLI test, bandit).
6. **CI reproducible:** frozen-lockfile (frontend), dev-deps grup (backend), editable scada-core smoke (CLI).
7. **MCP CI job:** `just mcp-check` + ci.yml'e mcp-scada install/import/test job'u.
8. **(Hızlı-kazanım, 5.21)** `.gitignore`: `~$*.docx/xlsx` Office lock, `.claude/worktrees/`, `.commit_msg.txt`, `cld.bat` vb.; `xlsx/` örnek mi local mı kararı.

**Risk:** Düşük (metadata/CI/dosya düzeyi). **Bağımlılık:** yok — hemen başlanabilir.
**Başarı ölçütü:** Temiz checkout tek Python'la backend+CLI+core kurar; tek frontend lockfile; CI lockfile'dan tekrar-üretilebilir; `just check` ≈ CI; MCP CI'da.

---

## 3. FAZ 2 — Production güvenliği (config + topoloji)

**Hedef:** Güvensiz varsayılanların production'a sızmasını engelle; şema ve collector topolojisini açık kıl.

**Görevler:**
1. **Secret/credential validation (Critical, Spec 2 ile daha kritik):** `config_errors()`'ı genişlet → default SECRET_KEY + default DB parolası/local DSN + boş/wildcard/localhost CORS + API deployment'ta `RUN_COLLECTOR=True` + bilinen seed kredensiyalleri + Grafana default admin. `ENVIRONMENT=production`'da net hata ile başlatmayı reddet. `.env.production.example` (placeholder) ekle; `.env.example` dev-dostu kalır; secret üretim komutları belgelenir.
2. **Alembic şema otoritesi (High):** `create_all()` env-özel → dev'de `AUTO_CREATE_TABLES=True` opsiyonel; staging/prod'da False + `alembic upgrade head` zorunlu. Readiness DB'nin Alembic head'inde olduğunu doğrular (Faz 3 /ready ile bağlanır).
3. **Collector ↔ API ayrımı (High):** prod'da API `RUN_COLLECTOR=False`; collector ayrı süreç (`app.collector.runner` zaten var). Compose profilleri/servisleri: `api`/`collector`/`frontend`/(ops `scheduler`). PLC polling sahibi belgelenir.
4. **JSON login (Medium):** `/api/auth/login` JSON kredensiyal kabul eder, aynı token mantığına delege; `/api/auth/token` OAuth2 uyumluluğu için kalır. (Ya da ertelenirse form-data gereği OpenAPI/dok'ta belirgin.)
5. **Seed script path-hack (Medium, 5.15a):** backend editable kur; `python -m app.seed_users`; `just seed` belgelenmiş sırada; `sys.path.insert` kaldır.
6. **Docker local↔prod ayrımı (Medium, 5.22 kısım):** mevcut compose'u "local/dev infra" diye etiketle; Grafana/DB parolaları env-override zorunlu. (Backend/frontend Dockerfile + prod compose Faz 4'e.)

**Risk:** Orta — runtime başlatma davranışını değiştirir; deployment env'leri ve testler gerekli. **Bağımlılık:** Faz 1 baseline'ı tercih edilir (CI/lock stabil).
**Başarı ölçütü:** Güvensiz varsayılanlarla prod başlamaz; prod şeması yalnız Alembic'le; API worker sayısı artınca PLC acquisition artmaz; JSON ya da net-belgeli login.

---

## 4. FAZ 3 — Auth, sözleşme ve operasyon

**Hedef:** Auth sınırlarını sertleştir, frontend↔backend sözleşmesini sabitle, runtime gözlemlenebilirliği ayır.

**Görevler:**
1. **SSE auth (High):** query-string JWT'yi kaldır → kısa-ömürlü scoped stream token (normal auth HTTP ile alınır, sadece SSE'de kullanılır) **[önerilen, en küçük değişiklik]**; alternatif HTTP-only cookie veya fetch-streaming. Reconnect çalışmaya devam eder; URL'lerde uzun-ömürlü JWT kalmaz.
2. **RBAC sertleştirme (High, Spec 2 ile daha alakalı):** API şemalarında `Literal["admin","operator","viewer"]`; rol için DB check-constraint (migration); frontend union tip; login rate-limit; admin eylemleri (parola reset, rol değişimi, kullanıcı silme/pasifleştirme) için audit log; opsiyonel token versioning (parola reset eski token'ları geçersiz kılar).
3. **OpenAPI generated client (Medium):** `src/api/generated/` üret; `client.ts` yalnız auth/axios/ergonomi sarmalayıcı kalır; üretilen tipler kullanılır; CI'da backend açıp `pnpm gen-client` çalıştırıp stale ise fail.
4. **/live /ready /health ayrımı (Medium):** `/live` (process canlı), `/ready` (DB+Alembic head+Redis+scheduler), `/health` (insan-okur PLC/collector özeti). Ek metrikler: HTTP latency/error, DB pool, scheduler başarı/başarısız, latest-value cache yaşı, Redis durumu.
5. **PLC izleme + uyarı (Medium):** `PlcConnectionLog`-tarzı olay deposu; dashboard'da bağlantı durumu + son başarılı okuma zamanı; frontend bildirimleri; opsiyonel email/webhook; reconnect denemeleri.
6. **Test izolasyonu + kapsam (Medium, 5.15b):** `pytest-timeout`; transactional rollback veya PG/Testcontainers değerlendir; seed `main()`, collector kopma/timeout, bad-quality, frontend mutation path'leri için kapsam; ölçülen baseline sonrası CI coverage eşiği.

**Risk:** Orta — auth ve runtime davranışı; dikkatli test. **Bağımlılık:** /ready Faz 2 Alembic-readiness'e dayanır; RBAC Spec 2 yazma yüzeyini tamamlar.
**Başarı ölçütü:** URL'de uzun-ömürlü JWT yok; geçersiz rol API+DB'de reddedilir + admin eylemleri denetlenebilir; backend OpenAPI değişiklikleri frontend build/freshness'te görünür; orchestrator liveness/readiness ayırabilir; PLC sorunları operatöre görünür.

---

## 5. FAZ 4 — Operasyonel olgunluk

**Hedef:** Kurtarma, izleme ve dağıtım olgunluğu.

**Görevler:**
1. **Backup/restore/DR (5.18):** `docs/backup-recovery.md` — TimescaleDB yedek stratejisi, metadata/şema dump + time-series yedek, rapor arşivi + retention, `.env`/Docker/Alembic/Grafana provisioning yedeği, adım-adım restore, otomatik yedek script + retention.
2. **Grafana dashboard provisioning (5.19):** `docker/grafana/dashboards/` + commit'li dashboard'lar (PLC durumu, read latency, collector tick, rows written, bad-quality oranı, API request/error/latency). Prometheus metrik adlarıyla hizalı.
3. **Docker app images (5.22 devamı):** backend/frontend Dockerfile (containerize destekleniyorsa); ayrı staging/prod compose; health/readiness healthcheck'leri (Faz 3 sonrası).
4. **Retention/rollup dok.:** TimescaleDB retention + continuous aggregate politikasını deployment dok'una bağla.
5. **Agent dok. konsolidasyonu (5.20):** tek yetkili `AGENTS.md`; ikincil dosya kısa yönlendirme; detaylar `guides/` veya `docs/`.
6. **Release/versioning politikası:** backend/frontend/CLI/scada-core için sürüm + release notes politikası.

**Risk:** Düşük (çoğu dok + provisioning). **Bağımlılık:** Faz 3 (/ready healthcheck'ler için) tercih edilir.
**Başarı ölçütü:** Operatör belgeli adımlarla kurtarır; Grafana version-controlled dashboard'larla açılır; (destekleniyorsa) belgeli container deployment; tek yetkili agent dok'u.

---

## 6. Karar gerektiren maddeler (spec öncesi netleştirilecek)

- **5.11:** Bağımlılık ayrımı deseni — iki requirements dosyası mı, pyproject+optional-deps mi? (Doküman: kısa vadede iki dosya en düşük risk.)
- **5.21:** `xlsx/` örnek-girdi mi local-only mi? Export edilen PDF/HTML/XLSX izlenmeli mi?
- **5.2:** Hangi `ENVIRONMENT` değerleri "production" sayılır; validation ne kadar sıkı (fail-fast).
- **5.5:** SSE auth modeli — kısa-ömürlü token / cookie / fetch-stream (öneri: kısa-ömürlü token).
- **5.8:** Generated client'a kademeli geçiş onayı (handwritten client.ts ne kadarı kalır).
- **5.15b:** PG/Testcontainers ile DB testleri isteniyor mu, yoksa SQLite+timeout yeterli mi?
- **5.17:** Operatör uyarısı kapsamı — sadece UI mi, email/webhook de mi?
- **5.22:** Container'lı uygulama dağıtımı destekleniyor mu (Dockerfile + prod compose efor'u buna bağlı)?

---

## 7. Önerilen yürütme akışı

1. **Faz 1**'i ayrı bir spec'e (`docs/superpowers/specs/2026-XX-phase1-baseline-alignment-design.md`) + plana dönüştür → subagent-driven-development ile yürüt. (Düşük risk, hemen.)
2. Faz 1 merge sonrası **Faz 2** spec'i (karar maddeleri netleşince).
3. Faz 3, Faz 4 sırayla — her biri kendi spec+plan'ı, önceki faz baseline'ı üzerine.

Her faz: ayrı branch + PR + (uygunsa) ultrareview. Bu yol haritası referans/üst-metin; faz spec'leri görev-düzeyi detayı taşır.

---

## 8. Acceptance checklist (doküman §7'den, faz etiketli)

Faz 1: Python hizalı (✓CI smoke); tek frontend lockfile; frozen CI; runtime/dev dep ayrımı; committed lock; `just check`≈CI; MCP CI.
Faz 2: prod güvensiz default'ları reddeder; create_all prod'da çalışmaz (Alembic tek yol); API/collector ayrı süreç; JSON ya da belgeli login; seed `sys.path` hack'siz; Docker local↔prod ayrımı belgeli.
Faz 3: SSE'de uzun-ömürlü JWT yok; RBAC rol API+DB'de kısıtlı; admin audit log; login rate-limit; generated client/freshness aktif; /live /ready /health ayrı; PLC durumu operatöre görünür + uyarı; test baseline+eşik.
Faz 4: backup/restore belgeli; Grafana dashboard'lar provisioned; (destekleniyorsa) container deployment belgeli; agent dok tek kaynak; retention/release politikası.
