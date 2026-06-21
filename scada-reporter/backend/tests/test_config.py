"""Prod yapılandırma: CORS, ortam, DB pool, secret doğrulama."""

from app.core.config import Settings
from app.core.database import engine_kwargs


def test_cors_origins_parses_csv():
    s = Settings(CORS_ORIGINS="https://a.com, https://b.com ,https://c.com")
    assert s.cors_origins == ["https://a.com", "https://b.com", "https://c.com"]


def test_cors_origins_empty():
    assert Settings(CORS_ORIGINS="").cors_origins == []


def test_is_production_flag():
    assert Settings(ENVIRONMENT="production").is_production is True
    assert Settings(ENVIRONMENT="development").is_production is False


def test_config_errors_flags_default_secret_in_prod():
    s = Settings(ENVIRONMENT="production", SECRET_KEY="dev-secret-key-change-in-production")
    errs = s.config_errors()
    assert any("SECRET_KEY" in e for e in errs)


def test_config_errors_empty_when_all_safe_in_prod():
    s = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="a-real-long-random-secret-value-123456",
        DATABASE_URL="postgresql+asyncpg://u:strongpass@db.example:5432/scada",
        CORS_ORIGINS="https://app.example.com",
    )
    assert s.config_errors() == []


def test_config_errors_dev_allows_default_secret():
    s = Settings(ENVIRONMENT="development", SECRET_KEY="dev-secret-key-change-in-production")
    assert s.config_errors() == []


def test_engine_kwargs_sqlite_skips_pool():
    k = engine_kwargs("sqlite+aiosqlite:///./scada.db")
    assert "pool_size" not in k
    assert k.get("pool_pre_ping") is True


def test_engine_kwargs_postgres_has_pool():
    k = engine_kwargs("postgresql+asyncpg://u:p@h/db")
    assert k["pool_size"] >= 1
    assert k["max_overflow"] >= 0
    assert k["pool_pre_ping"] is True
