from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import effective_permissions, user_can
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: str = ""
    role: str = "operator"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserUpdate(BaseModel):
    language: Literal["en", "tr", "ru", "de"] | None = None
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=6)


async def authenticate_token(token: str, db: AsyncSession) -> User:
    """Token string'i doğrula ve kullanıcıyı döndür. EventSource gibi başlık
    gönderemeyen istemciler (SSE) bunu query-param token ile kullanır."""
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Gecersiz token")
    result = await db.execute(select(User).where(User.username == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kullanici bulunamadi")
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await authenticate_token(token, db)


def require_role(*roles: str):
    async def _check(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetki yok")
        return user

    return _check


def require_perm(perm: str):
    async def _check(user: User = Depends(get_current_user)):
        if not user_can(user, perm):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetki yok")
        return user

    return _check


@router.post("/token", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Kullanici adi veya sifre yanlis")
    token = create_access_token({"sub": user.username, "role": user.role})
    return TokenResponse(access_token=token)


@router.post("/register", status_code=201)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Kullanici adi zaten mevcut")
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    await db.commit()
    return {"id": user.id, "username": user.username}


def _me_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name,
        "language": user.language,
        "permissions": sorted(effective_permissions(user)),
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return _me_payload(user)


@router.patch("/me")
async def update_me(
    data: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.language is not None:
        user.language = data.language
    if data.new_password is not None:
        if not data.current_password or not verify_password(
            data.current_password, user.hashed_password
        ):
            raise HTTPException(status_code=400, detail="Mevcut sifre yanlis")
        user.hashed_password = hash_password(data.new_password)
    await db.commit()
    await db.refresh(user)
    return _me_payload(user)
