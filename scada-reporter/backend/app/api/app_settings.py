import zoneinfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.api.license_guard import require_writable
from app.core.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User

router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULT_TIMEZONE = "Europe/Istanbul"


class TimezoneIn(BaseModel):
    timezone: str


async def _get_value(db: AsyncSession, key: str) -> str | None:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    return row.value if row else None


@router.get("")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    tz = await _get_value(db, "timezone")
    return {"timezone": tz or DEFAULT_TIMEZONE}


@router.put("/timezone")
async def put_timezone(
    data: TimezoneIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    if data.timezone not in zoneinfo.available_timezones():
        raise HTTPException(status_code=422, detail="Geçersiz saat dilimi")
    row = (
        await db.execute(select(AppSetting).where(AppSetting.key == "timezone"))
    ).scalar_one_or_none()
    if row is not None:
        row.value = data.timezone
    else:
        db.add(AppSetting(key="timezone", value=data.timezone))
    await db.commit()
    return {"timezone": data.timezone}
