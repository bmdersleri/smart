import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.models.excel_template import ExcelTemplateColumn
from app.models.tag import Tag


def _tiny_workbook(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "OCAK"
    ws["D2"] = "Tarih"
    wb.save(path)


@pytest.mark.asyncio
async def test_seed_excel_template_binds_columns(db_session, tmp_path, monkeypatch):
    import app.seed_excel_template as mod

    wb_path = tmp_path / "gunluk_rapor.xlsx"
    _tiny_workbook(wb_path)
    monkeypatch.setattr(mod, "WORKBOOK_PATH", wb_path)

    db_session.add_all(
        [
            Tag(node_id="gtuTP02DB01.GUNLUK", name="gtuTP02DB01.GUNLUK", unit=""),
            Tag(node_id="gtuTP01DB01.GUNLUK", name="gtuTP01DB01.GUNLUK", unit=""),
            Tag(node_id="GENEL_TOPLAM_DEBI", name="GENEL_TOPLAM_DEBI", unit=""),
        ]
    )
    await db_session.commit()
    code_to_id = await mod.seed_variables(db_session)

    tid = await mod.seed_excel_template(db_session, code_to_id=code_to_id)
    assert tid is not None
    cols = (
        (
            await db_session.execute(
                select(ExcelTemplateColumn)
                .where(ExcelTemplateColumn.col_letter == "E")
                .where(ExcelTemplateColumn.template_id == tid)
            )
        )
        .scalars()
        .all()
    )
    # column E binds to the aot variable (always seeded)
    assert cols, "column E binding not found for the created template"
    e_col = cols[0]
    assert e_col.source_type == "variable"
    assert e_col.variable_code_snapshot == "aot_giris_debi_gunluk"

    # idempotent: second call skips, returns same id
    again = await mod.seed_excel_template(db_session, code_to_id=code_to_id)
    assert again == tid


@pytest.mark.asyncio
async def test_seed_excel_template_skips_when_workbook_absent(db_session, tmp_path, monkeypatch):
    import app.seed_excel_template as mod

    monkeypatch.setattr(mod, "WORKBOOK_PATH", tmp_path / "nope.xlsx")
    out = await mod.seed_excel_template(db_session, code_to_id={})
    assert out is None
