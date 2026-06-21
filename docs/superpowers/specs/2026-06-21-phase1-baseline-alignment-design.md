# Faz 1 — Baseline Hizalama (Tasarım)

**Tarih:** 2026-06-21
**Üst-metin:** `docs/superpowers/plans/2026-06-21-project-hardening-roadmap.md` (Faz 1)
**Kaynak bulgular:** `docs/project-improvement-recommendations.md` §5.1, 5.7, 5.11, 5.12, 5.13, 5.14, 5.16, 5.21
**Kapsam:** Baseline + DX + CI. **Runtime davranışına dokunmaz** (app kodu değişmez). En düşük risk, en yüksek sinyal.
**Önkoşul:** yok — hemen yürütülebilir.

---

## 1. Amaç

Repo'yu tek Python tabanına, tek frontend paket yöneticisine, yeniden-üretilebilir bağımlılık kurulumlarına ve CI ile eşleşen yerel kalite kapısına hizala. Hedef: temiz checkout tek komutla kurulur ve `just check` ≈ CI olur. Hiçbir API/collector/şema/auth davranışı değişmez.

## 2. Mevcut durum (repo'ya karşı doğrulandı, 2026-06-21)

- **Python sürümleri tutarsız:** `scada-core/pyproject.toml` `requires-python=">=3.14"`; `agent-harness/setup.py` `python_requires=">=3.11"`; backend `pyproject.toml` ruff `py312`; CI `python-version: "3.12"`. Yerel dev venv 3.14.6 (>=3.12'yi karşılar).
- **Frontend çift lockfile:** `frontend/package-lock.json` + `frontend/pnpm-lock.yaml` ikisi de var; justfile/CI/dok pnpm kullanıyor.
- **Backend bağımlılıkları tek dosyada:** `requirements.txt` satır 1-29 runtime, 31-38 `# Dev/test` (pytest/asyncio/cov/xdist/randomly/httpx/aiosqlite). `requirements-dev.txt` yok. `requirements.lock`/`uv.lock` yok.
- **CI install'ları pinned değil:** backend `uv pip install -r requirements.txt ruff mypy bandit safety`; cli `uv pip install -e . pytest`; frontend `pnpm install` (frozen değil).
- **`just check`** = `lint format-check typecheck test` (yalnız backend; frontend/CLI/MCP/security yok).
- **MCP CI yok:** ci.yml job'ları backend/cli/frontend; `mcp-servers/mcp-scada` yok.
- **CLI CI scada-core kurmuyor:** cli job `uv pip install -e . pytest` — scada-core editable kurulmuyor; scada-core `>=3.14` 3.12 CI'da editable kurulumu kırar. **5.1'in kapattığı asıl boşluk bu.**
- **Artifact'lar:** `xlsx/` untracked ama `app/seed_catalog.py` ondan okuyor (full_export/archive_export/gunluk_rapor.xlsx; ~12MB toplam — büyük binary). `.gitignore`'da `.claude/worktrees/`, `~$*` Office lock, `.commit_msg.txt`, `cld.bat` yok. *(Gözlem, kapsam dışı: `.env.example` şu an `.gitignore`'da — şablon olduğu için izlenmeli; Faz 2 §5.2'de ele alınır.)*

## 3. Kararlar (spec'te sabitlendi — kullanıcı override edebilir)

1. **Python tabanı = 3.12** (tek desteklenen baseline). Tüm paket metadata `>=3.12`. Yerel runtime 3.14 uyumlu kalır (3.14 ⊇ 3.12).
2. **5.11 bağımlılık ayrımı = iki dosya:** `requirements.txt` (runtime) + `requirements-dev.txt` (test/lint/type/security). En düşük risk (doküman önerisi). pyproject+optional-deps yönüne geçiş ileride.
3. **5.12 lock = `uv pip compile`** → committed `requirements.lock` (runtime) + `requirements-dev.lock` (runtime+dev). CI lock'tan kurar; `just install` lock kullanır.
4. **5.21 artifact = gitignore + dokümante et:** `xlsx/` gitignore'a (büyük WinCC girdisi, local; seed-catalog README'sinde dosyaların oraya konacağı belgelenir) + `.claude/worktrees/`, `~$*.docx`/`~$*.xlsx`, `.commit_msg.txt`, `cld.bat`. Repo'ya commitlenmez.
5. **`scada-core` PyPI'da değil:** agent-harness/MCP onu local path/editable ile tüketir. CI editable-install smoke'u üç paketi (backend+CLI+scada-core) aynı 3.12 ortamında kurar.

## 4. Yaklaşım (bulgu bazında)

| Bulgu | Değişiklik | Doğrulama |
|---|---|---|
| 5.1 | scada-core `requires-python=">=3.12"`; agent-harness `python_requires=">=3.12"`; README/AGENTS'a 3.12 notu | CI editable smoke (backend+CLI+core) 3.12'de geçer |
| 5.11 | requirements.txt runtime-only; `requirements-dev.txt` dev/test/lint/type/security | `uv pip install -r` her iki dosya temiz |
| 5.12 | `requirements.lock` + `requirements-dev.lock` (uv pip compile); justfile install lock kullanır | `uv pip sync` lock'tan tutarlı çözer |
| 5.7 | `frontend/package-lock.json` sil; CI `pnpm install --frozen-lockfile`; kök dok pnpm zorunlu | tek lockfile; `pnpm install --frozen-lockfile` geçer |
| 5.13 | justfile `backend-check`/`frontend-check`/`cli-check`/`mcp-check` + `check` hepsini çağırır | `just check` yerelde CI adımlarını kapsar |
| 5.14 | CI: frozen-lockfile (fe), dev-deps grup (be), editable smoke (cli+core) | CI lock'tan tekrar-üretilebilir |
| 5.16 | `just mcp-check` + ci.yml `mcp` job (mcp-scada editable install+import+test) | MCP CI'da yeşil |
| 5.21 | `.gitignore` güncelle; seed-catalog girdi dok | `git status` temiz |

## 5. Kapsam dışı (sonraki fazlar)
- Production config validation, Alembic şema otoritesi, collector ayrımı, JSON login, Docker prod (Faz 2).
- SSE auth, RBAC, OpenAPI generated client, health ayrımı, PLC izleme (Faz 3).
- Backup/restore, Grafana dashboard, release politikası (Faz 4).
- `.env.example` gitignore anomalisi (Faz 2 §5.2 ile birlikte).

## 6. Riskler

| Risk | Önlem |
|---|---|
| scada-core 3.14→3.12 metadata gerçekte 3.14-özel API kullanıyorsa | Kod 3.12 uyumlu (yalnız metadata sınırlıyordu); CI 3.12 smoke kanıtlar. Sorun çıkarsa runtime-min'i koru + CI'yı 3.14'e al kararı kullanıcıya |
| package-lock.json silmek npm-kullanıcısını kırar | Repo zaten pnpm-only (justfile/CI/dok); npm lockfile zaten kullanılmıyor |
| Lock dosyası platforma özgü çözebilir | `uv pip compile` platform-agnostik; CI linux, dev windows — uv universal resolution; sorun olursa `--universal` |
| `safety scan` ağ/hesap gerektirir | CI'de bandit zorunlu, safety opsiyonel (mevcut CI'de zaten yalnız bandit var) |
| CI değişikliklerini yerelde tam doğrulayamam (gh auth yok) | Komutları yerelde çalıştırıp kanıtla (compile/sync/frozen-install/just recipes); GH Actions çalışmasını kullanıcı PR'da doğrular |

## 7. Başarı ölçütü

- Temiz checkout backend+CLI+scada-core'u **tek Python 3.12** ile editable kurar (CI smoke yeşil).
- Frontend tek lockfile (`pnpm-lock.yaml`); CI `--frozen-lockfile`.
- Backend runtime/dev bağımlılıkları ayrı; committed lock'tan tekrar-üretilebilir kurulum.
- `just check` backend+frontend+CLI(+MCP) kapsar; CI ile hizalı.
- MCP install/import/test CI'da.
- Normal geliştirme sonrası `git status` yalnız kasıtlı kaynak değişikliği gösterir.
- **Hiçbir app/runtime davranışı değişmez** — mevcut testler (backend 252 / frontend 141 / scada-core 54 / mcp 12 / CLI 39) yeşil kalır.
