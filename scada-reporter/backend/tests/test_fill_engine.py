from datetime import datetime
from io import BytesIO

import pytest
import pytest_asyncio
from openpyxl import Workbook, load_workbook

from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.models.tag import Tag, TagReading
from app.services.template_fill.fill_engine import fill_template


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    yield
    from sqlalchemy import delete

    await db_session.execute(delete(ExcelTemplateColumn))
    await db_session.execute(delete(ExcelTemplate))
    await db_session.execute(delete(TagReading))
    await db_session.execute(delete(Tag))
    await db_session.commit()


def _template_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "OCAK 2026"
    ws["D2"] = "SENSÖR KODLARI"
    ws["E2"] = "410BF103"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest_asyncio.fixture
async def saved_template(db_session):
    tag = Tag(node_id="a", name="410BF103", unit="m3")
    db_session.add(tag)
    await db_session.flush()
    db_session.add_all(
        [
            TagReading(tag_id=tag.id, value=10.0, timestamp=datetime(2026, 1, 1, 6, 0)),
            TagReading(tag_id=tag.id, value=30.0, timestamp=datetime(2026, 1, 1, 18, 0)),
            TagReading(tag_id=tag.id, value=50.0, timestamp=datetime(2026, 1, 3, 9, 0)),
        ]
    )
    tpl = ExcelTemplate(
        name="T",
        file_blob=_template_bytes(),
        sheet_name="OCAK 2026",
        header_row=2,
        date_col="D",
        data_start_row=3,
        date_mode="write",
    )
    tpl.columns = [
        ExcelTemplateColumn(col_letter="E", tag_id=tag.id, agg="sum", source_code="410BF103"),
    ]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)
    return tpl


@pytest.mark.asyncio
async def test_fill_writes_daily_sums_and_dates(db_session, saved_template):
    out = await fill_template(db_session, saved_template.id, 2026, 1)
    ws = load_workbook(BytesIO(out)).active
    assert ws["E3"].value == 40.0  # 10 + 30 (day 1)
    assert ws["E5"].value == 50.0  # day 3
    assert ws["E4"].value is None  # day 2 no data -> blank, not 0
    assert ws["D3"].value.day == 1
    assert ws["D5"].value.day == 3


@pytest.mark.asyncio
async def test_disabled_and_null_columns_skipped(db_session, saved_template):
    saved_template.columns[0].enabled = False
    await db_session.commit()
    out = await fill_template(db_session, saved_template.id, 2026, 1)
    ws = load_workbook(BytesIO(out)).active
    assert ws["E3"].value is None


@pytest.mark.asyncio
async def test_missing_template_raises(db_session):
    with pytest.raises(ValueError):
        await fill_template(db_session, 9999, 2026, 1)
