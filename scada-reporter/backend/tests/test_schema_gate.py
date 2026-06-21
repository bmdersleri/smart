"""Şema kapısı TDD — Task 2 (Phase 2).

init_database_schema() yardımcısını monkeypatch ile test eder:
- AUTO_CREATE_TABLES=False → conn.run_sync çağrılmaz; init_timescaledb çağrılır.
- AUTO_CREATE_TABLES=True  → conn.run_sync bir kez Base.metadata.create_all ile çağrılır;
                              init_timescaledb çağrılır.

İzolasyon:
- conn: AsyncMock (run_sync awaitable)
- init_timescaledb: app.main modülündeki referans monkeypatched → gerçek DB dokunulmaz.
- settings.AUTO_CREATE_TABLES: monkeypatch.setattr ile anlık geçersiz kılınır.
"""

from unittest.mock import AsyncMock

import app.main
from app.core.database import Base
from app.main import init_database_schema


async def test_schema_gate_false_skips_create_all(monkeypatch):
    """AUTO_CREATE_TABLES=False → create_all çağrılmaz, init_timescaledb çağrılır."""
    conn = AsyncMock()
    mock_ts = AsyncMock()
    monkeypatch.setattr(app.main, "init_timescaledb", mock_ts)
    monkeypatch.setattr(app.main.settings, "AUTO_CREATE_TABLES", False)

    await init_database_schema(conn)

    assert not conn.run_sync.called, "create_all çağrılmamalıydı (AUTO_CREATE_TABLES=False)"
    mock_ts.assert_awaited_once_with(conn)


async def test_schema_gate_true_calls_create_all(monkeypatch):
    """AUTO_CREATE_TABLES=True → create_all bir kez çağrılır, init_timescaledb çağrılır."""
    conn = AsyncMock()
    mock_ts = AsyncMock()
    monkeypatch.setattr(app.main, "init_timescaledb", mock_ts)
    monkeypatch.setattr(app.main.settings, "AUTO_CREATE_TABLES", True)

    await init_database_schema(conn)

    conn.run_sync.assert_awaited_once_with(Base.metadata.create_all)
    mock_ts.assert_awaited_once_with(conn)


async def test_schema_gate_false_logs_alembic_message(monkeypatch, caplog):
    """AUTO_CREATE_TABLES=False → Alembic bekleniyor mesajı loglanır."""
    import logging

    conn = AsyncMock()
    mock_ts = AsyncMock()
    monkeypatch.setattr(app.main, "init_timescaledb", mock_ts)
    monkeypatch.setattr(app.main.settings, "AUTO_CREATE_TABLES", False)

    with caplog.at_level(logging.INFO, logger="app.main"):
        await init_database_schema(conn)

    assert any("AUTO_CREATE_TABLES=False" in r.message for r in caplog.records), (
        "Alembic bekleniyor log mesajı bulunamadı"
    )


async def test_schema_gate_true_does_not_log_alembic_message(monkeypatch, caplog):
    """AUTO_CREATE_TABLES=True → Alembic mesajı loglanmaz."""
    import logging

    conn = AsyncMock()
    mock_ts = AsyncMock()
    monkeypatch.setattr(app.main, "init_timescaledb", mock_ts)
    monkeypatch.setattr(app.main.settings, "AUTO_CREATE_TABLES", True)

    with caplog.at_level(logging.INFO, logger="app.main"):
        await init_database_schema(conn)

    assert not any("AUTO_CREATE_TABLES=False" in r.message for r in caplog.records)
