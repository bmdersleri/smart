set shell := ["pwsh", "-NoProfile", "-Command"]
set windows-shell := ["pwsh", "-NoProfile", "-Command"]

venv := "scada-reporter/backend/.venv"
be := "scada-reporter/backend"
fe := "scada-reporter/frontend"

# ── Geliştirme ──────────────────────────────────────────────────────────────

# Backend + frontend paralel başlat
dev:
    Start-Process powershell -ArgumentList "-NoProfile -Command just run-backend"; just run-frontend

# Backend başlat (hot reload) — watcher yalnız app/ kodunu izler; DB yazımları
# (scada_reporter.db + WAL/SHM) reload tetiklemez, böylece poller çalışırken
# sunucu sürekli yeniden başlamaz / kilide takılmaz.
run-backend:
    cd {{be}} && .venv/Scripts/uvicorn app.main:app --reload --reload-dir app --reload-exclude "*.db" --reload-exclude "*.db-wal" --reload-exclude "*.db-shm" --host 0.0.0.0 --port 8001

# Backend'i kesin yeniden başlat — reload takılırsa/asılırsa kullanılacak yol.
# --reload reloader parent + child spawn ettiğinden port'tan kill yetmez;
# tüm python süreçlerini durdurup tek temiz başlatma yapar (dev-only).
restart-backend:
    powershell -NoProfile -Command "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force"
    just run-backend

# Bağımsız collector process'i (poller + OPC UA); API'den ayrı çalıştırmak için
run-collector:
    cd {{be}} && .venv/Scripts/python -m app.collector.runner

# Frontend başlat (Vite dev server)
run-frontend:
    cd {{fe}} && pnpm dev

# Bağımlılıkları yükle (backend + frontend) — committed lock dosyalarından
install:
    cd {{be}} && uv pip install -r requirements.lock
    cd {{fe}} && pnpm install

# Geliştirme bağımlılıklarını yükle (backend) — committed lock dosyasından
install-dev:
    cd {{be}} && uv pip install -r requirements-dev.lock

# ── Test ─────────────────────────────────────────────────────────────────────

# Testleri çalıştır
test:
    cd {{be}} && .venv/Scripts/pytest tests/ -v

# Test + coverage raporu
test-cov:
    cd {{be}} && .venv/Scripts/pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

# TDD hot reload (dosya değişince otomatik test)
test-watch:
    cd {{be}} && .venv/Scripts/ptw tests/ -- -v

# Frontend unit testleri (vitest)
test-fe:
    cd {{fe}} && pnpm test

# Frontend test hot reload
test-fe-watch:
    cd {{fe}} && pnpm test:watch

# ── Güvenlik ─────────────────────────────────────────────────────────────────

# Python güvenlik taraması (bandit + safety)
security:
    cd {{be}} && .venv/Scripts/bandit.exe -r app/ -ll
    cd {{be}} && .venv/Scripts/safety.exe scan

# ── Veritabanı ───────────────────────────────────────────────────────────────

# Alembic: migration oluştur
makemigration msg="auto":
    cd {{be}} && .venv/Scripts/alembic revision --autogenerate -m "{{msg}}"

# Alembic: migration uygula
migrate:
    cd {{be}} && .venv/Scripts/alembic upgrade head

# Alembic: son migration'ı geri al
migrate-down:
    cd {{be}} && .venv/Scripts/alembic downgrade -1

# Alembic: migration geçmişi
migrate-history:
    cd {{be}} && .venv/Scripts/alembic history --verbose

# S7 PLC tag'lerini veritabanına ekle (eski demo seti)
seed-tags:
    cd {{be}} && .venv/Scripts/python app/seed_tags.py

# Varsayılan kullanıcıları ekle (admin/admin123, operator/operator123)
seed-users:
    cd {{be}} && .venv/Scripts/python app/seed_users.py

# WinCC export'larından uzun-süre tag kataloğunu yükle (xlsx/ klasöründen)
seed-catalog *args:
    cd {{be}} && .venv/Scripts/python -m app.seed_catalog {{args}}

# Tag tiplerine göre toplu deadband ayarla (--dry-run / --reset)
seed-deadband *args:
    cd {{be}} && .venv/Scripts/python -m app.seed_deadband {{args}}

# ── Kalite ───────────────────────────────────────────────────────────────────

# Python lint
lint:
    ruff check {{be}}/app/

# Python lint + otomatik düzelt
lint-fix:
    ruff check --fix {{be}}/app/

# Python format kontrol
format-check:
    ruff format --check {{be}}/app/

# Python otomatik formatla
format:
    ruff format {{be}}/app/

# Type check
typecheck:
    cd {{be}} && .venv/Scripts/mypy app/

# Backend güvenlik taraması (yalnız bandit). NOT: `check`'e DAHİL DEĞİL — bandit
# şu an app/'te pre-existing 5 Medium B608 (SQL string-concat) yüzünden exit 1
# veriyor (CI'nin bandit adımı da aynı durumda). Bulgular giderilince check'e bağla.
backend-security:
    cd {{be}} && .venv/Scripts/bandit.exe -r app/ -ll

# Backend kontrolleri (lint + format + type + test)
backend-check: lint format-check typecheck test

# Frontend kontrolleri (TypeScript + lint + test)
frontend-check:
    cd {{fe}} && pnpm tsc --noEmit && pnpm lint && pnpm test

# Agent CLI kontrolleri
cli-check:
    cd {{ah}} && ../backend/.venv/Scripts/pytest tests/ -v

# MCP server kontrolleri
mcp-check:
    cd mcp-servers/mcp-scada && ../../scada-reporter/backend/.venv/Scripts/python -m pytest tests/ -v

# Tüm kontroller (CI benzeri) — backend + frontend + CLI + MCP
check: backend-check frontend-check cli-check mcp-check

# ── Araçlar ──────────────────────────────────────────────────────────────────

# S7 PLC'ye bağlantı testi
test-plc:
    cd {{be}} && .venv/Scripts/python -c "import snap7; c=snap7.Client(); c.connect('192.168.112.50',0,1); print('PLC BASARILI'); print('CPU:', c.get_cpu_state()); c.disconnect(); c.destroy()"

# Docker altyapısını başlat (PostgreSQL + Redis)
docker-up:
    cd scada-reporter/docker && docker compose up -d

# Docker altyapısını durdur
docker-down:
    cd scada-reporter/docker && docker compose down

# OpenAPI'den TypeScript client üret
gen-client:
    cd {{fe}} && pnpm openapi-ts

# ── Agent CLI ─────────────────────────────────────────────────────────────────

ah := "scada-reporter/agent-harness"

# Agent CLI'yi yükle (editable mode)
install-agent:
    {{venv}}/Scripts/uv pip install -e {{ah}}

# Agent CLI testleri
test-agent:
    cd {{ah}} && ../backend/.venv/Scripts/pytest tests/ -v

# Agent CLI'yi çalıştır (ör: just agent "tags list --json")
agent args="--help":
    {{venv}}/Scripts/scada {{args}}

# Agent REPL
agent-repl:
    {{venv}}/Scripts/scada

# Agent CLI --help
agent-help:
    {{venv}}/Scripts/scada --help

# Proje yapısını göster
tree:
    eza --tree --git-ignore --level=3 --ignore-glob=".venv|node_modules|__pycache__|dist"
