import pytest

from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.services.facility_variables.service import (
    VariableError,
    columns_referencing_variable,
    create_variable,
    deactivate_variable,
)


async def _var(db, code):
    return await create_variable(
        db,
        code=code,
        name=code,
        description="",
        kind="scalar",
        unit="",
        expression={"op": "const", "value": 1.0},
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
        value_type="number",
        created_by=1,
    )


async def _bind(db, var_id, enabled=True):
    tpl = ExcelTemplate(
        name=f"t{var_id}",
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
            variable_id=var_id,
            target_mode="cell",
            enabled=enabled,
        )
    ]
    db.add(tpl)
    await db.commit()


@pytest.mark.asyncio
async def test_referencing_columns_found(db_session):
    var = await _var(db_session, "rv")
    await _bind(db_session, var.id)
    cols = await columns_referencing_variable(db_session, var.id)
    assert len(cols) == 1


@pytest.mark.asyncio
async def test_deactivate_blocked_when_referenced(db_session):
    var = await _var(db_session, "rv2")
    await _bind(db_session, var.id)
    with pytest.raises(VariableError, match="kullan|referenc|bağlı"):
        await deactivate_variable(db_session, var.id)


@pytest.mark.asyncio
async def test_deactivate_force_overrides(db_session):
    var = await _var(db_session, "rv3")
    await _bind(db_session, var.id)
    out = await deactivate_variable(db_session, var.id, force=True)
    assert out.is_active is False


@pytest.mark.asyncio
async def test_deactivate_allowed_when_only_disabled_column(db_session):
    var = await _var(db_session, "rv4")
    await _bind(db_session, var.id, enabled=False)
    out = await deactivate_variable(db_session, var.id)
    assert out.is_active is False
