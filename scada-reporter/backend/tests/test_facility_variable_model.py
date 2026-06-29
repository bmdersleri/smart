import pytest

from app.models.facility_variable import FacilityVariable, FacilityVariableDependency


@pytest.mark.asyncio
async def test_create_variable_with_dependency(db_session):
    var = FacilityVariable(
        code="var_test",
        name="Test",
        kind="scalar",
        value_type="number",
        unit="m3/gun",
        expression_json='{"op": "const", "value": 1}',
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
    )
    db_session.add(var)
    await db_session.commit()
    await db_session.refresh(var)

    assert var.id is not None
    assert var.is_active is True
    assert var.version == 1

    dep = FacilityVariableDependency(
        variable_id=var.id, depends_on_type="tag", depends_on_tag_id=None
    )
    db_session.add(dep)
    await db_session.commit()
    await db_session.refresh(dep)
    assert dep.variable_id == var.id


@pytest.mark.asyncio
async def test_code_is_unique(db_session):
    from sqlalchemy.exc import IntegrityError

    for _ in range(2):
        db_session.add(
            FacilityVariable(
                code="dup",
                name="x",
                kind="scalar",
                value_type="number",
                unit="",
                expression_json="{}",
                null_policy="skip",
                quality_policy="good_only",
                default_time_grain="day",
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.commit()
