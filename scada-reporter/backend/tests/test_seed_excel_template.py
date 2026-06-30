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
                .where(ExcelTemplateColumn.col_letter == "I")
                .where(ExcelTemplateColumn.template_id == tid)
            )
        )
        .scalars()
        .all()
    )
    # column I binds per-day to the Terfi 1 tag (gtuTP02DB01.GUNLUK), agg last
    assert cols, "column I binding not found for the created template"
    i_col = cols[0]
    assert i_col.source_type == "tag"
    assert i_col.source_code == "gtuTP02DB01.GUNLUK"
    assert i_col.agg == "last"
    assert i_col.variable_id is None
    terfi1 = (
        await db_session.execute(select(Tag.id).where(Tag.node_id == "gtuTP02DB01.GUNLUK"))
    ).scalar_one()
    assert i_col.tag_id == terfi1

    # idempotent: second call skips, returns same id
    again = await mod.seed_excel_template(db_session, code_to_id=code_to_id)
    assert again == tid


@pytest.mark.asyncio
async def test_seed_excel_template_skips_when_workbook_absent(db_session, tmp_path, monkeypatch):
    import app.seed_excel_template as mod

    monkeypatch.setattr(mod, "WORKBOOK_PATH", tmp_path / "nope.xlsx")
    out = await mod.seed_excel_template(db_session, code_to_id={})
    assert out is None
