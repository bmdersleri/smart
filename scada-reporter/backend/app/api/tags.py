import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_perm, require_role
from app.collector.s7_collector import read_tag_now
from app.core.database import get_db
from app.import_catalog import build_full_catalog
from app.models.tag import Tag, TagReading

router = APIRouter(prefix="/tags", tags=["tags"])


class TagCreate(BaseModel):
    node_id: str = ""
    name: str
    description: str = ""
    unit: str = ""
    channel: str = ""
    device: str = ""
    plc_name: str = ""
    plc_ip: str | None = None
    plc_rack: int = 0
    plc_slot: int = 1
    s7_address: str | None = None
    data_type: str = ""
    sample_interval: int = 5
    long_term: bool = False
    deadband: float | None = None


class TagUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    device: str | None = None
    channel: str | None = None
    description: str | None = None
    min_alarm: float | None = None
    max_alarm: float | None = None
    deadband: float | None = None


class TagResponse(BaseModel):
    id: int
    node_id: str
    name: str
    description: str
    unit: str
    channel: str
    device: str
    plc_name: str
    plc_ip: str | None
    s7_address: str | None
    data_type: str
    sample_interval: int
    long_term: bool
    daily_tracking: bool
    is_active: bool
    group_id: int | None
    min_alarm: float | None
    max_alarm: float | None
    deadband: float | None
    # tag ekleme anında doldurulan anlık okuma (DB kolonu değil)
    current_value: float | None = None
    quality: int | None = None
    read_at: datetime | None = None

    model_config = {"from_attributes": True}


@router.get("/browse")
async def browse_tags(_=Depends(get_current_user)):
    """snap7 ile otomatik tag kesfi desteklenmez — bos liste doner."""
    return {"tags": [], "count": 0}


@router.post("/import")
async def import_tags(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    """WinCC full_export.xlsx yükle: Connection->IP çözülür, mutlak adres + tip ile
    tag'ler eklenir. Uzun-süre (archive) katalogu için `just seed-catalog` kullanın.
    """
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400, detail="Lutfen gecerli bir Excel dosyasi yukleyin (.xlsx)"
        )

    content = await file.read()
    try:
        result = build_full_catalog(content)
    except (KeyError, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Excel cozumlenemedi (full_export formati bekleniyor): {e}",
        ) from e

    existing = await db.execute(select(Tag.node_id))
    existing_ids = {r[0] for r in existing.all()}

    imported = 0
    skipped = result.skipped
    for t in result.tags:
        if t["node_id"] in existing_ids:
            skipped += 1
            continue
        db.add(Tag(**t))
        existing_ids.add(t["node_id"])
        imported += 1

    if imported:
        await db.commit()

    return {
        "imported": imported,
        "skipped": skipped,
        "total": imported + skipped,
        "errors": [],
    }


# Dışa/içe aktarma için kolon düzeni (CSV başlığı ve XLSX sütunları)
_IO_COLUMNS = [
    "node_id",
    "name",
    "description",
    "unit",
    "plc_name",
    "plc_ip",
    "plc_rack",
    "plc_slot",
    "s7_address",
    "data_type",
    "sample_interval",
    "long_term",
    "daily_tracking",
    "is_active",
]


@router.get("/export")
async def export_tags(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Tüm tag'leri CSV veya XLSX olarak indir. Aynı kolon düzeni import_csv ile uyumlu."""
    result = await db.execute(select(Tag).order_by(Tag.plc_name, Tag.name))
    tags = result.scalars().all()
    rows = [[getattr(t, c) for c in _IO_COLUMNS] for t in tags]
    stamp = datetime.now().strftime("%Y%m%d-%H%M")

    if format == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Tags"
        ws.append(_IO_COLUMNS)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="tags-{stamp}.xlsx"'},
        )

    sbuf = io.StringIO()
    writer = csv.writer(sbuf)
    writer.writerow(_IO_COLUMNS)
    writer.writerows(rows)
    return Response(
        content=sbuf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="tags-{stamp}.csv"'},
    )


_BOOL_FIELDS = {"long_term", "daily_tracking", "is_active"}
_INT_FIELDS = {"plc_rack", "plc_slot", "sample_interval"}


@router.post("/import_csv")
async def import_tags_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    """Genel CSV import. En az `name` kolonu gerekir; node_id verilmezse türetilir.
    Mevcut node_id atlanır. Kolonlar export ile aynıdır (eksikler varsayılan alır).
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Lütfen .csv dosyası yükleyin")
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or "name" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 'name' kolonu içermeli")

    existing = await db.execute(select(Tag.node_id))
    existing_ids = {r[0] for r in existing.all()}

    imported, skipped, errors = 0, 0, []
    for i, raw in enumerate(reader, start=2):
        name = (raw.get("name") or "").strip()
        if not name:
            skipped += 1
            continue
        payload: dict = {}
        for col in _IO_COLUMNS:
            if col not in raw or raw[col] is None or raw[col] == "":
                continue
            val = raw[col].strip()
            if col in _BOOL_FIELDS:
                payload[col] = val.lower() in ("1", "true", "yes", "evet", "x")
            elif col in _INT_FIELDS:
                try:
                    payload[col] = int(val)
                except ValueError:
                    errors.append(f"satır {i}: {col} sayı değil ({val})")
            else:
                payload[col] = val
        payload["name"] = name
        suffix = payload.get("s7_address") or name
        node_id = payload.get("node_id") or f"{payload.get('plc_name') or 'tag'}:{suffix}"
        if node_id in existing_ids:
            skipped += 1
            continue
        payload["node_id"] = node_id
        db.add(Tag(**payload))
        existing_ids.add(node_id)
        imported += 1

    if imported:
        await db.commit()
    return {"imported": imported, "skipped": skipped, "total": imported + skipped, "errors": errors}


@router.get("/", response_model=list[TagResponse])
async def list_tags(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Tag).order_by(Tag.device, Tag.name))
    return result.scalars().all()


@router.post("/", response_model=TagResponse, status_code=201)
async def create_tag(
    data: TagCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_perm("tag:create")),
):
    payload = data.model_dump()
    # node_id verilmemişse türet (benzersizlik için)
    if not payload.get("node_id"):
        suffix = payload["s7_address"] or payload["name"]
        payload["node_id"] = f"{payload['plc_name'] or 'tag'}:{suffix}"
    tag = Tag(**payload)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    # Yeni tag'in değerini hemen PLC'den oku (zaman aşımı/offline -> None)
    value, quality, read_at = await read_tag_now(
        tag.s7_address, tag.data_type, tag.plc_ip, tag.plc_rack, tag.plc_slot, tag.plc_name
    )
    if quality == 192 and value is not None:
        db.add(TagReading(tag_id=tag.id, value=value, quality=quality, timestamp=read_at))
        await db.commit()

    resp = TagResponse.model_validate(tag)
    resp.current_value = value
    resp.quality = quality
    resp.read_at = read_at
    return resp


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
):
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadi")
    await db.delete(tag)
    await db.commit()


@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: int,
    data: TagUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadi")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tag, field, value)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.get("/{tag_id}/readings")
async def get_readings(
    tag_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    conditions = [TagReading.tag_id == tag_id]
    if start:
        conditions.append(TagReading.timestamp >= start)
    if end:
        conditions.append(TagReading.timestamp <= end)

    result = await db.execute(
        select(TagReading)
        .where(and_(*conditions))
        .order_by(TagReading.timestamp.desc())
        .limit(limit)
    )
    readings = result.scalars().all()
    return [{"timestamp": r.timestamp, "value": r.value, "quality": r.quality} for r in readings]
