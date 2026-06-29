"""report_archive stores resolved facility-variable refs; orchestrator renders variables."""

import json
from datetime import UTC, datetime

import pytest

from app.models.report_archive import ReportArchive


@pytest.mark.asyncio
async def test_archive_has_variable_refs_column(db_session):
    arch = ReportArchive(
        status="pending",
        trigger="manual",
        tag_ids="[]",
        start=datetime(2026, 6, 1, tzinfo=UTC),
        end=datetime(2026, 6, 2, tzinfo=UTC),
        interval="daily",
        output_format="json",
    )
    db_session.add(arch)
    await db_session.commit()
    await db_session.refresh(arch)
    assert arch.variable_refs_json is None
    arch.variable_refs_json = json.dumps([{"variable_id": 1, "code": "x", "version": 1}])
    await db_session.commit()
    await db_session.refresh(arch)
    assert json.loads(arch.variable_refs_json)[0]["code"] == "x"
