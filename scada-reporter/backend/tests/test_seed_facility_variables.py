import pytest
from sqlalchemy import select

from app.models.facility_variable import FacilityVariable
from app.models.tag import Tag


@pytest.mark.asyncio
async def test_seed_creates_core_flow_variables(db_session):
    db_session.add_all(
        [
            Tag(node_id="gtuTP02DB01.GUNLUK", name="gtuTP02DB01.GUNLUK", unit=""),
            Tag(node_id="gtuTP01DB01.GUNLUK", name="gtuTP01DB01.GUNLUK", unit=""),
            Tag(node_id="GENEL_TOPLAM_DEBI", name="GENEL_TOPLAM_DEBI", unit=""),
        ]
    )
    await db_session.commit()

    from app.seed_facility_variables import seed_variables

    code_to_id = await seed_variables(db_session)

    assert "aot_giris_debi_gunluk" in code_to_id
    assert "terfi1_debi_gunluk" in code_to_id
    assert "terfi2_debi_gunluk" in code_to_id
    assert "tesis_toplam_debi_olculen_gunluk" in code_to_id
    assert "giris_7gun_ort_debi" in code_to_id

    rows = (await db_session.execute(select(FacilityVariable))).scalars().all()
    assert {r.code for r in rows} >= set(code_to_id)
    # the add-composite references the two terfi tag aggregations
    aot = next(r for r in rows if r.code == "aot_giris_debi_gunluk")
    assert aot.kind == "scalar"
