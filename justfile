venv := "scada-reporter/backend/.venv"

# Projeyi bash ile çalıştır (backend)
run-backend:
    cd scada-reporter/backend && {{venv}}/Scripts/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Bağımlılıkları yükle
install:
    cd scada-reporter/backend && uv pip install -r requirements.txt

# Docker altyapısını başlat (PostgreSQL + Redis)
docker-up:
    cd scada-reporter/docker && docker compose up -d

# Docker altyapısını durdur
docker-down:
    cd scada-reporter/docker && docker compose down

# Python lint
lint:
    ruff check scada-reporter/backend/app/

# Python format kontrol
format-check:
    ruff format --check scada-reporter/backend/app/

# Python otomatik formatla
format:
    ruff format scada-reporter/backend/app/

# S7 PLC tag'lerini veritabanina ekle
seed-tags:
    cd scada-reporter/backend && {{venv}}\Scripts\python app/seed_tags.py

# S7 PLC'ye baglanti testi
test-plc:
    cd scada-reporter/backend && {{venv}}\Scripts\python -c "import snap7; c=snap7.Client(); c.connect('192.168.112.50',0,1); print('PLC baglanti BASARILI'); print('CPU state:', c.get_cpu_state()); c.disconnect(); c.destroy()"

# Type check
typecheck:
    cd scada-reporter/backend && {{venv}}/Scripts/mypy app/

# Tüm kontroller
check: lint format-check typecheck

# Sanal ortamı aktif et
activate:
    echo "Run: .venv\Scripts\activate"

# Proje yapısını göster
tree:
    eza --tree --git-ignore --level=3
