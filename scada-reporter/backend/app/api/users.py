from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.permissions import ALL_PERMISSIONS, Role, effective_permissions
from app.core.security import hash_password
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: Role
    is_active: bool
    permission_overrides: dict
    permissions: list[str]


class UserCreateIn(BaseModel):
    username: str
    email: str
    password: str = Field(min_length=6)
    full_name: str = ""
    role: Role = "operator"
    permission_overrides: dict = {}

    @field_validator("permission_overrides")
    @classmethod
    def _check_overrides(cls, v):
        if v is None:
            return v
        bad = set(v) - set(ALL_PERMISSIONS)
        if bad:
            raise ValueError(f"Gecersiz yetki anahtari: {', '.join(sorted(bad))}")
        return {k: bool(val) for k, val in v.items()}


class UserPatchIn(BaseModel):
    email: str | None = None
    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    permission_overrides: dict | None = None

    @field_validator("permission_overrides")
    @classmethod
    def _check_overrides(cls, v):
        if v is None:
            return v
        bad = set(v) - set(ALL_PERMISSIONS)
        if bad:
            raise ValueError(f"Gecersiz yetki anahtari: {', '.join(sorted(bad))}")
        return {k: bool(val) for k, val in v.items()}


class PasswordIn(BaseModel):
    password: str = Field(min_length=6)


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name or "",
        role=cast(Role, user.role),
        is_active=user.is_active,
        permission_overrides=user.permission_overrides or {},
        permissions=sorted(effective_permissions(user)),
    )


async def _active_admin_count(db: AsyncSession) -> int:
    return (
        await db.scalar(
            select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))
        )
    ) or 0


async def _guard_last_admin(
    db: AsyncSession, target: User, *, removing: bool, new_role=None, new_active=None
) -> None:
    """target admin'i pasifleştiren/silen/düşüren işlem son aktif admin'i
    yok edecekse 400."""
    if target.role != "admin" or not target.is_active:
        return
    demoted = removing or (new_role is not None and new_role != "admin") or (new_active is False)
    if demoted and await _active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Son aktif admin kaldirilamaz")


@router.get("/", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(require_role("admin"))):
    result = await db.execute(select(User).order_by(User.username))
    return [_to_out(u) for u in result.scalars().all()]


@router.post("/", response_model=UserOut, status_code=201)
async def create_user(
    request: Request,
    data: UserCreateIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
):
    dup = await db.scalar(
        select(User.id).where((User.username == data.username) | (User.email == data.email))
    )
    if dup:
        raise HTTPException(status_code=409, detail="Kullanici adi veya e-posta zaten mevcut")
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        permission_overrides=data.permission_overrides,
    )
    db.add(user)
    await db.flush()  # populate user.id before audit row
    await record_audit(
        db,
        actor=actor,
        action="user.create",
        target_type="user",
        target_id=user.id,
        detail={"username": user.username, "role": user.role},
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(user)
    return _to_out(user)


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: int,
    request: Request,
    data: UserPatchIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")
    await _guard_last_admin(db, user, removing=False, new_role=data.role, new_active=data.is_active)
    changed_fields: dict = {}
    old_role = user.role
    if data.email is not None:
        changed_fields["email"] = data.email
        user.email = data.email
    if data.full_name is not None:
        changed_fields["full_name"] = data.full_name
        user.full_name = data.full_name
    if data.role is not None:
        changed_fields["role"] = data.role
        user.role = data.role
    if data.is_active is not None:
        changed_fields["is_active"] = data.is_active
        user.is_active = data.is_active
    if data.permission_overrides is not None:
        changed_fields["permission_overrides"] = data.permission_overrides
        user.permission_overrides = data.permission_overrides
    ip = request.client.host if request.client else None
    await record_audit(
        db,
        actor=actor,
        action="user.update",
        target_type="user",
        target_id=user_id,
        detail={"changed": changed_fields},
        ip=ip,
    )
    # If role changed, also emit a dedicated role_change entry
    if data.role is not None and data.role != old_role:
        await record_audit(
            db,
            actor=actor,
            action="user.role_change",
            target_type="user",
            target_id=user_id,
            detail={"from": old_role, "to": data.role},
            ip=ip,
        )
    await db.commit()
    await db.refresh(user)
    return _to_out(user)


@router.post("/{user_id}/password")
async def reset_password(
    user_id: int,
    request: Request,
    data: PasswordIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")
    user.hashed_password = hash_password(data.password)
    await record_audit(
        db,
        actor=actor,
        action="user.password_reset",
        target_type="user",
        target_id=user_id,
        detail={"username": user.username},
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz")
    await _guard_last_admin(db, user, removing=True)
    deleted_username = user.username
    await db.delete(user)
    await record_audit(
        db,
        actor=admin,
        action="user.delete",
        target_type="user",
        target_id=user_id,
        detail={"username": deleted_username},
        ip=request.client.host if request.client else None,
    )
    await db.commit()
