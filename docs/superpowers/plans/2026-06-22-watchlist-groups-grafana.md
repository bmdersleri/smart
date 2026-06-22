# Watchlist Grupları + Grafana — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Watchlist tag'lerini per-user gruplara (M:N) ayıran CRUD + her grubu Grafana'da hem templated tek dashboard hem grup-başına üretilen dashboard olarak gösteren, manuel senkronlu bir özellik.

**Architecture:** İki yeni tablo (`watchlist_groups`, `watchlist_group_members`) mevcut `watchlists`'in üstünde organizasyon katmanı. Yeni router `app/api/watchlist_groups.py`. Grafana entegrasyonu saf builder + httpx-tabanlı senkron servisi (`app/services/grafana_sync.py`), manuel `POST /sync-grafana` endpoint'i ile. Templated dashboard provisioning dosyası. Frontend WatchlistTab'a grup yönetimi.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest (async, httpx AsyncClient + MockTransport), React 19 + TanStack Query + i18next, Grafana HTTP API, frser-sqlite-datasource.

## Global Constraints

- Python 3.14 baseline; backend testleri `pytest -n0 -q` (TDD'de tek dosya), tam suite push öncesi.
- Tüm yeni endpoint'ler `get_current_user` ile korunur; kullanıcı yalnız kendi gruplarına erişir (başka kullanıcı grubu → 404).
- Deps: `from app.api.auth import get_current_user`, `from app.core.database import get_db, Base`, `from app.models.user import User`, `from app.core.security import hash_password` (testlerde).
- Test auth pattern: `User(username=..., email=..., hashed_password=hash_password("test123"), role="admin")` → `POST /api/auth/token` form-data → `Authorization: Bearer`.
- Alembic head (down_revision): `d5e6f7a8b9c0`.
- frser zaman sütunu epoch **saniye** (`strftime('%s', ...)`); datasource uid `scadadb`.
- Dev-phase: direkt master'a commit+push, PR yok.
- Migration uygula: `DATABASE_URL="sqlite+aiosqlite:///./scada_reporter.db" .venv/Scripts/python -m alembic upgrade head`.

---

## File Structure

- Create: `scada-reporter/backend/app/models/watchlist_group.py` — iki ORM modeli.
- Create: `scada-reporter/backend/alembic/versions/<rev>_watchlist_groups.py` — migration.
- Create: `scada-reporter/backend/app/api/watchlist_groups.py` — grup CRUD + member + sync endpoint.
- Create: `scada-reporter/backend/app/services/grafana_sync.py` — saf builder + httpx senkron servisi.
- Modify: `scada-reporter/backend/app/core/config.py` — GRAFANA_* ayarları.
- Modify: `scada-reporter/backend/app/main.py` — yeni router + model import.
- Modify: `scada-reporter/backend/app/api/dashboard.py:260-273` — `remove_watchlist` grup üyeliği temizliği.
- Create tests: `tests/test_watchlist_groups.py`, `tests/test_grafana_sync.py`.
- Create: `scada-reporter/docker/grafana/dashboards/scada-watchlist-groups.json` — templated dashboard (kanonik) + native provisioning dizinine kopya.
- Modify: `scada-reporter/frontend/src/api/client.ts` — grup fonksiyonları.
- Modify: `scada-reporter/frontend/src/pages/dashboard/WatchlistTab.tsx` — grup UI + sync butonu.
- Create: `scada-reporter/frontend/src/utils/watchlistGroups.ts` (+ `.test.ts`) — saf yardımcı.
- Create: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/watchlistGroups.json` + i18n/index.ts kaydı.

---

## Task 1: Models + migration

**Files:**
- Create: `scada-reporter/backend/app/models/watchlist_group.py`
- Create: `scada-reporter/backend/alembic/versions/a1b2c3d4e5f6_watchlist_groups.py`
- Modify: `scada-reporter/backend/app/main.py` (model import for metadata)
- Test: `tests/test_watchlist_groups.py`

**Interfaces:**
- Produces: `WatchlistGroup(id, user_id, name, sort_order, created_at)`, `WatchlistGroupMember(id, group_id, tag_id)` ORM sınıfları; tablolar `watchlist_groups`, `watchlist_group_members`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_watchlist_groups.py
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watchlist_group import WatchlistGroup, WatchlistGroupMember


@pytest.mark.asyncio
async def test_group_and_member_persist(db_session: AsyncSession):
    g = WatchlistGroup(user_id=1, name="Pompalar")
    db_session.add(g)
    await db_session.commit()
    db_session.add(WatchlistGroupMember(group_id=g.id, tag_id=42))
    await db_session.commit()
    rows = (await db_session.execute(select(WatchlistGroupMember))).scalars().all()
    assert len(rows) == 1
    assert rows[0].group_id == g.id and rows[0].tag_id == 42
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py::test_group_and_member_persist -p no:randomly -n0 -q`
Expected: FAIL — `ModuleNotFoundError: app.models.watchlist_group`.

- [ ] **Step 3: Create the models**

```python
# app/models/watchlist_group.py
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WatchlistGroup(Base):
    __tablename__ = "watchlist_groups"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uc_wlgroup_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class WatchlistGroupMember(Base):
    __tablename__ = "watchlist_group_members"
    __table_args__ = (UniqueConstraint("group_id", "tag_id", name="uc_wlmember_group_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False
    )
```

- [ ] **Step 4: Register model import in main.py**

In `app/main.py`, near the other `from app.models import ... # noqa: F401` lines (around line 44-51), add:

```python
from app.models import watchlist_group as _watchlist_group  # noqa: F401
```

- [ ] **Step 5: Run test, verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py::test_group_and_member_persist -p no:randomly -n0 -q`
Expected: PASS (tests use `create_all`, so no migration needed for tests).

- [ ] **Step 6: Create the Alembic migration**

```python
# alembic/versions/a1b2c3d4e5f6_watchlist_groups.py
"""watchlist groups + members

Revision ID: a1b2c3d4e5f6
Revises: d5e6f7a8b9c0
"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "name", name="uc_wlgroup_user_name"),
    )
    op.create_index("ix_watchlist_groups_user_id", "watchlist_groups", ["user_id"])
    op.create_table(
        "watchlist_group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("watchlist_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("group_id", "tag_id", name="uc_wlmember_group_tag"),
    )
    op.create_index("ix_watchlist_group_members_group_id", "watchlist_group_members", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_group_members_group_id", table_name="watchlist_group_members")
    op.drop_table("watchlist_group_members")
    op.drop_index("ix_watchlist_groups_user_id", table_name="watchlist_groups")
    op.drop_table("watchlist_groups")
```

- [ ] **Step 7: Apply + verify migration up/down on a scratch DB**

Run:
```bash
cd scada-reporter/backend
DATABASE_URL="sqlite+aiosqlite:///./_migtest.db" .venv/Scripts/python -m alembic upgrade head
DATABASE_URL="sqlite+aiosqlite:///./_migtest.db" .venv/Scripts/python -m alembic downgrade -1
rm _migtest.db
```
Expected: both succeed, no error. Then apply to dev DB:
`DATABASE_URL="sqlite+aiosqlite:///./scada_reporter.db" .venv/Scripts/python -m alembic upgrade head`

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/backend/app/models/watchlist_group.py scada-reporter/backend/alembic/versions/a1b2c3d4e5f6_watchlist_groups.py scada-reporter/backend/app/main.py scada-reporter/backend/tests/test_watchlist_groups.py
git commit -m "feat(watchlist-groups): models + migration"
```

---

## Task 2: Group create + list API

**Files:**
- Create: `scada-reporter/backend/app/api/watchlist_groups.py`
- Modify: `scada-reporter/backend/app/main.py` (mount router)
- Test: `tests/test_watchlist_groups.py`

**Interfaces:**
- Consumes: `WatchlistGroup`, `WatchlistGroupMember` (Task 1); `Watchlist` model; `get_current_user`, `get_db`.
- Produces: router at prefix `/api/dashboard/watchlist-groups`; `GET /` → `{groups:[{id,name,sort_order,tag_count,tags:[{tag_id,name}]}], ungrouped:[{tag_id,name}]}`; `POST /` `{name}` → 201 group dict (409 on dup).

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_watchlist_groups.py
from httpx import AsyncClient
from app.core.security import hash_password
from app.models.user import User


async def _auth(client, db_session, uname="gu"):
    db_session.add(User(username=uname, email=f"{uname}@t.com",
                        hashed_password=hash_password("test123"), role="admin"))
    await db_session.commit()
    tok = await client.post("/api/auth/token", data={"username": uname, "password": "test123"})
    return {"Authorization": f"Bearer {tok.json()['access_token']}"}


@pytest.mark.asyncio
async def test_create_and_list_group(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session)
    r = await client.post("/api/dashboard/watchlist-groups/", json={"name": "Pompalar"}, headers=h)
    assert r.status_code == 201
    gid = r.json()["id"]
    lst = await client.get("/api/dashboard/watchlist-groups/", headers=h)
    assert lst.status_code == 200
    body = lst.json()
    assert any(g["id"] == gid and g["name"] == "Pompalar" and g["tag_count"] == 0
               for g in body["groups"])
    assert "ungrouped" in body


@pytest.mark.asyncio
async def test_create_duplicate_name_conflicts(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gu2")
    await client.post("/api/dashboard/watchlist-groups/", json={"name": "X"}, headers=h)
    r = await client.post("/api/dashboard/watchlist-groups/", json={"name": "X"}, headers=h)
    assert r.status_code == 409
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py -k "create_and_list or duplicate" -p no:randomly -n0 -q`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Create router with GET + POST**

```python
# app/api/watchlist_groups.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.tag import Tag
from app.models.user import User
from app.models.watchlist import Watchlist
from app.models.watchlist_group import WatchlistGroup, WatchlistGroupMember

router = APIRouter(prefix="/dashboard/watchlist-groups", tags=["watchlist-groups"])


class GroupIn(BaseModel):
    name: str


async def _owned_group(db: AsyncSession, group_id: int, user_id: int) -> WatchlistGroup:
    g = await db.get(WatchlistGroup, group_id)
    if g is None or g.user_id != user_id:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    return g


@router.get("/")
async def list_groups(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    groups = (
        await db.execute(
            select(WatchlistGroup).where(WatchlistGroup.user_id == user.id)
            .order_by(WatchlistGroup.sort_order, WatchlistGroup.name)
        )
    ).scalars().all()

    # members for these groups, with tag names
    members = (
        await db.execute(
            select(WatchlistGroupMember.group_id, WatchlistGroupMember.tag_id, Tag.name)
            .join(Tag, Tag.id == WatchlistGroupMember.tag_id)
            .join(WatchlistGroup, WatchlistGroup.id == WatchlistGroupMember.group_id)
            .where(WatchlistGroup.user_id == user.id)
        )
    ).all()
    by_group: dict[int, list[dict]] = {}
    grouped_tag_ids: set[int] = set()
    for gid, tid, tname in members:
        by_group.setdefault(gid, []).append({"tag_id": tid, "name": tname})
        grouped_tag_ids.add(tid)

    # watchlist tags not in any group → ungrouped
    wl = (
        await db.execute(
            select(Watchlist.tag_id, Tag.name)
            .join(Tag, Tag.id == Watchlist.tag_id)
            .where(Watchlist.user_id == user.id)
        )
    ).all()
    ungrouped = [{"tag_id": tid, "name": n} for tid, n in wl if tid not in grouped_tag_ids]

    return {
        "groups": [
            {
                "id": g.id,
                "name": g.name,
                "sort_order": g.sort_order,
                "tags": by_group.get(g.id, []),
                "tag_count": len(by_group.get(g.id, [])),
            }
            for g in groups
        ],
        "ungrouped": ungrouped,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    g = WatchlistGroup(user_id=user.id, name=body.name.strip())
    db.add(g)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Bu isimde grup zaten var") from None
    await db.refresh(g)
    return {"id": g.id, "name": g.name, "sort_order": g.sort_order, "tag_count": 0, "tags": []}
```

- [ ] **Step 4: Mount router in main.py**

In `app/main.py`, add to the `from app.api import (...)` block: `watchlist_groups`, and after the other `app.include_router(..., prefix="/api")` lines add:

```python
app.include_router(watchlist_groups.router, prefix="/api")
```

- [ ] **Step 5: Run, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py -k "create_and_list or duplicate" -p no:randomly -n0 -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/api/watchlist_groups.py scada-reporter/backend/app/main.py scada-reporter/backend/tests/test_watchlist_groups.py
git commit -m "feat(watchlist-groups): create + list API"
```

---

## Task 3: Rename + delete group

**Files:**
- Modify: `scada-reporter/backend/app/api/watchlist_groups.py`
- Test: `tests/test_watchlist_groups.py`

**Interfaces:**
- Produces: `PATCH /{id}` `{name}` → 200 `{id,name}` (404 if not owned, 409 dup); `DELETE /{id}` → 204.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_rename_and_delete_group(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gu3")
    gid = (await client.post("/api/dashboard/watchlist-groups/", json={"name": "A"}, headers=h)).json()["id"]
    r = await client.patch(f"/api/dashboard/watchlist-groups/{gid}", json={"name": "B"}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "B"
    d = await client.delete(f"/api/dashboard/watchlist-groups/{gid}", headers=h)
    assert d.status_code == 204
    lst = await client.get("/api/dashboard/watchlist-groups/", headers=h)
    assert all(g["id"] != gid for g in lst.json()["groups"])


@pytest.mark.asyncio
async def test_other_users_group_is_404(client: AsyncClient, db_session: AsyncSession):
    h1 = await _auth(client, db_session, "owner")
    gid = (await client.post("/api/dashboard/watchlist-groups/", json={"name": "Mine"}, headers=h1)).json()["id"]
    h2 = await _auth(client, db_session, "intruder")
    r = await client.patch(f"/api/dashboard/watchlist-groups/{gid}", json={"name": "Hacked"}, headers=h2)
    assert r.status_code == 404
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py -k "rename_and_delete or other_users" -p no:randomly -n0 -q`
Expected: FAIL (405/404 route missing).

- [ ] **Step 3: Add PATCH + DELETE**

```python
# append to app/api/watchlist_groups.py
@router.patch("/{group_id}")
async def rename_group(
    group_id: int, body: GroupIn,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    g = await _owned_group(db, group_id, user.id)
    g.name = body.name.strip()
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Bu isimde grup zaten var") from None
    return {"id": g.id, "name": g.name}


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    g = await _owned_group(db, group_id, user.id)
    await db.delete(g)  # members cascade via FK ondelete=CASCADE
    await db.commit()
```

Note: in-memory SQLite test engine — ensure FK cascade works. SQLAlchemy `delete(g)` on the ORM object will cascade member rows only if a relationship/cascade is configured OR DB enforces FK. To be safe and explicit, before deleting the group, delete its members in app code:

```python
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(WatchlistGroupMember).where(WatchlistGroupMember.group_id == group_id))
    await db.delete(g)
    await db.commit()
```

Use the explicit form (add the `sa_delete` import at top: `from sqlalchemy import delete as sa_delete, select`).

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py -k "rename_and_delete or other_users" -p no:randomly -n0 -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/watchlist_groups.py scada-reporter/backend/tests/test_watchlist_groups.py
git commit -m "feat(watchlist-groups): rename + delete"
```

---

## Task 4: Member add / remove

**Files:**
- Modify: `scada-reporter/backend/app/api/watchlist_groups.py`
- Test: `tests/test_watchlist_groups.py`

**Interfaces:**
- Produces: `POST /{group_id}/tags/{tag_id}` → 201 `{status:"added"|"already_exists"}` (400 if tag not on user's watchlist, 404 group); `DELETE /{group_id}/tags/{tag_id}` → 204.

- [ ] **Step 1: Write failing test**

```python
from app.models.tag import Tag as TagModel
from app.models.watchlist import Watchlist


@pytest.mark.asyncio
async def test_add_and_remove_member(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gm")
    # create a tag + put on watchlist (membership precondition)
    db_session.add(TagModel(node_id="N1,REAL0", name="T1"))
    await db_session.commit()
    tag = (await db_session.execute(select(TagModel).where(TagModel.name == "T1"))).scalar_one()
    # find the user id from token-created user
    from app.models.user import User as U
    uid = (await db_session.execute(select(U).where(U.username == "gm"))).scalar_one().id
    db_session.add(Watchlist(user_id=uid, tag_id=tag.id))
    await db_session.commit()
    gid = (await client.post("/api/dashboard/watchlist-groups/", json={"name": "G"}, headers=h)).json()["id"]

    r = await client.post(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)
    assert r.status_code == 201 and r.json()["status"] == "added"
    again = await client.post(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)
    assert again.json()["status"] == "already_exists"

    body = (await client.get("/api/dashboard/watchlist-groups/", headers=h)).json()
    assert any(g["id"] == gid and g["tag_count"] == 1 for g in body["groups"])

    d = await client.delete(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)
    assert d.status_code == 204


@pytest.mark.asyncio
async def test_add_member_not_on_watchlist_400(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gm2")
    db_session.add(TagModel(node_id="N2,REAL0", name="T2"))
    await db_session.commit()
    tag = (await db_session.execute(select(TagModel).where(TagModel.name == "T2"))).scalar_one()
    gid = (await client.post("/api/dashboard/watchlist-groups/", json={"name": "G2"}, headers=h)).json()["id"]
    r = await client.post(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)
    assert r.status_code == 400
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py -k "add_and_remove_member or not_on_watchlist" -p no:randomly -n0 -q`
Expected: FAIL (404 route missing).

- [ ] **Step 3: Add member endpoints**

```python
# append to app/api/watchlist_groups.py
@router.post("/{group_id}/tags/{tag_id}", status_code=status.HTTP_201_CREATED)
async def add_member(
    group_id: int, tag_id: int,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await _owned_group(db, group_id, user.id)
    on_wl = await db.scalar(
        select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.tag_id == tag_id)
    )
    if on_wl is None:
        raise HTTPException(status_code=400, detail="Tag watchlist'te değil")
    exists = await db.scalar(
        select(WatchlistGroupMember).where(
            WatchlistGroupMember.group_id == group_id, WatchlistGroupMember.tag_id == tag_id
        )
    )
    if exists:
        return {"status": "already_exists"}
    db.add(WatchlistGroupMember(group_id=group_id, tag_id=tag_id))
    await db.commit()
    return {"status": "added"}


@router.delete("/{group_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: int, tag_id: int,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await _owned_group(db, group_id, user.id)
    row = await db.scalar(
        select(WatchlistGroupMember).where(
            WatchlistGroupMember.group_id == group_id, WatchlistGroupMember.tag_id == tag_id
        )
    )
    if row:
        await db.delete(row)
        await db.commit()
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py -k "add_and_remove_member or not_on_watchlist" -p no:randomly -n0 -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/watchlist_groups.py scada-reporter/backend/tests/test_watchlist_groups.py
git commit -m "feat(watchlist-groups): add/remove member"
```

---

## Task 5: remove_watchlist clears group memberships

**Files:**
- Modify: `scada-reporter/backend/app/api/dashboard.py:260-273`
- Test: `tests/test_watchlist_groups.py`

**Interfaces:**
- Consumes: existing `DELETE /api/dashboard/watchlist/{tag_id}`.
- Produces: removing a tag from the watchlist also deletes that tag's memberships in the user's groups.

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_remove_watchlist_clears_group_membership(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gw")
    db_session.add(TagModel(node_id="N3,REAL0", name="T3"))
    await db_session.commit()
    tag = (await db_session.execute(select(TagModel).where(TagModel.name == "T3"))).scalar_one()
    from app.models.user import User as U
    uid = (await db_session.execute(select(U).where(U.username == "gw"))).scalar_one().id
    db_session.add(Watchlist(user_id=uid, tag_id=tag.id))
    await db_session.commit()
    gid = (await client.post("/api/dashboard/watchlist-groups/", json={"name": "G"}, headers=h)).json()["id"]
    await client.post(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)

    # remove from watchlist
    await client.delete(f"/api/dashboard/watchlist/{tag.id}", headers=h)

    body = (await client.get("/api/dashboard/watchlist-groups/", headers=h)).json()
    assert all(t["tag_id"] != tag.id for g in body["groups"] for t in g["tags"])
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py::test_remove_watchlist_clears_group_membership -p no:randomly -n0 -q`
Expected: FAIL — membership still present.

- [ ] **Step 3: Update remove_watchlist**

In `app/api/dashboard.py`, add import at top:
```python
from app.models.watchlist_group import WatchlistGroup, WatchlistGroupMember
```
Replace the body of `remove_watchlist` (lines ~260-273) so that after deleting the watchlist row it also clears memberships:

```python
@router.delete("/watchlist/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_watchlist(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.tag_id == tag_id)
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
    # also drop this tag from the user's watchlist groups
    member_ids = (
        await db.execute(
            select(WatchlistGroupMember.id)
            .join(WatchlistGroup, WatchlistGroup.id == WatchlistGroupMember.group_id)
            .where(WatchlistGroup.user_id == current_user.id, WatchlistGroupMember.tag_id == tag_id)
        )
    ).scalars().all()
    for mid in member_ids:
        m = await db.get(WatchlistGroupMember, mid)
        if m:
            await db.delete(m)
    await db.commit()
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py::test_remove_watchlist_clears_group_membership -p no:randomly -n0 -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/dashboard.py scada-reporter/backend/tests/test_watchlist_groups.py
git commit -m "feat(watchlist-groups): removing watchlist tag clears group membership"
```

---

## Task 6: Grafana dashboard builder (pure) + config

**Files:**
- Create: `scada-reporter/backend/app/services/grafana_sync.py`
- Modify: `scada-reporter/backend/app/core/config.py`
- Test: `tests/test_grafana_sync.py`

**Interfaces:**
- Produces: `build_group_dashboard(group_id: int, name: str, datasource_uid: str = "scadadb") -> dict`; settings `GRAFANA_URL`, `GRAFANA_USER`, `GRAFANA_PASSWORD`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_grafana_sync.py
from app.services.grafana_sync import build_group_dashboard


def test_build_group_dashboard_shape():
    d = build_group_dashboard(7, "Pompalar")
    assert d["uid"] == "wl-group-7"
    assert "Pompalar" in d["title"]
    assert "watchlist-group" in d["tags"]
    sql = d["panels"][0]["targets"][0]["rawQueryText"]
    assert "group_id = 7" in sql
    assert "strftime('%s'" in sql  # epoch seconds, not ms
    assert d["panels"][0]["targets"][0]["datasource"]["uid"] == "scadadb"
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_sync.py::test_build_group_dashboard_shape -p no:randomly -n0 -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement builder**

```python
# app/services/grafana_sync.py
from __future__ import annotations


def _query(group_id: int) -> str:
    return (
        "SELECT CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time, "
        "t.name AS metric, tr.value AS value "
        "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
        f"WHERE tr.tag_id IN (SELECT tag_id FROM watchlist_group_members WHERE group_id = {group_id}) "
        "AND tr.timestamp >= datetime('now','-6 hours') ORDER BY time"
    )


def build_group_dashboard(group_id: int, name: str, datasource_uid: str = "scadadb") -> dict:
    ds = {"type": "frser-sqlite-datasource", "uid": datasource_uid}
    sql = _query(group_id)
    return {
        "uid": f"wl-group-{group_id}",
        "title": f"Watchlist — {name}",
        "tags": ["scada", "watchlist-group"],
        "timezone": "browser",
        "schemaVersion": 39,
        "refresh": "10s",
        "time": {"from": "now-6h", "to": "now"},
        "panels": [
            {
                "id": 1,
                "type": "timeseries",
                "title": name,
                "datasource": ds,
                "gridPos": {"h": 18, "w": 24, "x": 0, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "custom": {"drawStyle": "line", "lineWidth": 1,
                                   "fillOpacity": 8, "showPoints": "never", "spanNulls": True},
                        "color": {"mode": "palette-classic"},
                    },
                    "overrides": [],
                },
                "options": {
                    "legend": {"displayMode": "table", "placement": "right",
                               "calcs": ["last", "min", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"},
                },
                "targets": [
                    {
                        "refId": "A",
                        "datasource": ds,
                        "queryType": "time series",
                        "timeColumns": ["time"],
                        "rawQueryText": sql,
                        "queryText": sql,
                    }
                ],
            }
        ],
    }
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_sync.py::test_build_group_dashboard_shape -p no:randomly -n0 -q`
Expected: PASS.

- [ ] **Step 5: Add settings**

In `app/core/config.py` inside `class Settings`, add (near other fields):

```python
    GRAFANA_URL: str = "http://localhost:3000"
    GRAFANA_USER: str = "admin"
    GRAFANA_PASSWORD: str = "admin123"
```

- [ ] **Step 6: Run config import sanity**

Run: `.venv/Scripts/python -c "from app.core.config import settings; print(settings.GRAFANA_URL)"`
Expected: prints `http://localhost:3000`.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/services/grafana_sync.py scada-reporter/backend/app/core/config.py scada-reporter/backend/tests/test_grafana_sync.py
git commit -m "feat(watchlist-groups): grafana dashboard builder + config"
```

---

## Task 7: sync_groups service + sync-grafana endpoint

**Files:**
- Modify: `scada-reporter/backend/app/services/grafana_sync.py`
- Modify: `scada-reporter/backend/app/api/watchlist_groups.py`
- Test: `tests/test_grafana_sync.py`, `tests/test_watchlist_groups.py`

**Interfaces:**
- Consumes: `build_group_dashboard`; settings GRAFANA_*; httpx.
- Produces: `async def sync_groups(groups: list[tuple[int, str]], *, http: httpx.AsyncClient) -> dict` returning `{"written": int, "deleted": int, "errors": list[str]}`; endpoint `POST /api/dashboard/watchlist-groups/sync-grafana` → that dict (502 if all writes fail / Grafana unreachable).

- [ ] **Step 1: Write failing service test (httpx MockTransport)**

```python
# append to tests/test_grafana_sync.py
import httpx
import pytest
from app.services.grafana_sync import sync_groups


@pytest.mark.asyncio
async def test_sync_groups_writes_and_deletes_stale():
    calls = {"posts": [], "deletes": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search":
            # one stale generated dashboard exists (wl-group-99)
            return httpx.Response(200, json=[{"uid": "wl-group-99", "tags": ["watchlist-group"]}])
        if request.url.path == "/api/dashboards/db":
            calls["posts"].append(request)
            return httpx.Response(200, json={"status": "success"})
        if request.url.path.startswith("/api/dashboards/uid/"):
            calls["deletes"].append(request.url.path)
            return httpx.Response(200, json={"title": "deleted"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://gf") as http:
        result = await sync_groups([(1, "A"), (2, "B")], http=http)

    assert result["written"] == 2
    assert result["deleted"] == 1  # wl-group-99 no longer a real group
    assert "/api/dashboards/uid/wl-group-99" in calls["deletes"]
    assert result["errors"] == []
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_sync.py::test_sync_groups_writes_and_deletes_stale -p no:randomly -n0 -q`
Expected: FAIL — `sync_groups` missing.

- [ ] **Step 3: Implement sync_groups**

```python
# append to app/services/grafana_sync.py
import httpx


async def sync_groups(groups: list[tuple[int, str]], *, http: httpx.AsyncClient) -> dict:
    """Push one dashboard per group; delete stale wl-group-* dashboards.

    `http` is a configured AsyncClient (base_url + auth). Returns counts + errors.
    """
    written = 0
    errors: list[str] = []
    wanted_uids = {f"wl-group-{gid}" for gid, _ in groups}

    for gid, name in groups:
        dash = build_group_dashboard(gid, name)
        try:
            r = await http.post("/api/dashboards/db", json={"dashboard": dash, "overwrite": True})
            if r.status_code >= 400:
                errors.append(f"write {gid}: HTTP {r.status_code}")
            else:
                written += 1
        except httpx.HTTPError as e:
            errors.append(f"write {gid}: {e}")

    deleted = 0
    try:
        sr = await http.get("/api/search", params={"tag": "watchlist-group"})
        existing = sr.json() if sr.status_code < 400 else []
    except httpx.HTTPError as e:
        existing = []
        errors.append(f"search: {e}")
    for item in existing:
        uid = item.get("uid", "")
        if uid.startswith("wl-group-") and uid not in wanted_uids:
            try:
                dr = await http.delete(f"/api/dashboards/uid/{uid}")
                if dr.status_code < 400:
                    deleted += 1
                else:
                    errors.append(f"delete {uid}: HTTP {dr.status_code}")
            except httpx.HTTPError as e:
                errors.append(f"delete {uid}: {e}")

    return {"written": written, "deleted": deleted, "errors": errors}
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_sync.py::test_sync_groups_writes_and_deletes_stale -p no:randomly -n0 -q`
Expected: PASS.

- [ ] **Step 5: Write failing endpoint test (patch httpx client factory)**

```python
# append to tests/test_watchlist_groups.py
@pytest.mark.asyncio
async def test_sync_grafana_endpoint(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    import httpx
    from app.api import watchlist_groups as wg

    h = await _auth(client, db_session, "gs")
    await client.post("/api/dashboard/watchlist-groups/", json={"name": "G1"}, headers=h)

    def handler(request):
        if request.url.path == "/api/search":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"status": "success"})

    def fake_client(*args, **kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://gf")

    monkeypatch.setattr(wg.httpx, "AsyncClient", fake_client)
    r = await client.post("/api/dashboard/watchlist-groups/sync-grafana", headers=h)
    assert r.status_code == 200
    assert r.json()["written"] == 1
```

- [ ] **Step 6: Run, verify fail**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py::test_sync_grafana_endpoint -p no:randomly -n0 -q`
Expected: FAIL — endpoint missing.

- [ ] **Step 7: Add the endpoint**

In `app/api/watchlist_groups.py`, add imports at top:
```python
import httpx
from app.core.config import settings
from app.services.grafana_sync import sync_groups
```
Append:
```python
@router.post("/sync-grafana")
async def sync_grafana(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    groups = (
        await db.execute(
            select(WatchlistGroup.id, WatchlistGroup.name).where(WatchlistGroup.user_id == user.id)
        )
    ).all()
    pairs = [(gid, name) for gid, name in groups]
    auth = (settings.GRAFANA_USER, settings.GRAFANA_PASSWORD)
    try:
        async with httpx.AsyncClient(base_url=settings.GRAFANA_URL, auth=auth, timeout=10.0) as http:
            result = await sync_groups(pairs, http=http)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None
    if result["written"] == 0 and result["errors"]:
        raise HTTPException(status_code=502, detail={"message": "Grafana senkron hatası", **result})
    return result
```

- [ ] **Step 8: Run, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_watchlist_groups.py::test_sync_grafana_endpoint tests/test_grafana_sync.py -p no:randomly -n0 -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add scada-reporter/backend/app/services/grafana_sync.py scada-reporter/backend/app/api/watchlist_groups.py scada-reporter/backend/tests/test_grafana_sync.py scada-reporter/backend/tests/test_watchlist_groups.py
git commit -m "feat(watchlist-groups): grafana sync service + endpoint"
```

---

## Task 8: Templated provisioned dashboard

**Files:**
- Create: `scada-reporter/docker/grafana/dashboards/scada-watchlist-groups.json`
- (Runtime) copy to native provisioning dir `C:\Users\aa\Tools\monitoring\grafana-dashboards\`

**Interfaces:**
- Produces: provisioned dashboard uid `scada-watchlist-groups` with a `group` template variable.

- [ ] **Step 1: Create the dashboard JSON**

```json
{
  "uid": "scada-watchlist-groups",
  "title": "SCADA — Watchlist Grupları",
  "tags": ["scada", "watchlist"],
  "timezone": "browser",
  "schemaVersion": 39,
  "version": 1,
  "refresh": "10s",
  "time": { "from": "now-6h", "to": "now" },
  "templating": {
    "list": [
      {
        "name": "group",
        "type": "query",
        "datasource": { "type": "frser-sqlite-datasource", "uid": "scadadb" },
        "refresh": 2,
        "includeAll": false,
        "query": "SELECT name AS __text, id AS __value FROM watchlist_groups ORDER BY sort_order, name"
      }
    ]
  },
  "panels": [
    {
      "id": 1,
      "type": "timeseries",
      "title": "Grup tag değerleri",
      "datasource": { "type": "frser-sqlite-datasource", "uid": "scadadb" },
      "gridPos": { "h": 18, "w": 24, "x": 0, "y": 0 },
      "fieldConfig": {
        "defaults": {
          "custom": { "drawStyle": "line", "lineWidth": 1, "fillOpacity": 8, "showPoints": "never", "spanNulls": true },
          "color": { "mode": "palette-classic" }
        },
        "overrides": []
      },
      "options": {
        "legend": { "displayMode": "table", "placement": "right", "calcs": ["last", "min", "max"] },
        "tooltip": { "mode": "multi", "sort": "desc" }
      },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "frser-sqlite-datasource", "uid": "scadadb" },
          "queryType": "time series",
          "timeColumns": ["time"],
          "rawQueryText": "SELECT CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time, t.name AS metric, tr.value AS value FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id WHERE tr.tag_id IN (SELECT tag_id FROM watchlist_group_members WHERE group_id = $group) AND tr.timestamp >= datetime('now','-6 hours') ORDER BY time",
          "queryText": "SELECT CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time, t.name AS metric, tr.value AS value FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id WHERE tr.tag_id IN (SELECT tag_id FROM watchlist_group_members WHERE group_id = $group) AND tr.timestamp >= datetime('now','-6 hours') ORDER BY time"
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Deploy to native provisioning dir + restart Grafana**

Run:
```bash
cp scada-reporter/docker/grafana/dashboards/scada-watchlist-groups.json "/c/Users/aa/Tools/monitoring/grafana-dashboards/"
powershell -Command "Get-Process grafana -ErrorAction SilentlyContinue | Stop-Process -Force"
```
Then restart Grafana (background) with the documented start command (see `native-monitoring-stack` memory). After ~10s, verify:
```bash
curl -s -u admin:admin123 "http://localhost:3000/api/search?query=Watchlist%20Gruplar" | head -c 300
```
Expected: JSON containing the `scada-watchlist-groups` dashboard. **If the `group` query variable shows no options or errors**, the frser plugin may not support query variables — fallback: change the variable to `type:"textbox"` (user types a group id) and note it; the per-group generated dashboards (Task 7) remain the primary path.

- [ ] **Step 3: Commit**

```bash
git add scada-reporter/docker/grafana/dashboards/scada-watchlist-groups.json
git commit -m "feat(watchlist-groups): templated grafana dashboard with group variable"
```

---

## Task 9: Frontend API client

**Files:**
- Modify: `scada-reporter/frontend/src/api/client.ts`
- (Optional) `just gen-client` to refresh generated client

**Interfaces:**
- Produces: `listWatchlistGroups()`, `createWatchlistGroup(name)`, `renameWatchlistGroup(id,name)`, `deleteWatchlistGroup(id)`, `addTagToGroup(id,tagId)`, `removeTagFromGroup(id,tagId)`, `syncGrafana()` and types `WatchlistGroup`, `WatchlistGroupsResponse`.

- [ ] **Step 1: Add client functions + types**

In `scada-reporter/frontend/src/api/client.ts`, after the watchlist functions (~line 191-195), add:

```typescript
export interface WatchlistGroupTag { tag_id: number; name: string }
export interface WatchlistGroup {
  id: number; name: string; sort_order: number; tag_count: number; tags: WatchlistGroupTag[]
}
export interface WatchlistGroupsResponse { groups: WatchlistGroup[]; ungrouped: WatchlistGroupTag[] }

const WG = '/dashboard/watchlist-groups'
export const listWatchlistGroups = () => api.get<WatchlistGroupsResponse>(`${WG}/`)
export const createWatchlistGroup = (name: string) => api.post<WatchlistGroup>(`${WG}/`, { name })
export const renameWatchlistGroup = (id: number, name: string) =>
  api.patch<{ id: number; name: string }>(`${WG}/${id}`, { name })
export const deleteWatchlistGroup = (id: number) => api.delete(`${WG}/${id}`)
export const addTagToGroup = (id: number, tagId: number) => api.post(`${WG}/${id}/tags/${tagId}`)
export const removeTagFromGroup = (id: number, tagId: number) => api.delete(`${WG}/${id}/tags/${tagId}`)
export const syncGrafana = () =>
  api.post<{ written: number; deleted: number; errors: string[] }>(`${WG}/sync-grafana`)
```

- [ ] **Step 2: Typecheck**

Run: `cd scada-reporter/frontend && pnpm exec tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add scada-reporter/frontend/src/api/client.ts
git commit -m "feat(watchlist-groups): frontend api client"
```

---

## Task 10: i18n strings + pure group helper

**Files:**
- Create: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/watchlistGroups.json`
- Modify: `scada-reporter/frontend/src/i18n/index.ts` (register namespace)
- Create: `scada-reporter/frontend/src/utils/watchlistGroups.ts` + `.test.ts`

**Interfaces:**
- Produces: i18n namespace `watchlistGroups`; helper `tagInGroup(group: WatchlistGroup, tagId: number): boolean`.

- [ ] **Step 1: Write failing helper test**

```typescript
// src/utils/watchlistGroups.test.ts
import { describe, it, expect } from 'vitest'
import { tagInGroup } from './watchlistGroups'
import type { WatchlistGroup } from '../api/client'

const g: WatchlistGroup = { id: 1, name: 'A', sort_order: 0, tag_count: 1, tags: [{ tag_id: 5, name: 'X' }] }

describe('tagInGroup', () => {
  it('true when tag present', () => { expect(tagInGroup(g, 5)).toBe(true) })
  it('false when absent', () => { expect(tagInGroup(g, 9)).toBe(false) })
})
```

- [ ] **Step 2: Run, verify fail**

Run: `cd scada-reporter/frontend && pnpm vitest run src/utils/watchlistGroups.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement helper**

```typescript
// src/utils/watchlistGroups.ts
import type { WatchlistGroup } from '../api/client'

export function tagInGroup(group: WatchlistGroup, tagId: number): boolean {
  return group.tags.some((t) => t.tag_id === tagId)
}
```

- [ ] **Step 4: Run, verify pass**

Run: `cd scada-reporter/frontend && pnpm vitest run src/utils/watchlistGroups.test.ts`
Expected: PASS.

- [ ] **Step 5: Create i18n files (5 langs)**

Create `src/i18n/locales/en/watchlistGroups.json`:
```json
{
  "title": "Groups",
  "new_group": "New group",
  "group_name": "Group name",
  "rename": "Rename",
  "delete": "Delete",
  "ungrouped": "Ungrouped",
  "add_to_group": "Add to group",
  "sync_grafana": "Sync to Grafana",
  "synced": "{{written}} dashboards written, {{deleted}} deleted",
  "sync_failed": "Grafana sync failed",
  "open_dashboard": "Open Grafana dashboard"
}
```
`tr`:
```json
{
  "title": "Gruplar",
  "new_group": "Yeni grup",
  "group_name": "Grup adı",
  "rename": "Yeniden adlandır",
  "delete": "Sil",
  "ungrouped": "Gruplanmamış",
  "add_to_group": "Gruba ekle",
  "sync_grafana": "Grafana'ya senkronla",
  "synced": "{{written}} dashboard yazıldı, {{deleted}} silindi",
  "sync_failed": "Grafana senkron başarısız",
  "open_dashboard": "Grafana dashboard'unu aç"
}
```
`ru`:
```json
{
  "title": "Группы",
  "new_group": "Новая группа",
  "group_name": "Название группы",
  "rename": "Переименовать",
  "delete": "Удалить",
  "ungrouped": "Без группы",
  "add_to_group": "Добавить в группу",
  "sync_grafana": "Синхронизировать с Grafana",
  "synced": "Записано {{written}}, удалено {{deleted}}",
  "sync_failed": "Ошибка синхронизации Grafana",
  "open_dashboard": "Открыть дашборд Grafana"
}
```
`de`:
```json
{
  "title": "Gruppen",
  "new_group": "Neue Gruppe",
  "group_name": "Gruppenname",
  "rename": "Umbenennen",
  "delete": "Löschen",
  "ungrouped": "Ohne Gruppe",
  "add_to_group": "Zur Gruppe hinzufügen",
  "sync_grafana": "Mit Grafana synchronisieren",
  "synced": "{{written}} Dashboards geschrieben, {{deleted}} gelöscht",
  "sync_failed": "Grafana-Synchronisierung fehlgeschlagen",
  "open_dashboard": "Grafana-Dashboard öffnen"
}
```
`ar`:
```json
{
  "title": "المجموعات",
  "new_group": "مجموعة جديدة",
  "group_name": "اسم المجموعة",
  "rename": "إعادة تسمية",
  "delete": "حذف",
  "ungrouped": "غير مجمّع",
  "add_to_group": "أضف إلى المجموعة",
  "sync_grafana": "مزامنة مع Grafana",
  "synced": "تمت كتابة {{written}}، وحذف {{deleted}}",
  "sync_failed": "فشلت مزامنة Grafana",
  "open_dashboard": "افتح لوحة Grafana"
}
```

- [ ] **Step 6: Register namespace in i18n/index.ts**

In `src/i18n/index.ts` (per memory: 3 edit sites): add `import enWG from './locales/en/watchlistGroups.json'` (+ tr/ru/de/ar), add `watchlistGroups: enWG` to each language's `resources` object, and add `'watchlistGroups'` to the `ns` array.

- [ ] **Step 7: Run typecheck + the helper test**

Run: `cd scada-reporter/frontend && pnpm exec tsc --noEmit && pnpm vitest run src/utils/watchlistGroups.test.ts`
Expected: no TS errors, test PASS.

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/src/utils/watchlistGroups.ts scada-reporter/frontend/src/utils/watchlistGroups.test.ts scada-reporter/frontend/src/i18n/
git commit -m "feat(watchlist-groups): i18n + group helper"
```

---

## Task 11: WatchlistTab group management UI

**Files:**
- Modify: `scada-reporter/frontend/src/pages/dashboard/WatchlistTab.tsx`
- Test: `scada-reporter/frontend/src/pages/dashboard/WatchlistGroups.test.tsx` (light render test)

**Interfaces:**
- Consumes: client functions + `tagInGroup` (Tasks 9-10).
- Produces: group management section in the watchlist tab (list/create/rename/delete groups, toggle a tag's group membership, "Sync to Grafana" button + link).

- [ ] **Step 1: Read current WatchlistTab to find the insert point**

Run: `sed -n '1,60p' scada-reporter/frontend/src/pages/dashboard/WatchlistTab.tsx`
Note the component name, how it lists watchlist tags, and where to add the groups section.

- [ ] **Step 2: Write a light failing render test**

```tsx
// src/pages/dashboard/WatchlistGroups.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '../../i18n'
import WatchlistGroups from './WatchlistGroups'

vi.mock('../../api/client', () => ({
  listWatchlistGroups: () => Promise.resolve({ data: { groups: [{ id: 1, name: 'Pompalar', sort_order: 0, tag_count: 0, tags: [] }], ungrouped: [] } }),
  createWatchlistGroup: vi.fn(), renameWatchlistGroup: vi.fn(), deleteWatchlistGroup: vi.fn(),
  addTagToGroup: vi.fn(), removeTagFromGroup: vi.fn(),
  syncGrafana: () => Promise.resolve({ data: { written: 1, deleted: 0, errors: [] } }),
}))

describe('WatchlistGroups', () => {
  it('renders group names from the API', async () => {
    await i18n.changeLanguage('en')
    const qc = new QueryClient()
    render(<QueryClientProvider client={qc}><WatchlistGroups /></QueryClientProvider>)
    await waitFor(() => expect(screen.getByText('Pompalar')).toBeTruthy())
  })
})
```

- [ ] **Step 3: Run, verify fail**

Run: `cd scada-reporter/frontend && pnpm vitest run src/pages/dashboard/WatchlistGroups.test.tsx`
Expected: FAIL — `WatchlistGroups` component missing.

- [ ] **Step 4: Create the WatchlistGroups component**

Create `src/pages/dashboard/WatchlistGroups.tsx` — a self-contained section component (keeps WatchlistTab focused). It:
- `useQuery(['watchlist-groups'], listWatchlistGroups)`,
- renders each group (name, tag_count, rename inline, delete with confirm),
- a "+ New group" input → `createWatchlistGroup` then invalidate query,
- a "Sync to Grafana" button → `syncGrafana()` then toast using `t('synced', {written, deleted})` or `t('sync_failed')`,
- a link to `/d/scada-watchlist-groups` (opens Grafana; use `import.meta.env.VITE_GRAFANA_URL ?? 'http://localhost:3000'`).

```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  listWatchlistGroups, createWatchlistGroup, renameWatchlistGroup,
  deleteWatchlistGroup, syncGrafana,
} from '../../api/client'

const GRAFANA = (import.meta.env.VITE_GRAFANA_URL as string) ?? 'http://localhost:3000'

export default function WatchlistGroups() {
  const { t } = useTranslation('watchlistGroups')
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')
  const [msg, setMsg] = useState('')
  const { data } = useQuery({ queryKey: ['watchlist-groups'], queryFn: () => listWatchlistGroups().then((r) => r.data) })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['watchlist-groups'] })
  const create = useMutation({ mutationFn: () => createWatchlistGroup(newName), onSuccess: () => { setNewName(''); invalidate() } })
  const del = useMutation({ mutationFn: (id: number) => deleteWatchlistGroup(id), onSuccess: invalidate })
  const rename = useMutation({ mutationFn: (v: { id: number; name: string }) => renameWatchlistGroup(v.id, v.name), onSuccess: invalidate })
  const sync = useMutation({
    mutationFn: () => syncGrafana(),
    onSuccess: (r) => setMsg(t('synced', { written: r.data.written, deleted: r.data.deleted })),
    onError: () => setMsg(t('sync_failed')),
  })

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">{t('title')}</h2>
        <div className="flex items-center gap-2">
          <a href={`${GRAFANA}/d/scada-watchlist-groups`} target="_blank" rel="noreferrer"
             className="text-xs text-cyan-400 hover:underline">{t('open_dashboard')}</a>
          <button onClick={() => sync.mutate()} disabled={sync.isPending}
                  className="text-xs px-2 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
            {t('sync_grafana')}
          </button>
        </div>
      </div>
      {msg && <p className="text-xs text-gray-400">{msg}</p>}
      <div className="flex gap-2">
        <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder={t('group_name')}
               className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-white" />
        <button onClick={() => newName.trim() && create.mutate()}
                className="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-white">{t('new_group')}</button>
      </div>
      <ul className="space-y-1">
        {(data?.groups ?? []).map((g) => (
          <li key={g.id} className="flex items-center justify-between text-sm text-gray-200 px-2 py-1 rounded bg-gray-950">
            <span>{g.name} <span className="text-gray-500">({g.tag_count})</span></span>
            <span className="flex gap-2">
              <button onClick={() => { const n = prompt(t('rename'), g.name); if (n) rename.mutate({ id: g.id, name: n }) }}
                      className="text-xs text-gray-400 hover:text-white">{t('rename')}</button>
              <button onClick={() => del.mutate(g.id)} className="text-xs text-red-400 hover:text-red-300">{t('delete')}</button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 5: Render WatchlistGroups inside WatchlistTab**

In `WatchlistTab.tsx`, import and render `<WatchlistGroups />` near the top of the tab body:
```tsx
import WatchlistGroups from './WatchlistGroups'
// ... inside the returned JSX, before the watchlist table:
<WatchlistGroups />
```

- [ ] **Step 6: Run, verify pass**

Run: `cd scada-reporter/frontend && pnpm vitest run src/pages/dashboard/WatchlistGroups.test.tsx`
Expected: PASS.

- [ ] **Step 7: Typecheck + lint**

Run: `cd scada-reporter/frontend && pnpm exec tsc --noEmit && pnpm lint`
Expected: clean (no hardcoded-string / RTL guard failures — all UI text via `t()`).

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/src/pages/dashboard/WatchlistGroups.tsx scada-reporter/frontend/src/pages/dashboard/WatchlistGroups.test.tsx scada-reporter/frontend/src/pages/dashboard/WatchlistTab.tsx
git commit -m "feat(watchlist-groups): WatchlistTab group management UI"
```

---

## Task 12: Per-tag group assignment UI

**Files:**
- Modify: `scada-reporter/frontend/src/pages/dashboard/WatchlistTab.tsx`
- (uses `addTagToGroup`/`removeTagFromGroup`, `tagInGroup`)

**Interfaces:**
- Consumes: groups query, `addTagToGroup`, `removeTagFromGroup`, `tagInGroup`.
- Produces: per-watchlist-tag group chips (toggle membership). M:N — a tag shows a chip per group, filled if member.

- [ ] **Step 1: Locate the watchlist tag row render in WatchlistTab**

Run: `grep -n "map" scada-reporter/frontend/src/pages/dashboard/WatchlistTab.tsx`
Identify the row where each watchlist tag is rendered (has `tag_id`/`id`).

- [ ] **Step 2: Add group chips to each tag row**

In the tag row, render a chip per group; clicking toggles membership via mutation, then invalidate `['watchlist-groups']`:

```tsx
// near other hooks in WatchlistTab:
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listWatchlistGroups, addTagToGroup, removeTagFromGroup } from '../../api/client'
import { tagInGroup } from '../../utils/watchlistGroups'
// ...
const qc = useQueryClient()
const { data: wg } = useQuery({ queryKey: ['watchlist-groups'], queryFn: () => listWatchlistGroups().then(r => r.data) })
const toggle = useMutation({
  mutationFn: ({ gid, tagId, on }: { gid: number; tagId: number; on: boolean }) =>
    on ? removeTagFromGroup(gid, tagId) : addTagToGroup(gid, tagId),
  onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist-groups'] }),
})
// ... in each tag row (tagId = the row's tag id):
<div className="flex gap-1 flex-wrap">
  {(wg?.groups ?? []).map((g) => {
    const on = tagInGroup(g, tagId)
    return (
      <button key={g.id} onClick={() => toggle.mutate({ gid: g.id, tagId, on })}
        className={`text-[10px] px-1.5 py-0.5 rounded-full border ${on ? 'bg-cyan-900/50 border-cyan-600 text-cyan-300' : 'border-gray-700 text-gray-500'}`}>
        {g.name}
      </button>
    )
  })}
</div>
```

Adapt `tagId` to the actual field name in the row object (likely `t.id` or `row.tag_id` — confirm from Step 1).

- [ ] **Step 3: Typecheck + lint + run watchlist-related tests**

Run: `cd scada-reporter/frontend && pnpm exec tsc --noEmit && pnpm lint && pnpm vitest run src/pages/dashboard/`
Expected: clean + existing dashboard tests still pass.

- [ ] **Step 4: Commit**

```bash
git add scada-reporter/frontend/src/pages/dashboard/WatchlistTab.tsx
git commit -m "feat(watchlist-groups): per-tag group assignment chips"
```

---

## Task 13: Full verification + ship

**Files:** none (verification).

- [ ] **Step 1: Backend full suite**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest -q`
Expected: all pass (incl. new watchlist-groups + grafana-sync tests).

- [ ] **Step 2: Backend lint + types**

Run: `cd scada-reporter/backend && .venv/Scripts/ruff check app tests && .venv/Scripts/mypy app/api/watchlist_groups.py app/services/grafana_sync.py app/models/watchlist_group.py`
Expected: clean.

- [ ] **Step 3: Frontend full suite + typecheck + lint**

Run: `cd scada-reporter/frontend && pnpm exec tsc --noEmit && pnpm lint && pnpm vitest run`
Expected: all pass.

- [ ] **Step 4: Manual runtime smoke**

With backend (`:8001`) + Grafana (`:3000`) running: create a group, add a watchlist tag, click "Sync to Grafana", confirm `wl-group-<id>` dashboard appears (`curl -s -u admin:admin123 "http://localhost:3000/api/search?tag=watchlist-group"`), and the templated `scada-watchlist-groups` group dropdown lists the group.

- [ ] **Step 5: Push (dev-phase: direct to master)**

```bash
git push origin master
```

- [ ] **Step 6: Update memory**

Update `native-monitoring-stack` memory: add the `scada-watchlist-groups` templated dashboard + the `wl-group-*` generated dashboards + the `GRAFANA_*` backend settings + sync endpoint.

---

## Self-Review

- **Spec coverage:** §2 model → T1. §3 API (GET/POST/PATCH/DELETE/member/sync) → T2,T3,T4,T7. §3 remove_watchlist cascade → T5. §4a templated dashboard → T8. §4b per-group + sync + config → T6,T7. §5 frontend → T9,T10,T11,T12. §6 testing → folded into each task + T13. All covered.
- **Placeholder scan:** No TBD/TODO; every code step has concrete code.
- **Type consistency:** `build_group_dashboard(group_id,name,datasource_uid)` consistent T6↔T7; `sync_groups(groups, *, http)` consistent T7; client fn names consistent T9↔T11↔T12; `tagInGroup` T10↔T12; uid scheme `wl-group-<id>` consistent T6/T7/T8/T13; datasource uid `scadadb` throughout.
- **Risk note (frser variable):** T8 Step 2 includes a textbox fallback if query variables are unsupported.
