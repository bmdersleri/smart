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


@pytest.mark.asyncio
async def test_column_variable_binding_fields(db_session):
    from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn

    tpl = ExcelTemplate(
        name="vbind",
        description="",
        file_blob=b"x",
        sheet_name="S",
        header_row=1,
        date_col="A",
        data_start_row=2,
    )
    tpl.columns = [
        ExcelTemplateColumn(
            col_letter="K",
            source_type="variable",
            variable_id=None,
            write_mode="reduce",
            reduce_op="sum",
            target_mode="cell",
            target_cell="K5",
            variable_code_snapshot="var_baat_giris_toplam",
        )
    ]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl, attribute_names=["columns"])

    col = tpl.columns[0]
    assert col.source_type == "variable"
    assert col.target_mode == "cell"
    assert col.target_cell == "K5"
    assert col.variable_code_snapshot == "var_baat_giris_toplam"


@pytest.mark.asyncio
async def test_column_defaults_to_tag_source(db_session):
    from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn

    tpl = ExcelTemplate(
        name="legacy",
        description="",
        file_blob=b"x",
        sheet_name="S",
        header_row=1,
        date_col="A",
        data_start_row=2,
    )
    tpl.columns = [ExcelTemplateColumn(col_letter="E", tag_id=None, agg="sum")]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl, attribute_names=["columns"])

    col = tpl.columns[0]
    assert col.source_type == "tag"
    assert col.target_mode == "column"
