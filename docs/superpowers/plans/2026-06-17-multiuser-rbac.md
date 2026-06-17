# Multi-User RBAC + User-Management Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin-managed multi-user system with hybrid (role + per-user override) permissions, enforced on tag/PLC/report-template endpoints and surfaced through a "User Operations" admin menu.

**Architecture:** A new `app/core/permissions.py` defines a permission catalog, role defaults, and an `effective_permissions(user)` resolver. A `require_perm(perm)` FastAPI dependency gates write endpoints. A new `app/api/users.py` provides admin-only user CRUD. The frontend `AuthContext` exposes effective permissions and a `can()` helper; a new admin-only `Users` page manages users; existing write buttons are gated by `can()`.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, pytest-asyncio, bcrypt/jose JWT, React 19 + TanStack Query, react-i18next, Vitest + Testing Library.

## Global Constraints

- Permission catalog (exact keys): `tag:create`, `plc:manage`, `report_template:create`, `report_template:edit`, `report_template:delete`.
- Role defaults: admin = all + user-management; operator = all except `report_template:delete`; viewer = none.
- `admin` role always has every permission and user-management; overrides never restrict admin.
- Override storage: `User.permission_overrides` JSON column, `{ "<perm_key>": bool }`, default `{}`.
- User-management is admin-only (`require_role("admin")`), not a catalog permission.
- Last-admin invariant: an action that would leave zero active admins is rejected with HTTP 400. Admin cannot delete self.
- All new user-facing strings are i18n (en/tr/ru/de) under a new `users` namespace; parity test must pass.
- Backend tests are pytest-asyncio; auth in API tests is injected by overriding `get_current_user` via `app.dependency_overrides` (see `tests/test_excel_templates_api.py`).
- Run backend tests from `scada-reporter/backend/` with `.venv` active: `python -m pytest`.
- Run frontend tests from `scada-reporter/frontend/`: `pnpm test`.

---

### Task 1: Permission core module

**Files:**
- Create: `scada-reporter/backend/app/core/permissions.py`
- Test: `scada-reporter/backend/tests/test_permissions.py`

**Interfaces:**
- Consumes: `app.models.user.User` (has `.role: str` and `.permission_overrides: dict`).
- Produces:
  - `ALL_PERMISSIONS: tuple[str, ...]`
  - `ROLE_DEFAULTS: dict[str, dict[str, bool]]`
  - `effective_permissions(user: User) -> set[str]`
  - `user_can(user: User, perm: str) -> bool`
  - Perm constants: `PERM_TAG_CREATE`, `PERM_PLC_MANAGE`, `PERM_REPORT_CREATE`, `PERM_REPORT_EDIT`, `PERM_REPORT_DELETE`.

> Note: Task 1 references `user.permission_overrides`, which the model gains in Task 2. Task 1 tests construct `User(...)` objects in-memory without a DB; `permission_overrides` defaults to `{}` via the model default added in Task 2. If executing Task 1 before Task 2, the test fixtures below pass `permission_overrides={}` explicitly, so they do not depend on the column default.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_permissions.py`:

```python
from types import SimpleNamespace

from app.core import permissions as P


def _user(role: str, overrides: dict | None = None):
    # SimpleNamespace stands in for the User ORM object — only .role and
    # .permission_overrides are read by the resolver.
    return SimpleNamespace(role=role, permission_overrides=overrides or {})


def test_catalog_keys_exact():
    assert set(P.ALL_PERMISSIONS) == {
        "tag:create",
        "plc:manage",
        "report_template:create",
        "report_template:edit",
        "report_template:delete",
    }


def test_admin_has_all_permissions():
    assert P.effective_permissions(_user("admin")) == set(P.ALL_PERMISSIONS)


def test_admin_overrides_ignored():
    # Even an override that revokes is ignored for admin.
    u = _user("admin", {"plc:manage": False})
    assert P.user_can(u, "plc:manage") is True


def test_operator_defaults():
    u = _user("operator")
    assert P.user_can(u, "tag:create") is True
    assert P.user_can(u, "plc:manage") is True
    assert P.user_can(u, "report_template:create") is True
    assert P.user_can(u, "report_template:edit") is True
    assert P.user_can(u, "report_template:delete") is False


def test_viewer_defaults_none():
    u = _user("viewer")
    assert P.effective_permissions(u) == set()


def test_override_grants_extra():
    u = _user("operator", {"report_template:delete": True})
    assert P.user_can(u, "report_template:delete") is True


def test_override_revokes():
    u = _user("operator", {"plc:manage": False})
    assert P.user_can(u, "plc:manage") is False


def test_unknown_override_key_ignored():
    u = _user("operator", {"bogus:perm": True})
    assert P.user_can(u, "bogus:perm") is False


def test_unknown_role_has_no_permissions():
    u = _user("ghost")
    assert P.effective_permissions(u) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_permissions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.permissions'`.

- [ ] **Step 3: Write minimal implementation**

Create `scada-reporter/backend/app/core/permissions.py`:

```python
"""Yetki kataloğu ve efektif yetki çözümleyici (rol + kullanıcı override)."""

from __future__ import annotations

PERM_TAG_CREATE = "tag:create"
PERM_PLC_MANAGE = "plc:manage"
PERM_REPORT_CREATE = "report_template:create"
PERM_REPORT_EDIT = "report_template:edit"
PERM_REPORT_DELETE = "report_template:delete"

ALL_PERMISSIONS: tuple[str, ...] = (
    PERM_TAG_CREATE,
    PERM_PLC_MANAGE,
    PERM_REPORT_CREATE,
    PERM_REPORT_EDIT,
    PERM_REPORT_DELETE,
)

ROLE_DEFAULTS: dict[str, dict[str, bool]] = {
    "admin": {p: True for p in ALL_PERMISSIONS},
    "operator": {
        PERM_TAG_CREATE: True,
        PERM_PLC_MANAGE: True,
        PERM_REPORT_CREATE: True,
        PERM_REPORT_EDIT: True,
        PERM_REPORT_DELETE: False,
    },
    "viewer": {p: False for p in ALL_PERMISSIONS},
}


def effective_permissions(user) -> set[str]:
    """User'ın efektif yetki kümesi. admin her zaman tam set."""
    if user.role == "admin":
        return set(ALL_PERMISSIONS)
    base = dict(ROLE_DEFAULTS.get(user.role, {p: False for p in ALL_PERMISSIONS}))
    overrides = getattr(user, "permission_overrides", None) or {}
    for key, value in overrides.items():
        if key in ALL_PERMISSIONS:
            base[key] = bool(value)
    return {perm for perm, granted in base.items() if granted}


def user_can(user, perm: str) -> bool:
    return perm in effective_permissions(user)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_permissions.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/core/permissions.py scada-reporter/backend/tests/test_permissions.py
git commit -m "feat(rbac): permission catalog + effective-permission resolver"
```

---

### Task 2: User model `permission_overrides` column + migration

**Files:**
- Modify: `scada-reporter/backend/app/models/user.py`
- Create: `scada-reporter/backend/alembic/versions/<rev>_add_permission_overrides.py` (generated)
- Test: `scada-reporter/backend/tests/test_user_model.py`

**Interfaces:**
- Produces: `User.permission_overrides: Mapped[dict]` (JSON, default `{}`, non-null).

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_user_model.py`:

```python
import pytest

from app.models.user import User


@pytest.mark.asyncio
async def test_permission_overrides_defaults_to_empty_dict(db_session):
    u = User(
        username="ovr",
        email="ovr@scada.local",
        hashed_password="x",
        role="operator",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    assert u.permission_overrides == {}


@pytest.mark.asyncio
async def test_permission_overrides_roundtrip(db_session):
    u = User(
        username="ovr2",
        email="ovr2@scada.local",
        hashed_password="x",
        role="operator",
        permission_overrides={"plc:manage": False},
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    assert u.permission_overrides == {"plc:manage": False}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_user_model.py -v`
Expected: FAIL with `TypeError: 'permission_overrides' is an invalid keyword argument for User` (or AttributeError on assert).

- [ ] **Step 3: Write minimal implementation**

Modify `scada-reporter/backend/app/models/user.py`. Add `JSON` to the sqlalchemy import and add the column after `language`:

```python
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(50), default="operator")  # admin, operator, viewer
    language: Mapped[str] = mapped_column(
        String(5), server_default="en", default="en", nullable=False
    )
    permission_overrides: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_user_model.py -v`
Expected: PASS (2 passed). (Test DB tables are created from models via `Base.metadata.create_all`, so no migration is needed for tests.)

- [ ] **Step 5: Generate the Alembic migration (for prod Postgres)**

Run from `scada-reporter/backend/` with backend DB env set:

```bash
just makemigration msg="add user permission_overrides"
```

Open the generated file under `alembic/versions/`. Ensure `upgrade()` adds the column with a server default so existing rows backfill, and `downgrade()` drops it:

```python
def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "permission_overrides",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "permission_overrides")
```

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/models/user.py scada-reporter/backend/tests/test_user_model.py scada-reporter/backend/alembic/versions/
git commit -m "feat(rbac): add User.permission_overrides column + migration"
```

---

### Task 3: `require_perm` dependency

**Files:**
- Modify: `scada-reporter/backend/app/api/auth.py`
- Test: `scada-reporter/backend/tests/test_require_perm.py`

**Interfaces:**
- Consumes: `app.core.permissions.user_can`, `get_current_user`.
- Produces: `require_perm(perm: str)` — returns an async dependency that yields the `User` when `user_can(user, perm)` else raises 403.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_require_perm.py`:

```python
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.auth import require_perm


def _user(role, overrides=None):
    return SimpleNamespace(role=role, permission_overrides=overrides or {})


@pytest.mark.asyncio
async def test_require_perm_allows_permitted_user():
    dep = require_perm("plc:manage")
    user = _user("operator")
    assert await dep(user=user) is user


@pytest.mark.asyncio
async def test_require_perm_blocks_unpermitted_user():
    dep = require_perm("report_template:delete")
    user = _user("operator")  # operator lacks delete
    with pytest.raises(HTTPException) as exc:
        await dep(user=user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_perm_admin_always_allowed():
    dep = require_perm("report_template:delete")
    assert await dep(user=_user("admin")) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_require_perm.py -v`
Expected: FAIL with `ImportError: cannot import name 'require_perm'`.

- [ ] **Step 3: Write minimal implementation**

In `scada-reporter/backend/app/api/auth.py`, add the import near the other app imports:

```python
from app.core.permissions import user_can
```

Then add, directly after the existing `require_role` function:

```python
def require_perm(perm: str):
    async def _check(user: User = Depends(get_current_user)):
        if not user_can(user, perm):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetki yok")
        return user

    return _check
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_require_perm.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/auth.py scada-reporter/backend/tests/test_require_perm.py
git commit -m "feat(rbac): require_perm dependency"
```

---

### Task 4: Enforce permissions on write endpoints + close open registration

**Files:**
- Modify: `scada-reporter/backend/app/api/tags.py` (create endpoint)
- Modify: `scada-reporter/backend/app/api/plc.py` (create/update/delete)
- Modify: `scada-reporter/backend/app/api/advanced_reports.py` (template create/update/delete)
- Modify: `scada-reporter/backend/app/api/excel_templates.py` (create/delete)
- Modify: `scada-reporter/backend/app/api/auth.py` (`/register` admin-gate)
- Test: `scada-reporter/backend/tests/test_permission_enforcement.py`

**Interfaces:**
- Consumes: `require_perm` (Task 3), `require_role` (existing).
- Produces: write endpoints return 403 for users lacking the matching permission.

Permission mapping:
- `POST /api/tags/` → `require_perm("tag:create")`
- `POST /api/plc/`, `PATCH /api/plc/{name}`, `DELETE /api/plc/{name}` → `require_perm("plc:manage")`
- `POST /api/advanced-reports/templates` → `require_perm("report_template:create")`
- `PUT /api/advanced-reports/templates/{id}` → `require_perm("report_template:edit")`
- `DELETE /api/advanced-reports/templates/{id}` → `require_perm("report_template:delete")`
- `POST /api/excel-templates` → `require_perm("report_template:create")`
- `DELETE /api/excel-templates/{id}` → `require_perm("report_template:delete")`
- `POST /api/auth/register` → `require_role("admin")`

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_permission_enforcement.py`:

```python
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.api.auth import get_current_user
from app.main import app


def _as_user(role, overrides=None):
    return SimpleNamespace(
        id=1, username=role, role=role, permission_overrides=overrides or {}, is_active=True
    )


@pytest_asyncio.fixture
def as_role():
    def _set(role, overrides=None):
        app.dependency_overrides[get_current_user] = lambda: _as_user(role, overrides)

    yield _set
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_viewer_cannot_create_tag(client, as_role):
    as_role("viewer")
    resp = await client.post("/api/tags/", json={"name": "T1"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_operator_can_create_plc(client, as_role):
    as_role("operator")
    resp = await client.post("/api/plc/", json={"name": "PLC-X", "ip": "10.0.0.9"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_viewer_cannot_create_plc(client, as_role):
    as_role("viewer")
    resp = await client.post("/api/plc/", json={"name": "PLC-Y"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_operator_cannot_delete_report_template(client, as_role):
    as_role("operator")
    resp = await client.delete("/api/advanced-reports/templates/999")
    # operator lacks report_template:delete -> 403 BEFORE the 404 lookup
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_operator_with_override_can_delete_report_template(client, as_role):
    as_role("operator", {"report_template:delete": True})
    resp = await client.delete("/api/advanced-reports/templates/999")
    # permission granted -> passes guard, then 404 (no such template)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_admin_cannot_register(client, as_role):
    as_role("operator")
    resp = await client.post(
        "/api/auth/register",
        json={"username": "x", "email": "x@x.com", "password": "secret1"},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_permission_enforcement.py -v`
Expected: FAIL — e.g. `test_viewer_cannot_create_plc` returns 201 (PLC currently unguarded), `test_non_admin_cannot_register` returns 201.

- [ ] **Step 3: Write minimal implementation**

In `scada-reporter/backend/app/api/tags.py`, change the `create_tag` guard:
```python
    _=Depends(require_perm("tag:create")),
```
(Ensure `require_perm` is imported: `from app.api.auth import require_perm` — add alongside existing `require_role` import.)

In `scada-reporter/backend/app/api/plc.py`, add the import and change three guards:
```python
from app.api.auth import get_current_user, require_perm
```
- `create_plc`: `_=Depends(require_perm("plc:manage")),`
- `update_plc`: `_=Depends(require_perm("plc:manage")),`
- `delete_plc`: `_=Depends(require_perm("plc:manage")),`

In `scada-reporter/backend/app/api/advanced_reports.py`, add `require_perm` to the import from `app.api.auth` and change three template guards:
- `create_template`: `user: User = Depends(require_perm("report_template:create")),`
- `update_template`: `_: User = Depends(require_perm("report_template:edit")),`
- `delete_template`: `_: User = Depends(require_perm("report_template:delete")),`

In `scada-reporter/backend/app/api/excel_templates.py`, add `require_perm`:
```python
from app.api.auth import get_current_user, require_perm
```
- `create_template`: `user=Depends(require_perm("report_template:create")),`
- `delete_template`: `user=Depends(require_perm("report_template:delete")),`

In `scada-reporter/backend/app/api/auth.py`, gate registration. Change the `register` signature to require admin:
```python
@router.post("/register", status_code=201)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_permission_enforcement.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Run the full suite to catch regressions**

Run: `python -m pytest -q`
Expected: PASS. If any pre-existing test posts to `/api/auth/register` without an admin override, update it to inject an admin via `app.dependency_overrides[get_current_user]` (mirror the fixture above). Note any such fix in the commit body.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/api/ scada-reporter/backend/tests/test_permission_enforcement.py
git commit -m "feat(rbac): enforce perms on tag/plc/report writes, close open registration"
```

---

### Task 5: `/auth/me` exposes permissions + self password change

**Files:**
- Modify: `scada-reporter/backend/app/api/auth.py`
- Test: `scada-reporter/backend/tests/test_auth_me.py`

**Interfaces:**
- Consumes: `effective_permissions`, `verify_password`, `hash_password`.
- Produces:
  - `GET /api/auth/me` response gains `permissions: list[str]` (sorted).
  - `PATCH /api/auth/me` accepts optional `language`, and optional `current_password` + `new_password` pair for self password change. Wrong `current_password` → 400.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_auth_me.py`:

```python
import pytest
import pytest_asyncio

from app.api.auth import get_current_user
from app.core.security import hash_password, verify_password
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def operator(db_session):
    u = User(
        username="op1",
        email="op1@scada.local",
        hashed_password=hash_password("oldpass"),
        role="operator",
        permission_overrides={},
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    app.dependency_overrides[get_current_user] = lambda: u
    yield u
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_me_returns_effective_permissions(client, operator):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    perms = resp.json()["permissions"]
    assert "tag:create" in perms
    assert "report_template:delete" not in perms  # operator default


@pytest.mark.asyncio
async def test_self_password_change_succeeds(client, operator, db_session):
    resp = await client.patch(
        "/api/auth/me",
        json={"current_password": "oldpass", "new_password": "newpass1"},
    )
    assert resp.status_code == 200
    await db_session.refresh(operator)
    assert verify_password("newpass1", operator.hashed_password)


@pytest.mark.asyncio
async def test_self_password_change_wrong_current(client, operator):
    resp = await client.patch(
        "/api/auth/me",
        json={"current_password": "WRONG", "new_password": "newpass1"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth_me.py -v`
Expected: FAIL — `permissions` key missing; password fields rejected/ignored.

- [ ] **Step 3: Write minimal implementation**

In `scada-reporter/backend/app/api/auth.py`:

Add imports:
```python
from app.core.permissions import effective_permissions, user_can  # user_can already added in Task 3
```

Replace the `UserUpdate` schema and the `me` / `update_me` handlers:

```python
class UserUpdate(BaseModel):
    language: Literal["en", "tr", "ru", "de"] | None = None
    current_password: str | None = None
    new_password: str | None = None


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auth_me.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/auth.py scada-reporter/backend/tests/test_auth_me.py
git commit -m "feat(rbac): /auth/me exposes effective permissions + self password change"
```

---

### Task 6: User-management API (`app/api/users.py`)

**Files:**
- Create: `scada-reporter/backend/app/api/users.py`
- Modify: `scada-reporter/backend/app/main.py` (register router)
- Test: `scada-reporter/backend/tests/test_users_api.py`

**Interfaces:**
- Consumes: `require_role("admin")`, `effective_permissions`, `hash_password`, `User`.
- Produces router `users.router` (prefix `/users`) with:
  - `GET /api/users/` → `list[UserOut]`
  - `POST /api/users/` → `UserOut` (201)
  - `PATCH /api/users/{user_id}` → `UserOut`
  - `POST /api/users/{user_id}/password` → `{ "ok": true }`
  - `DELETE /api/users/{user_id}` → 204
  - `UserOut` fields: `id, username, email, full_name, role, is_active, permission_overrides, permissions`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_users_api.py`:

```python
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.api.auth import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.user import User


def _admin():
    return SimpleNamespace(
        id=1, username="admin", role="admin", permission_overrides={}, is_active=True
    )


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    yield
    await db_session.execute(delete(User))
    await db_session.commit()


@pytest_asyncio.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = _admin
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def seed_admin(db_session):
    a = User(
        username="root",
        email="root@scada.local",
        hashed_password=hash_password("x"),
        role="admin",
        permission_overrides={},
        is_active=True,
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


@pytest.mark.asyncio
async def test_create_and_list_user(client, as_admin):
    resp = await client.post(
        "/api/users/",
        json={
            "username": "bob",
            "email": "bob@scada.local",
            "password": "secret1",
            "full_name": "Bob",
            "role": "operator",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "bob"
    assert "report_template:delete" not in body["permissions"]

    lst = await client.get("/api/users/")
    assert lst.status_code == 200
    assert any(u["username"] == "bob" for u in lst.json())


@pytest.mark.asyncio
async def test_create_duplicate_username_409(client, as_admin):
    payload = {"username": "dup", "email": "d1@scada.local", "password": "secret1"}
    assert (await client.post("/api/users/", json=payload)).status_code == 201
    payload2 = {"username": "dup", "email": "d2@scada.local", "password": "secret1"}
    assert (await client.post("/api/users/", json=payload2)).status_code == 409


@pytest.mark.asyncio
async def test_patch_role_and_overrides(client, as_admin):
    created = (
        await client.post(
            "/api/users/",
            json={"username": "carol", "email": "c@scada.local", "password": "secret1"},
        )
    ).json()
    resp = await client.patch(
        f"/api/users/{created['id']}",
        json={"role": "operator", "permission_overrides": {"report_template:delete": True}},
    )
    assert resp.status_code == 200
    assert "report_template:delete" in resp.json()["permissions"]


@pytest.mark.asyncio
async def test_reset_password(client, as_admin):
    created = (
        await client.post(
            "/api/users/",
            json={"username": "dave", "email": "dv@scada.local", "password": "secret1"},
        )
    ).json()
    resp = await client.post(
        f"/api/users/{created['id']}/password", json={"password": "newsecret"}
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_user(client, as_admin):
    created = (
        await client.post(
            "/api/users/",
            json={"username": "erin", "email": "e@scada.local", "password": "secret1"},
        )
    ).json()
    resp = await client.delete(f"/api/users/{created['id']}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cannot_delete_last_active_admin(client, as_admin, seed_admin):
    # seed_admin ("root") is the only DB admin. _admin override (id=1) is not in DB.
    resp = await client.delete(f"/api/users/{seed_admin.id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cannot_demote_last_active_admin(client, as_admin, seed_admin):
    resp = await client.patch(f"/api/users/{seed_admin.id}", json={"role": "operator"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2, username="op", role="operator", permission_overrides={}, is_active=True
    )
    try:
        resp = await client.get("/api/users/")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_users_api.py -v`
Expected: FAIL with 404s (router not registered).

- [ ] **Step 3: Write minimal implementation**

Create `scada-reporter/backend/app/api/users.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.core.database import get_db
from app.core.permissions import effective_permissions
from app.core.security import hash_password
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    permission_overrides: dict
    permissions: list[str]


class UserCreateIn(BaseModel):
    username: str
    email: str
    password: str
    full_name: str = ""
    role: str = "operator"
    permission_overrides: dict = {}


class UserPatchIn(BaseModel):
    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    permission_overrides: dict | None = None


class PasswordIn(BaseModel):
    password: str


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
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


async def _guard_last_admin(db: AsyncSession, target: User, *, removing: bool, new_role=None,
                            new_active=None) -> None:
    """target admin'i pasifleştiren/silen/düşüren işlem son aktif admin'i
    yok edecekse 400."""
    if target.role != "admin" or not target.is_active:
        return
    demoted = removing or (new_role is not None and new_role != "admin") or (
        new_active is False
    )
    if demoted and await _active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Son aktif admin kaldirilamaz")


@router.get("/", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(require_role("admin"))):
    result = await db.execute(select(User).order_by(User.username))
    return [_to_out(u) for u in result.scalars().all()]


@router.post("/", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreateIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
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
    await db.commit()
    await db.refresh(user)
    return _to_out(user)


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: int,
    data: UserPatchIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")
    await _guard_last_admin(
        db, user, removing=False, new_role=data.role, new_active=data.is_active
    )
    if data.email is not None:
        user.email = data.email
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.permission_overrides is not None:
        user.permission_overrides = data.permission_overrides
    await db.commit()
    await db.refresh(user)
    return _to_out(user)


@router.post("/{user_id}/password")
async def reset_password(
    user_id: int,
    data: PasswordIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")
    user.hashed_password = hash_password(data.password)
    await db.commit()
    return {"ok": True}


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz")
    await _guard_last_admin(db, user, removing=True)
    await db.delete(user)
    await db.commit()
```

Register the router in `scada-reporter/backend/app/main.py`. Add `users` to the `from app.api import (...)` block and add after the auth include:

```python
app.include_router(users.router, prefix="/api")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_users_api.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Run full backend suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/api/users.py scada-reporter/backend/app/main.py scada-reporter/backend/tests/test_users_api.py
git commit -m "feat(rbac): admin user-management API with last-admin guard"
```

---

### Task 7: Frontend AuthContext permissions + `can()` + API client

**Files:**
- Modify: `scada-reporter/frontend/src/context/AuthContext.tsx`
- Modify: `scada-reporter/frontend/src/api/client.ts`
- Test: `scada-reporter/frontend/src/context/AuthContext.test.tsx`

**Interfaces:**
- Produces:
  - `AuthContext` `user.permissions: string[]`; context exposes `can(perm: string): boolean` (admin always true).
  - `client.ts`: `getMe` return type gains `permissions: string[]`; user-management functions `listUsers`, `createUser`, `patchUser`, `resetUserPassword`, `deleteUser`, and types `ManagedUser`, `UserCreatePayload`, `UserPatchPayload`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/frontend/src/context/AuthContext.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'

vi.mock('../api/client', () => ({
  getMe: vi.fn(),
  login: vi.fn(),
}))

import { getMe } from '../api/client'

function Probe() {
  const { can } = useAuth()
  return <div>plc:{String(can('plc:manage'))} del:{String(can('report_template:delete'))}</div>
}

describe('AuthContext can()', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'tok')
    vi.mocked(getMe).mockResolvedValue({
      data: {
        id: 1, username: 'op', role: 'operator', full_name: '', language: 'en',
        permissions: ['tag:create', 'plc:manage'],
      },
    } as never)
  })

  it('grants listed perms and denies others', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByText(/plc:true/)).toBeInTheDocument())
    expect(screen.getByText(/del:false/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/context/AuthContext.test.tsx`
Expected: FAIL — `can` is not a function / not exported by context.

- [ ] **Step 3: Write minimal implementation**

In `scada-reporter/frontend/src/context/AuthContext.tsx`, extend the `User` interface and context:

```tsx
interface User { id: number; username: string; role: string; full_name: string; language: string; permissions: string[] }

interface AuthCtx {
  user: User | null
  loading: boolean
  login: (u: string, p: string) => Promise<void>
  logout: () => void
  can: (perm: string) => boolean
}
```

Inside `AuthProvider`, add the helper and include it in the provider value:

```tsx
  const can = (perm: string) =>
    user?.role === 'admin' || !!user?.permissions?.includes(perm)

  return <Ctx.Provider value={{ user, loading, login, logout, can }}>{children}</Ctx.Provider>
```

In `scada-reporter/frontend/src/api/client.ts`, update `getMe`/`updateMe` return types to include `permissions: string[]` and append user-management functions at the end of the Auth section:

```ts
export const getMe = () => api.get<{ id: number; username: string; role: string; full_name: string; language: string; permissions: string[] }>('/auth/me')

export interface ManagedUser {
  id: number; username: string; email: string; full_name: string
  role: string; is_active: boolean
  permission_overrides: Record<string, boolean>; permissions: string[]
}
export interface UserCreatePayload {
  username: string; email: string; password: string
  full_name?: string; role?: string; permission_overrides?: Record<string, boolean>
}
export interface UserPatchPayload {
  email?: string; full_name?: string; role?: string
  is_active?: boolean; permission_overrides?: Record<string, boolean>
}
export const listUsers = () => api.get<ManagedUser[]>('/users/')
export const createUser = (data: UserCreatePayload) => api.post<ManagedUser>('/users/', data)
export const patchUser = (id: number, data: UserPatchPayload) => api.patch<ManagedUser>(`/users/${id}`, data)
export const resetUserPassword = (id: number, password: string) => api.post(`/users/${id}/password`, { password })
export const deleteUser = (id: number) => api.delete(`/users/${id}`)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/context/AuthContext.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/context/AuthContext.tsx scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/context/AuthContext.test.tsx
git commit -m "feat(rbac): AuthContext.can() + user-management API client"
```

---

### Task 8: Users page + admin nav link + i18n namespace

**Files:**
- Create: `scada-reporter/frontend/src/pages/Users.tsx`
- Create: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de}/users.json`
- Modify: `scada-reporter/frontend/src/i18n/index.ts` (register `users` namespace)
- Modify: `scada-reporter/frontend/src/App.tsx` (route)
- Modify: `scada-reporter/frontend/src/components/Layout.tsx` (admin-only nav link)
- Modify: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de}/common.json` (add `nav_users` key)
- Test: `scada-reporter/frontend/src/pages/Users.test.tsx`

**Interfaces:**
- Consumes: `listUsers`, `createUser`, `patchUser`, `resetUserPassword`, `deleteUser`, `ManagedUser` (Task 7); `useAuth().user.role`.
- Produces: `/users` route; "User Operations" nav entry shown only when `role === 'admin'`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/frontend/src/pages/Users.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Users from './Users'

vi.mock('../api/client', () => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  patchUser: vi.fn(),
  resetUserPassword: vi.fn(),
  deleteUser: vi.fn(),
}))
import { listUsers } from '../api/client'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('Users page', () => {
  beforeEach(() => {
    vi.mocked(listUsers).mockResolvedValue({
      data: [
        { id: 1, username: 'admin', email: 'a@a', full_name: 'Admin', role: 'admin',
          is_active: true, permission_overrides: {}, permissions: [] },
      ],
    } as never)
  })

  it('renders the user list', async () => {
    wrap(<Users />)
    await waitFor(() => expect(screen.getByText('admin')).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/pages/Users.test.tsx`
Expected: FAIL — cannot resolve `./Users`.

- [ ] **Step 3: Create the i18n files**

Create `scada-reporter/frontend/src/i18n/locales/en/users.json`:
```json
{
  "title": "User Operations",
  "new_user": "New User",
  "username": "Username",
  "email": "Email",
  "full_name": "Full Name",
  "password": "Password",
  "role": "Role",
  "role_admin": "Admin",
  "role_operator": "Operator",
  "role_viewer": "Viewer",
  "active": "Active",
  "permissions": "Permissions",
  "overrides": "Permission Overrides",
  "perm_tag_create": "Create tags",
  "perm_plc_manage": "Manage PLCs",
  "perm_report_create": "Create report templates",
  "perm_report_edit": "Edit report templates",
  "perm_report_delete": "Delete report templates",
  "edit": "Edit",
  "save": "Save",
  "cancel": "Cancel",
  "delete": "Delete",
  "reset_password": "Reset Password",
  "create": "Create",
  "confirm_delete": "Delete this user?",
  "last_admin_error": "Cannot remove the last active admin"
}
```

Create `scada-reporter/frontend/src/i18n/locales/tr/users.json`:
```json
{
  "title": "Kullanıcı İşlemleri",
  "new_user": "Yeni Kullanıcı",
  "username": "Kullanıcı Adı",
  "email": "E-posta",
  "full_name": "Ad Soyad",
  "password": "Şifre",
  "role": "Rol",
  "role_admin": "Yönetici",
  "role_operator": "Operatör",
  "role_viewer": "İzleyici",
  "active": "Aktif",
  "permissions": "Yetkiler",
  "overrides": "Yetki Geçersiz Kılmaları",
  "perm_tag_create": "Tag ekleme",
  "perm_plc_manage": "PLC yönetimi",
  "perm_report_create": "Rapor şablonu oluşturma",
  "perm_report_edit": "Rapor şablonu düzenleme",
  "perm_report_delete": "Rapor şablonu silme",
  "edit": "Düzenle",
  "save": "Kaydet",
  "cancel": "İptal",
  "delete": "Sil",
  "reset_password": "Şifre Sıfırla",
  "create": "Oluştur",
  "confirm_delete": "Bu kullanıcı silinsin mi?",
  "last_admin_error": "Son aktif yönetici kaldırılamaz"
}
```

Create `scada-reporter/frontend/src/i18n/locales/ru/users.json`:
```json
{
  "title": "Управление пользователями",
  "new_user": "Новый пользователь",
  "username": "Имя пользователя",
  "email": "Эл. почта",
  "full_name": "Полное имя",
  "password": "Пароль",
  "role": "Роль",
  "role_admin": "Администратор",
  "role_operator": "Оператор",
  "role_viewer": "Наблюдатель",
  "active": "Активен",
  "permissions": "Права",
  "overrides": "Переопределения прав",
  "perm_tag_create": "Создание тегов",
  "perm_plc_manage": "Управление ПЛК",
  "perm_report_create": "Создание шаблонов отчётов",
  "perm_report_edit": "Редактирование шаблонов отчётов",
  "perm_report_delete": "Удаление шаблонов отчётов",
  "edit": "Изменить",
  "save": "Сохранить",
  "cancel": "Отмена",
  "delete": "Удалить",
  "reset_password": "Сбросить пароль",
  "create": "Создать",
  "confirm_delete": "Удалить этого пользователя?",
  "last_admin_error": "Нельзя удалить последнего активного администратора"
}
```

Create `scada-reporter/frontend/src/i18n/locales/de/users.json`:
```json
{
  "title": "Benutzerverwaltung",
  "new_user": "Neuer Benutzer",
  "username": "Benutzername",
  "email": "E-Mail",
  "full_name": "Vollständiger Name",
  "password": "Passwort",
  "role": "Rolle",
  "role_admin": "Administrator",
  "role_operator": "Operator",
  "role_viewer": "Betrachter",
  "active": "Aktiv",
  "permissions": "Berechtigungen",
  "overrides": "Berechtigungs-Überschreibungen",
  "perm_tag_create": "Tags erstellen",
  "perm_plc_manage": "SPS verwalten",
  "perm_report_create": "Berichtsvorlagen erstellen",
  "perm_report_edit": "Berichtsvorlagen bearbeiten",
  "perm_report_delete": "Berichtsvorlagen löschen",
  "edit": "Bearbeiten",
  "save": "Speichern",
  "cancel": "Abbrechen",
  "delete": "Löschen",
  "reset_password": "Passwort zurücksetzen",
  "create": "Erstellen",
  "confirm_delete": "Diesen Benutzer löschen?",
  "last_admin_error": "Der letzte aktive Administrator kann nicht entfernt werden"
}
```

Add the `nav_users` key to each `common.json` (en/tr/ru/de) — match the existing JSON shape, inserting near the other `nav_*` keys:
- en: `"nav_users": "User Operations",`
- tr: `"nav_users": "Kullanıcı İşlemleri",`
- ru: `"nav_users": "Управление пользователями",`
- de: `"nav_users": "Benutzerverwaltung",`

- [ ] **Step 4: Register the `users` namespace**

In `scada-reporter/frontend/src/i18n/index.ts`:
- Add imports:
```ts
import enUsers from './locales/en/users.json'
import trUsers from './locales/tr/users.json'
import ruUsers from './locales/ru/users.json'
import deUsers from './locales/de/users.json'
```
- Add `users:` to each language's resource object, e.g. `en: { ..., metrics: enMetrics, users: enUsers }` (and tr/ru/de equivalently).
- Add `'users'` to the `ns: [...]` array.

- [ ] **Step 5: Create the Users page**

Create `scada-reporter/frontend/src/pages/Users.tsx`:

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listUsers, createUser, patchUser, resetUserPassword, deleteUser,
  type ManagedUser, type UserCreatePayload,
} from '../api/client'

const PERM_KEYS = [
  ['tag:create', 'perm_tag_create'],
  ['plc:manage', 'perm_plc_manage'],
  ['report_template:create', 'perm_report_create'],
  ['report_template:edit', 'perm_report_edit'],
  ['report_template:delete', 'perm_report_delete'],
] as const

const ROLES = ['admin', 'operator', 'viewer'] as const

const EMPTY: UserCreatePayload = {
  username: '', email: '', password: '', full_name: '', role: 'operator', permission_overrides: {},
}

export default function Users() {
  const { t } = useTranslation('users')
  const qc = useQueryClient()
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => listUsers().then((r) => r.data) })
  const [form, setForm] = useState<UserCreatePayload>(EMPTY)
  const [editing, setEditing] = useState<ManagedUser | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['users'] })
  const createMut = useMutation({ mutationFn: createUser, onSuccess: () => { invalidate(); setForm(EMPTY) } })
  const patchMut = useMutation({
    mutationFn: (v: { id: number; data: Parameters<typeof patchUser>[1] }) => patchUser(v.id, v.data),
    onSuccess: () => { invalidate(); setEditing(null) },
  })
  const delMut = useMutation({ mutationFn: deleteUser, onSuccess: invalidate })

  const toggleOverride = (target: UserCreatePayload | ManagedUser, key: string, set: (o: Record<string, boolean>) => void) => {
    const cur = { ...(target.permission_overrides || {}) }
    if (key in cur) delete cur[key]
    else cur[key] = true
    set(cur)
  }

  return (
    <div className="p-6 text-gray-200">
      <h1 className="text-xl font-semibold mb-4">{t('title')}</h1>

      {/* Create form */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 mb-6 grid gap-2 max-w-xl">
        <h2 className="font-medium">{t('new_user')}</h2>
        <input className="bg-gray-800 px-2 py-1 rounded" placeholder={t('username')} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input className="bg-gray-800 px-2 py-1 rounded" placeholder={t('email')} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <input className="bg-gray-800 px-2 py-1 rounded" placeholder={t('full_name')} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        <input className="bg-gray-800 px-2 py-1 rounded" type="password" placeholder={t('password')} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <select className="bg-gray-800 px-2 py-1 rounded" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {ROLES.map((r) => <option key={r} value={r}>{t(`role_${r}`)}</option>)}
        </select>
        <div className="text-sm text-gray-400">{t('overrides')}</div>
        {PERM_KEYS.map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={key in (form.permission_overrides || {})} onChange={() => toggleOverride(form, key, (o) => setForm({ ...form, permission_overrides: o }))} />
            {t(label)}
          </label>
        ))}
        <button className="bg-blue-600 px-3 py-1.5 rounded mt-2 disabled:opacity-50" disabled={!form.username || !form.password} onClick={() => createMut.mutate(form)}>{t('create')}</button>
      </div>

      {/* User table */}
      <table className="w-full text-sm">
        <thead className="text-gray-400 text-left">
          <tr><th className="py-2">{t('username')}</th><th>{t('full_name')}</th><th>{t('role')}</th><th>{t('active')}</th><th>{t('permissions')}</th><th /></tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-t border-gray-800">
              <td className="py-2">{u.username}</td>
              <td>{u.full_name}</td>
              <td>{t(`role_${u.role}`)}</td>
              <td>{u.is_active ? '✓' : '—'}</td>
              <td className="text-gray-500 text-xs">{u.permissions.join(', ')}</td>
              <td className="text-right space-x-2">
                <button className="text-blue-400" onClick={() => setEditing(u)}>{t('edit')}</button>
                <button className="text-amber-400" onClick={() => { const p = prompt(t('reset_password')); if (p) resetUserPassword(u.id, p) }}>{t('reset_password')}</button>
                <button className="text-red-400" onClick={() => { if (confirm(t('confirm_delete'))) delMut.mutate(u.id) }}>{t('delete')}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Edit modal */}
      {editing && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center" onClick={() => setEditing(null)}>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 grid gap-2 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <h2 className="font-medium">{editing.username}</h2>
            <select className="bg-gray-800 px-2 py-1 rounded" value={editing.role} onChange={(e) => setEditing({ ...editing, role: e.target.value })}>
              {ROLES.map((r) => <option key={r} value={r}>{t(`role_${r}`)}</option>)}
            </select>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={editing.is_active} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} />{t('active')}</label>
            <div className="text-sm text-gray-400">{t('overrides')}</div>
            {PERM_KEYS.map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={key in (editing.permission_overrides || {})} onChange={() => toggleOverride(editing, key, (o) => setEditing({ ...editing, permission_overrides: o }))} />
                {t(label)}
              </label>
            ))}
            <div className="flex gap-2 mt-2">
              <button className="bg-blue-600 px-3 py-1.5 rounded" onClick={() => patchMut.mutate({ id: editing.id, data: { role: editing.role, is_active: editing.is_active, permission_overrides: editing.permission_overrides } })}>{t('save')}</button>
              <button className="bg-gray-700 px-3 py-1.5 rounded" onClick={() => setEditing(null)}>{t('cancel')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Wire route + nav**

In `scada-reporter/frontend/src/App.tsx`:
- Add `import Users from './pages/Users'` with the other page imports.
- Add the route inside the `Layout` route block: `<Route path="users" element={<Users />} />`.

In `scada-reporter/frontend/src/components/Layout.tsx`, render an admin-only nav link. Inside the `<nav>` block, after the `nav.map(...)`, add:

```tsx
          {user?.role === 'admin' && (
            <NavLink
              to="/users"
              onClick={() => setMobileNav(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4z" />
              </svg>
              {t('nav_users')}
            </NavLink>
          )}
```

- [ ] **Step 7: Run tests (page + i18n parity)**

Run: `pnpm test -- src/pages/Users.test.tsx src/i18n/parity.test.ts`
Expected: PASS. (Parity test verifies every namespace has matching keys across en/tr/ru/de — the four `users.json` files must have identical key sets.)

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/src/pages/Users.tsx scada-reporter/frontend/src/pages/Users.test.tsx scada-reporter/frontend/src/i18n/ scada-reporter/frontend/src/App.tsx scada-reporter/frontend/src/components/Layout.tsx
git commit -m "feat(rbac): admin Users page, nav link, users i18n namespace"
```

---

### Task 9: Gate write buttons with `can()`

**Files:**
- Modify: `scada-reporter/frontend/src/pages/Tags.tsx` (tag-create button)
- Modify: `scada-reporter/frontend/src/pages/PlcConfig.tsx` (PLC add/edit/delete controls)
- Modify: `scada-reporter/frontend/src/pages/AdvancedReports.tsx` (template create/edit/delete controls)
- Modify: `scada-reporter/frontend/src/pages/ExcelTemplates.tsx` (template create/delete controls)
- Test: `scada-reporter/frontend/src/pages/Tags.gating.test.tsx`

**Interfaces:**
- Consumes: `useAuth().can` (Task 7).
- Produces: write controls hidden when the user lacks the permission. (Server still enforces — this is cosmetic.)

> The exact JSX for each button differs per page. For each file: import nothing new beyond `useAuth`, call `const { can } = useAuth()` in the component, and wrap the relevant control(s) in `{can('<perm>') && ( ... )}`. Map: Tags create → `tag:create`; PlcConfig add/edit/delete → `plc:manage`; AdvancedReports create/edit → `report_template:create`/`report_template:edit`, delete → `report_template:delete`; ExcelTemplates create → `report_template:create`, delete → `report_template:delete`. Locate each control with a quick search (e.g. the button whose onClick triggers the create mutation) before wrapping.

- [ ] **Step 1: Write the failing test (Tags gating as the representative case)**

Create `scada-reporter/frontend/src/pages/Tags.gating.test.tsx`. First, identify the exact accessible name of the tag-create button in `Tags.tsx` (the i18n string it renders) and use it below in place of `CREATE_BUTTON_NAME`:

```tsx
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi } from 'vitest'
import Tags from './Tags'

const canMock = vi.fn()
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'viewer', permissions: [] }, can: canMock, logout: vi.fn() }),
}))
// Stub the data layer so the page renders without network.
vi.mock('../api/client', () => ({
  getTags: vi.fn().mockResolvedValue({ data: [] }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('Tags create gating', () => {
  it('hides create when can() is false', () => {
    canMock.mockReturnValue(false)
    wrap(<Tags />)
    expect(screen.queryByRole('button', { name: /CREATE_BUTTON_NAME/i })).not.toBeInTheDocument()
  })
})
```

> Note: `Tags.tsx` may import more than `getTags`; if the test errors on a missing mock export, extend the `../api/client` mock with the other named exports the page imports (each `vi.fn()` returning `{ data: [] }`). Keep the mock minimal — only what the import statement pulls in.

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/pages/Tags.gating.test.tsx`
Expected: FAIL — create button still present (not yet gated).

- [ ] **Step 3: Wrap the controls**

In each listed page component, add `const { can } = useAuth()` (import `useAuth` from `../context/AuthContext` if not already imported) and wrap the write controls per the mapping above. For `Tags.tsx` specifically, wrap the create button: `{can('tag:create') && ( <button ...>…</button> )}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/pages/Tags.gating.test.tsx`
Expected: PASS.

- [ ] **Step 5: Run the full frontend suite**

Run: `pnpm test`
Expected: PASS. Fix any page test that asserted a now-gated control is present by giving its `useAuth` mock `can: () => true`.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/frontend/src/pages/
git commit -m "feat(rbac): gate tag/plc/report write controls with can()"
```

---

## Self-Review

**Spec coverage:**
- Hybrid role+override model → Task 1 (resolver), Task 2 (storage).
- Permission catalog (medium granularity) → Task 1 `ALL_PERMISSIONS`.
- Role defaults incl. operator (all but delete) → Task 1 `ROLE_DEFAULTS`.
- `require_perm` dependency → Task 3.
- PLC security fix + tag/report enforcement → Task 4.
- Close open `/auth/register` → Task 4.
- User CRUD API (list/create/patch/password/delete) + last-admin guard + self-delete guard → Task 6.
- `/auth/me` permissions + self password change → Task 5.
- Frontend `can()` + client → Task 7.
- Admin-only Users page + nav + i18n (en/tr/ru/de) → Task 8.
- UI gating of write buttons → Task 9.
- Language option: already implemented (`/auth/me` PATCH language preserved in Task 5); no new work — matches spec.

**Placeholder scan:** No TBD/TODO. Task 9's per-page JSX is intentionally search-located (controls vary per page); the permission mapping and wrapping pattern are fully specified, and the representative Tags test is concrete.

**Type consistency:** `permission_overrides` (dict / `Record<string, boolean>`), `permissions` (list/array of str), `effective_permissions`/`user_can`/`require_perm`/`can` names are consistent across backend Tasks 1–6 and frontend Tasks 7–9. `ManagedUser`/`UserCreatePayload`/`UserPatchPayload` defined in Task 7 and consumed in Task 8.

**Out of scope (per spec):** custom roles, audit log, email password reset, SSO.
