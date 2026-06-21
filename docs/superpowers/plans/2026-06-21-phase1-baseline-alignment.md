# Faz 1 — Baseline Hizalama (Uygulama Planı)

**Tasarım:** `docs/superpowers/specs/2026-06-21-phase1-baseline-alignment-design.md`
**Yürütme:** superpowers:subagent-driven-development (her task: implementer + spec/kalite incelemesi).
**Branch:** yeni `feat/phase1-baseline-alignment` (master'dan; Spec 2 PR #4 merge sonrası master'a dayan).

## Global Kısıtlar (her task'a bağlayıcı)

- **App/runtime kodu DEĞİŞMEZ.** Yalnız paket metadata, bağımlılık dosyaları, justfile, CI yml, .gitignore, dokümantasyon. `scada-reporter/backend/app/`, `frontend/src/`, `scada-core/src/`, `mcp-scada/src/` altındaki kaynak mantığına dokunma.
- **Python tabanı = 3.12.** Tüm metadata `>=3.12`.
- Mevcut testler yeşil kalmalı: backend 252 / frontend 141 / scada-core 54 / mcp 12 / CLI 39.
- Komutlar Windows; venv `scada-reporter/backend/.venv` (Python 3.14.6). uv 0.11.21, pnpm 11, ruff/mypy/bandit sistemde.
- `rm -rf`/`rm -f` yasak (guard hook). Dosya silmek için `git rm` veya PowerShell `Remove-Item` tek-dosya.
- CI yml'yi yerelde tam çalıştıramazsın (gh auth yok) — yml'yi syntax/komut düzeyinde doğrula (recipe'leri/komutları yerelde çalıştır), GH Actions koşusunu kullanıcı PR'da doğrular.
- Commit mesajı sonu: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Sıralama / bağımlılık

T1 (Python) → bağımsız. T2 (dep split) → T3 (lock) → T6 (CI dev grup). T4 (pnpm) bağımsız. T5 (just check) T2/T6 sonrası. T7 (gitignore) bağımsız. Önerilen sıra: **T1 → T2 → T3 → T4 → T5 → T6 → T7.**

---

## Task 1 — Python sürüm hizalama (3.12)

**Dosyalar:** `scada-reporter/packages/scada-core/pyproject.toml`, `scada-reporter/agent-harness/setup.py`, `README.md` (kök), `AGENTS.md` (kök).

**Adımlar:**
1. scada-core `pyproject.toml`: `requires-python = ">=3.14"` → `requires-python = ">=3.12"`.
2. agent-harness `setup.py`: `python_requires=">=3.11"` → `python_requires=">=3.12"`.
3. README.md ve AGENTS.md'ye kısa "Python 3.12+ gereklidir (tek desteklenen baseline)" notu ekle (kurulum/gereksinim bölümüne).
4. **Doğrula:** üç paketi temiz bir 3.12 venv'de editable kur (yerelde 3.14 venv'de de çalışmalı):
   ```
   uv venv /tmp/p1venv --python 3.12   # 3.12 yoksa: uv python install 3.12
   uv pip install --python /tmp/p1venv -e scada-reporter/packages/scada-core -e scada-reporter/agent-harness
   uv pip install --python /tmp/p1venv -r scada-reporter/backend/requirements.txt
   ```
   Hepsi metadata hatası olmadan kurulmalı. (3.12 indirilemezse yerel 3.14 venv ile editable kurulumun bozulmadığını doğrula + notu raporla.)
5. **Commit:** `chore(py): align Python baseline to >=3.12 across scada-core + agent-harness`.

**Doğrulama ölçütü:** scada-core/agent-harness metadata `>=3.12`; editable kurulum 3.12'de temiz.

---

## Task 2 — Backend bağımlılık ayrımı (runtime / dev)

**Dosyalar:** `scada-reporter/backend/requirements.txt` (düzenle), `scada-reporter/backend/requirements-dev.txt` (oluştur).

**Adımlar:**
1. `requirements.txt`'ten `# Dev/test` bloğunu (satır 31-38: pytest, pytest-asyncio, pytest-cov, pytest-xdist, pytest-randomly, httpx, aiosqlite) çıkar. **Not:** `httpx` runtime'da da kullanılıyor (satır 16) — runtime kopyasını KORU, yalnız dev tekrarını sil.
2. `requirements-dev.txt` oluştur: `-r requirements.txt` ilk satır + dev araçları: pytest, pytest-asyncio, pytest-cov, pytest-xdist, pytest-randomly, aiosqlite, **ruff, mypy, bandit, safety** (CI'nin ad-hoc kurduğu araçlar artık burada). Sürümleri venv-freeze ile uyumlu pinle (`.superpowers/sdd/venv-freeze-clean.txt` referans).
3. **Doğrula:**
   ```
   uv pip install --python /tmp/p1venv -r scada-reporter/backend/requirements.txt        # yalnız runtime
   uv pip install --python /tmp/p1venv -r scada-reporter/backend/requirements-dev.txt     # + dev
   ```
   Runtime kurulumda pytest/ruff/mypy/bandit OLMAMALI; dev kurulumda olmalı.
4. **Commit:** `chore(deps): split backend runtime vs dev/test/security requirements`.

**Doğrulama ölçütü:** runtime kurulumu test/lint/security araçları içermez; dev kurulumu hepsini içerir.

---

## Task 3 — Yeniden-üretilebilir bağımlılık lock

**Dosyalar:** `scada-reporter/backend/requirements.lock` (oluştur), `scada-reporter/backend/requirements-dev.lock` (oluştur), `justfile` (install recipe).

**Adımlar:**
1. Lock üret (backend dizininde):
   ```
   uv pip compile requirements.txt -o requirements.lock
   uv pip compile requirements-dev.txt -o requirements-dev.lock
   ```
2. justfile `install` recipe'ini lock'tan kuracak şekilde güncelle (runtime): `uv pip install -r requirements.lock` (veya `uv pip sync requirements.lock`). Yeni `install-dev` recipe: `uv pip sync requirements-dev.lock`. (Mevcut `install` frontend pnpm satırını koru.)
3. **Doğrula:** `uv pip sync --python /tmp/p1venv requirements-dev.lock` temiz çözer; çözülen sürümler venv-freeze ile çelişmemeli (büyük sürüm sapması raporla).
4. **Commit:** `chore(deps): add committed uv lockfiles for reproducible backend installs`.

**Doğrulama ölçütü:** lock dosyaları committed; `uv pip sync` aynı grafiği tutarlı çözer.

---

## Task 4 — Frontend tek lockfile (pnpm)

**Dosyalar:** `scada-reporter/frontend/package-lock.json` (sil), `frontend/README.md` veya kök `README.md` (pnpm zorunlu notu).

**Adımlar:**
1. `package-lock.json`'ı kaldır: `git rm scada-reporter/frontend/package-lock.json` (izleniyorsa) ya da `Remove-Item` (untracked ise). Önce `git ls-files` ile izlenme durumunu kontrol et.
2. Kök/README veya frontend README'ye "pnpm zorunlu paket yöneticisi; npm kullanma" notu (zaten kısmen var, netleştir).
3. **Doğrula:** `cd scada-reporter/frontend && pnpm install --frozen-lockfile` temiz geçer (pnpm-lock.yaml güncel). tsc/lint/vitest hâlâ yeşil (`pnpm tsc --noEmit && pnpm lint && pnpm test`).
4. **Commit:** `chore(frontend): standardize on pnpm, remove package-lock.json`.

**Doğrulama ölçütü:** tek lockfile; `pnpm install --frozen-lockfile` geçer; frontend testleri yeşil.

---

## Task 5 — `just check` ↔ CI hizalama

**Dosyalar:** `justfile`.

**Adımlar:**
1. Yeni recipe'ler ekle:
   - `backend-check: lint format-check typecheck test` (+ opsiyonel `security`).
   - `frontend-check:` → `cd {{fe}} && pnpm tsc --noEmit && pnpm lint && pnpm test`.
   - `cli-check:` → `cd {{ah}} && ../backend/.venv/Scripts/pytest tests/ -v`.
   - `mcp-check:` → mcp-scada testleri (`cd mcp-servers/mcp-scada && ../../scada-reporter/backend/.venv/Scripts/python -m pytest -v`).
2. `check`'i yeniden tanımla: `check: backend-check frontend-check cli-check mcp-check`.
3. **Doğrula:** `just backend-check`, `just frontend-check`, `just cli-check`, `just mcp-check` tek tek yeşil; `just check` hepsini sırayla çalıştırır. (Windows pwsh; recipe söz dizimi mevcut justfile stiliyle uyumlu — `&&` zincirleri pwsh'te çalışır.)
4. **Commit:** `chore(just): expand check to cover frontend, CLI, and MCP (CI parity)`.

**Doğrulama ölçütü:** `just check` backend+frontend+CLI+MCP kapsar; her alt-recipe yeşil.

---

## Task 6 — CI reproducible + MCP job + editable smoke

**Dosyalar:** `.github/workflows/ci.yml`.

**Adımlar:**
1. **backend job:** dev araçları ad-hoc kurma yerine `uv pip install -r requirements-dev.lock` (veya `requirements-dev.txt`) kullan. (`ruff mypy bandit safety` artık dev dosyasında.)
2. **cli job:** scada-core'u da editable kur — `uv pip install -e ../packages/scada-core -e . pytest` (3.12'de artık metadata uyumlu). Bu, 5.1'in editable-install smoke'unu da karşılar.
3. **yeni `mcp` job:** mcp-scada'yı editable kur (scada-core dahil), import smoke + pytest:
   ```yaml
   mcp:
     name: MCP scada (install · import · test)
     runs-on: ubuntu-latest
     defaults: { run: { working-directory: mcp-servers/mcp-scada } }
     steps:
       - uses: actions/checkout@v4
       - uses: astral-sh/setup-uv@v5
         with: { python-version: "3.12" }
       - run: |
           uv venv .venv
           uv pip install -e ../../scada-reporter/packages/scada-core -e . pytest pytest-asyncio
       - run: uv run --no-sync python -c "import mcp_scada.server"
       - run: uv run --no-sync pytest -v --tb=short
   ```
4. **frontend job:** `pnpm install` → `pnpm install --frozen-lockfile`.
5. **Doğrula:** yml `yq`/parse ile geçerli; her job'un komutlarını yerelde elle çalıştırıp geçtiğini kanıtla (editable kurulumlar, mcp import, frozen-lockfile, dev-lock install). GH Actions koşusu = kullanıcı PR'da.
6. **Commit:** `ci: reproducible installs, editable scada-core smoke, MCP job, frozen frontend`.

**Doğrulama ölçütü:** CI 4 job (backend/cli/frontend/mcp); installs lock/frozen; cli+mcp scada-core'u editable kurar.

---

## Task 7 — Artifact / .gitignore politikası

**Dosyalar:** `.gitignore` (kök), `scada-reporter/backend/app/seed_catalog.py` üst-yorum veya ilgili README (girdi dok).

**Adımlar:**
1. `.gitignore`'a ekle: `xlsx/` (büyük WinCC girdisi, local), `.claude/worktrees/`, `~$*.docx`, `~$*.xlsx`, `.commit_msg.txt`, `cld.bat`, `docs/~$*`.
2. Bunların izlenmediğini doğrula (`git ls-files xlsx/` boş olmalı — şu an öyle). İzlenen varsa bu task'ta DOKUNMA, raporla (silme kararı kullanıcının).
3. seed-catalog girdi gereksinimini belgele: `just seed-catalog`'un `xlsx/` altında `full_export.xlsx`/`archive_export.xlsx`/`gunluk_rapor.xlsx` beklediğini README veya seed_catalog docstring'ine yaz (dosyaları repo'ya koymadan).
4. **Doğrula:** `git status --short` yalnız kasıtlı değişiklikleri gösterir (xlsx/, worktrees, stray dosyalar görünmez).
5. **Commit:** `chore(gitignore): ignore local artifacts (xlsx input, worktrees, office locks, stray files)`.

**Doğrulama ölçütü:** normal workflow sonrası `git status` temiz; seed-catalog girdi gereği belgeli.

---

## Final doğrulama (tüm task'lar sonrası)

- `just check` yeşil (backend+frontend+CLI+MCP).
- Temiz 3.12 venv'de backend+CLI+scada-core editable kurulur.
- `uv pip sync requirements-dev.lock` + `pnpm install --frozen-lockfile` tutarlı.
- Tüm mevcut test sayıları korunur (app davranışı değişmedi).
- `git status` temiz.
- Sonra: bütün-branch review + finishing-a-development-branch → PR (master). GH Actions yeşilini kullanıcı doğrular.

## Başarı ölçütü (spec §7 ile aynı)
Tek Python 3.12 baseline + CI smoke; tek frontend lockfile + frozen CI; runtime/dev dep ayrımı + committed lock; `just check`≈CI; MCP CI'da; `git status` temiz; runtime davranışı değişmez.
