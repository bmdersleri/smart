import pytest

from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn


@pytest.mark.asyncio
async def test_template_with_columns_cascade(db_session):
    tpl = ExcelTemplate(
        name="Balta Aylık",
        file_blob=b"PK\x03\x04fake",
        sheet_name="OCAK 2026",
        header_row=2,
        date_col="D",
        data_start_row=3,
        date_mode="write",
    )
    tpl.columns = [
        ExcelTemplateColumn(col_letter="E", tag_id=None, agg="sum", source_code="410BF103"),
        ExcelTemplateColumn(col_letter="F", tag_id=None, agg="delta", source_code="460BF105"),
    ]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)
    assert tpl.id is not None
    assert len(tpl.columns) == 2
    assert tpl.columns[0].enabled is True
