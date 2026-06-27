import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.backup import Backup


def test_backup_settings_have_defaults():
    assert isinstance(settings.BACKUP_DIR, str) and settings.BACKUP_DIR
    assert settings.BACKUP_RETENTION_DAYS > 0
    assert settings.BACKUP_SCHEDULE_CRON.count(" ") == 4  # 5-field cron
    assert isinstance(settings.RUN_BACKUP_SCHEDULER, bool)


@pytest.mark.asyncio
async def test_backup_model_persists(db_session):
    rec = Backup(
        filename="b.db",
        path="/x/b.db",
        dialect="sqlite",
        kind="full",
        status="completed",
        trigger="manual",
        size_bytes=10,
        sha256="abc",
    )
    db_session.add(rec)
    await db_session.commit()
    got = (await db_session.execute(select(Backup))).scalars().all()
    assert len(got) == 1 and got[0].sha256 == "abc"
