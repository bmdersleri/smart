from datetime import datetime

import pytest

from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.models.tag import Tag, TagReading
from app.services.facility_variables.binding import resolve_column
from app.services.facility_variables.service import create_variable


def _dummy_template() -> ExcelTemplate:
    """ExcelTemplateColumn FK kısıtını karşılamak için sahte şablon."""
    return ExcelTemplate(
        name=f"test_tpl_{id(object())}",
        file_blob=b"PK\x03\x04fake",
        sheet_name="S",
        header_row=1,
        date_col="A",
        data_start_row=2,
    )


async def _tag_with_readings(db, name, rows):
    tag = Tag(node_id=name, name=name, unit="m3")
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    for ts, val in rows:
        db.add(TagReading(tag_id=tag.id, timestamp=ts, value=val))
    await db.commit()
    return tag


@pytest.mark.asyncio
async def test_tag_column_uses_daily_values(db_session):
    tag = await _tag_with_readings(
        db_session,
        "T",
        [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0)],
    )
    tpl = _dummy_template()
    col = ExcelTemplateColumn(col_letter="E", source_type="tag", tag_id=tag.id, agg="delta")
    tpl.columns = [col]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(col)

    res = await resolve_column(db_session, col, 2026, 6, tz_offset_hours=0)
    assert res.kind == "column"
    assert res.days[1] == 40.0


@pytest.mark.asyncio
async def test_variable_series_column(db_session):
    tag = await _tag_with_readings(
        db_session,
        "T",
        [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0)],
    )
    var = await create_variable(
        db_session,
        code="v_series",
        name="v",
        description="",
        kind="series",
        unit="m3/gun",
        expression={
            "op": "series",
            "source": {"type": "tag", "tag_id": tag.id},
            "agg": "delta",
            "grain": "day",
            "window": "month",
        },
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
        value_type="number",
        created_by=1,
    )
    tpl = _dummy_template()
    col = ExcelTemplateColumn(
        col_letter="K",
        source_type="variable",
        variable_id=var.id,
        write_mode="series",
        target_mode="column",
    )
    tpl.columns = [col]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(col)

    res = await resolve_column(db_session, col, 2026, 6, tz_offset_hours=0)
    assert res.kind == "column"
    assert res.days[1] == 40.0


@pytest.mark.asyncio
async def test_variable_reduce_to_cell(db_session):
    tag = await _tag_with_readings(
        db_session,
        "T",
        [
            (datetime(2026, 6, 1, 0), 0.0),
            (datetime(2026, 6, 1, 23), 40.0),
            (datetime(2026, 6, 2, 0), 40.0),
            (datetime(2026, 6, 2, 23), 80.0),
        ],
    )
    var = await create_variable(
        db_session,
        code="v_series2",
        name="v",
        description="",
        kind="series",
        unit="m3/gun",
        expression={
            "op": "series",
            "source": {"type": "tag", "tag_id": tag.id},
            "agg": "delta",
            "grain": "day",
            "window": "month",
        },
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
        value_type="number",
        created_by=1,
    )
    tpl = _dummy_template()
    col = ExcelTemplateColumn(
        col_letter="K",
        source_type="variable",
        variable_id=var.id,
        write_mode="reduce",
        reduce_op="avg",
        target_mode="cell",
        target_cell="K5",
    )
    tpl.columns = [col]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(col)

    res = await resolve_column(db_session, col, 2026, 6, tz_offset_hours=0)
    assert res.kind == "cell"
    assert res.scalar == 40.0  # avg of daily deltas 40, 40


@pytest.mark.asyncio
async def test_inactive_variable_warns(db_session):
    from app.services.facility_variables.service import deactivate_variable

    var = await create_variable(
        db_session,
        code="v_off",
        name="v",
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
    await deactivate_variable(db_session, var.id)
    tpl = _dummy_template()
    col = ExcelTemplateColumn(
        col_letter="K",
        source_type="variable",
        variable_id=var.id,
        target_mode="cell",
    )
    tpl.columns = [col]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(col)

    res = await resolve_column(db_session, col, 2026, 6, tz_offset_hours=0)
    assert res.warnings
    assert res.scalar is None
