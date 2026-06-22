"""Production config validation — TDD for Task 1 (Phase 2).

İzolasyon notu: pydantic-settings .env dosyasından ve OS env var'larından okur.
_env_file=None ile .env dosya sızıntısı kesilir; her test tüm ilgili alanları
açık geçer; böylece gerçek .env değerleri test sonuçlarını etkilemez.
"""

from app.core.config import DEFAULT_SECRET, Settings

# ---------------------------------------------------------------------------
# Baseline: tüm-güvenli prod — config_errors() boş döner
# ---------------------------------------------------------------------------

SAFE_PROD_KWARGS = dict(
    _env_file=None,
    ENVIRONMENT="production",
    SECRET_KEY="x" * 32,
    DATABASE_URL="postgresql+asyncpg://u:strongpass@db.example:5432/scada",
    CORS_ORIGINS="https://app.example.com",
    RUN_COLLECTOR=False,
    GRAFANA_PASSWORD="strong-grafana-pass",
)


def make_prod(**overrides) -> Settings:
    """Güvenli prod baseline'ından tek alan değiştirip Settings yarat."""
    kwargs = {**SAFE_PROD_KWARGS, **overrides}
    return Settings(**kwargs)


def make_dev(**overrides) -> Settings:
    """Development ortamı için Settings yarat (izolasyonlu)."""
    kwargs = dict(
        _env_file=None,
        ENVIRONMENT="development",
        SECRET_KEY=DEFAULT_SECRET,
        DATABASE_URL="postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter",
        CORS_ORIGINS="http://localhost:5173,http://localhost:3000",
        RUN_COLLECTOR=True,
    )
    kwargs.update(overrides)
    return Settings(**kwargs)


# ---------------------------------------------------------------------------
# Baseline testi — sızıntı yoksa bu [] döner (kritik)
# ---------------------------------------------------------------------------


def test_all_safe_prod_has_no_errors():
    """Tüm alanlar güvenliyse config_errors() boş döner."""
    s = make_prod()
    assert s.config_errors() == []


# ---------------------------------------------------------------------------
# SECRET_KEY kontrolü (mevcut davranış — gerilemediyse geçmeli)
# ---------------------------------------------------------------------------


def test_default_secret_in_prod_is_error():
    s = make_prod(SECRET_KEY=DEFAULT_SECRET)
    errs = s.config_errors()
    assert any("SECRET_KEY" in e for e in errs)


def test_custom_secret_in_prod_is_ok():
    s = make_prod(SECRET_KEY="super-secret-production-key-32-chars!")
    assert all("SECRET_KEY" not in e for e in s.config_errors())


# ---------------------------------------------------------------------------
# DATABASE_URL kontrolü
# ---------------------------------------------------------------------------


def test_database_url_with_scada123_password_is_error():
    s = make_prod(DATABASE_URL="postgresql+asyncpg://scada:scada123@db.example:5432/prod")
    errs = s.config_errors()
    assert any("DATABASE_URL" in e for e in errs), f"Beklenen DATABASE_URL hatası yok: {errs}"


def test_database_url_with_localhost_is_error():
    s = make_prod(DATABASE_URL="postgresql+asyncpg://u:strongpass@localhost:5432/prod")
    errs = s.config_errors()
    assert any("DATABASE_URL" in e for e in errs), f"Beklenen DATABASE_URL hatası yok: {errs}"


def test_database_url_with_127_0_0_1_is_error():
    s = make_prod(DATABASE_URL="postgresql+asyncpg://u:strongpass@127.0.0.1:5432/prod")
    errs = s.config_errors()
    assert any("DATABASE_URL" in e for e in errs), f"Beklenen DATABASE_URL hatası yok: {errs}"


def test_database_url_with_real_host_and_strong_pass_is_ok():
    s = make_prod(DATABASE_URL="postgresql+asyncpg://dbuser:strongpass@db.prod.example:5432/scada")
    assert all("DATABASE_URL" not in e for e in s.config_errors())


# ---------------------------------------------------------------------------
# CORS kontrolü
# ---------------------------------------------------------------------------


def test_cors_empty_in_prod_is_error():
    s = make_prod(CORS_ORIGINS="")
    errs = s.config_errors()
    assert any("CORS" in e for e in errs), f"Beklenen CORS hatası yok: {errs}"


def test_cors_wildcard_in_prod_is_error():
    s = make_prod(CORS_ORIGINS="*")
    errs = s.config_errors()
    assert any("CORS" in e for e in errs), f"Beklenen CORS hatası yok: {errs}"


def test_cors_wildcard_among_others_in_prod_is_error():
    s = make_prod(CORS_ORIGINS="https://app.example.com,*")
    errs = s.config_errors()
    assert any("CORS" in e for e in errs), f"Beklenen CORS hatası yok: {errs}"


def test_cors_all_localhost_in_prod_is_error():
    s = make_prod(CORS_ORIGINS="http://localhost:5173,http://localhost:3000")
    errs = s.config_errors()
    assert any("CORS" in e for e in errs), f"Beklenen CORS hatası yok: {errs}"


def test_cors_all_127_0_0_1_in_prod_is_error():
    s = make_prod(CORS_ORIGINS="http://127.0.0.1:5173")
    errs = s.config_errors()
    assert any("CORS" in e for e in errs), f"Beklenen CORS hatası yok: {errs}"


def test_cors_mix_real_and_localhost_is_ok():
    """Bir gerçek domain + bir localhost → hata DEĞİL (karışık liste güvensiz değil)."""
    s = make_prod(CORS_ORIGINS="https://app.example.com,http://localhost:5173")
    assert all("CORS" not in e for e in s.config_errors())


def test_cors_single_real_domain_is_ok():
    s = make_prod(CORS_ORIGINS="https://app.example.com")
    assert all("CORS" not in e for e in s.config_errors())


# ---------------------------------------------------------------------------
# Development ortamında HİÇBİR hata olmamalı
# ---------------------------------------------------------------------------


def test_dev_never_has_errors_with_all_unsafe_defaults():
    """Development ortamında tüm güvensiz değerler bile hata üretmez."""
    s = make_dev()
    assert s.config_errors() == []


def test_dev_never_has_errors_with_localhost_db():
    s = make_dev(DATABASE_URL="postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter")
    assert s.config_errors() == []


def test_dev_never_has_errors_with_localhost_cors():
    s = make_dev(CORS_ORIGINS="http://localhost:5173")
    assert s.config_errors() == []


# ---------------------------------------------------------------------------
# config_warnings()
# ---------------------------------------------------------------------------


def test_warnings_prod_run_collector_true_gives_warning():
    s = make_prod(RUN_COLLECTOR=True)
    warnings = s.config_warnings()
    assert len(warnings) == 1
    assert "RUN_COLLECTOR" in warnings[0]


def test_warnings_prod_run_collector_false_is_empty():
    s = make_prod(RUN_COLLECTOR=False)
    assert s.config_warnings() == []


def test_warnings_dev_run_collector_true_is_empty():
    """Development'ta RUN_COLLECTOR=True uyarı üretmez."""
    s = make_dev(RUN_COLLECTOR=True)
    assert s.config_warnings() == []


def test_warnings_dev_run_collector_false_is_empty():
    s = make_dev(RUN_COLLECTOR=False)
    assert s.config_warnings() == []


def test_warnings_prod_weak_grafana_password_gives_warning():
    """Prod'da default/zayıf GRAFANA_PASSWORD bir UYARI üretir (hata değil — opsiyonel)."""
    s = make_prod(GRAFANA_PASSWORD="admin123")
    assert any("GRAFANA_PASSWORD" in w for w in s.config_warnings())
    assert all("GRAFANA_PASSWORD" not in e for e in s.config_errors())


def test_warnings_dev_weak_grafana_password_is_empty():
    """Development'ta zayıf GRAFANA_PASSWORD uyarı üretmez."""
    s = make_dev(GRAFANA_PASSWORD="admin123")
    assert all("GRAFANA" not in w for w in s.config_warnings())


# ---------------------------------------------------------------------------
# Birden fazla hata aynı anda — hepsi raporlanmalı
# ---------------------------------------------------------------------------


def test_multiple_errors_all_reported():
    """Birden fazla güvensiz değer varsa tüm hatalar raporlanır."""
    s = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY=DEFAULT_SECRET,  # hata 1
        DATABASE_URL="postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter",  # hata 2
        CORS_ORIGINS="http://localhost:5173",  # hata 3
        RUN_COLLECTOR=False,
    )
    errs = s.config_errors()
    assert any("SECRET_KEY" in e for e in errs)
    assert any("DATABASE_URL" in e for e in errs)
    assert any("CORS" in e for e in errs)
    assert len(errs) == 3
