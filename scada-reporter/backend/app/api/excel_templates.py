import base64

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.services.template_fill.fill_engine import fill_template
from app.services.template_fill.template_inspector import inspect_template

router = APIRouter(prefix="/excel-templates", tags=["excel-templates"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ColumnIn(BaseModel):
    col_letter: str
    tag_id: int | None = None
    agg: str = "avg"
    source_code: str = ""
    enabled: bool = True


class TemplateIn(BaseModel):
    name: str
    description: str = ""
    file_b64: str
    sheet_name: str
    header_row: int
    date_col: str
    data_start_row: int
    date_mode: str = "write"
    columns: list[ColumnIn]


class ColumnOut(ColumnIn):
    id: int


class TemplateOut(BaseModel):
    id: int
    name: str
    description: str
    sheet_name: str
    header_row: int
    date_col: str
    data_start_row: int
    date_mode: str
    columns: list[ColumnOut]


def _to_out(tpl: ExcelTemplate) -> TemplateOut:
    return TemplateOut(
        id=tpl.id,
        name=tpl.name,
        description=tpl.description,
        sheet_name=tpl.sheet_name,
        header_row=tpl.header_row,
        date_col=tpl.date_col,
        data_start_row=tpl.data_start_row,
        date_mode=tpl.date_mode,
        columns=[
            ColumnOut(
                id=c.id,
                col_letter=c.col_letter,
                tag_id=c.tag_id,
                agg=c.agg,
                source_code=c.source_code,
                enabled=c.enabled,
            )
            for c in tpl.columns
        ],
    )


@router.post("/inspect")
async def inspect(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    data = await file.read()
    try:
        return await inspect_template(db, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Şablon okunamadı: {e}") from e


@router.post("", status_code=201, response_model=TemplateOut)
async def create_template(
    payload: TemplateIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        blob = base64.b64decode(payload.file_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail="file_b64 geçersiz") from e
    tpl = ExcelTemplate(
        name=payload.name,
        description=payload.description,
        file_blob=blob,
        sheet_name=payload.sheet_name,
        header_row=payload.header_row,
        date_col=payload.date_col,
        data_start_row=payload.data_start_row,
        date_mode=payload.date_mode,
        created_by=user.get("id") if isinstance(user, dict) else None,
    )
    tpl.columns = [
        ExcelTemplateColumn(
            col_letter=c.col_letter,
            tag_id=c.tag_id,
            agg=c.agg,
            source_code=c.source_code,
            enabled=c.enabled,
        )
        for c in payload.columns
    ]
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl, attribute_names=["columns"])
    return _to_out(tpl)


@router.get("", response_model=list[TemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await db.execute(select(ExcelTemplate).options(selectinload(ExcelTemplate.columns)))
    return [_to_out(t) for t in result.scalars().all()]


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    tpl = await db.get(ExcelTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    await db.delete(tpl)
    await db.commit()


@router.post("/{template_id}/generate")
async def generate(
    template_id: int,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        data = await fill_template(db, template_id, year, month)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    fname = f"rapor_{year}_{month:02d}.xlsx"
    return Response(
        content=data,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
