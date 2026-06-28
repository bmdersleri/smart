"""Compliance config CRUD API tests: permit detail/update/delete, points,
parameters, limits — RBAC, validation, nested graph, soft-delete."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.compliance import (
    ComplianceDischargePoint,
    ComplianceEvent,
    ComplianceLimit,
    ComplianceParameter,
    CompliancePermit,
)
from app.models.lab import LabParameter
from app.models.tag import Tag
from app.models.user import User


async def _login(
    client: AsyncClient, db: AsyncSession, username: str, role: str = "operator"
) -> str:
    user = User(
        username=username,
        email=f"{username}@t.com",
        hashed_password=hash_password("pw123"),
        role=role,
    )
    db.add(user)
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


def _ts(year=2026, month=6, day=1, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute)


async def _create_permit(client: AsyncClient, headers: dict, name: str = "Cfg Permit") -> int:
    r = await client.post(
        "/api/compliance/permits",
        json={"name": name, "report_frequency": "monthly"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _seed_tag(db: AsyncSession, node_id: str, name: str) -> int:
    tag = Tag(node_id=node_id, name=name)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag.id


async def _seed_lab_parameter(db: AsyncSession, code: str, name: str) -> int:
    param = LabParameter(code=code, name=name)
    db.add(param)
    await db.commit()
    await db.refresh(param)
    return param.id


# --------------------------------------------------------------------------
# Happy path: admin point -> parameter (scada) -> limit
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_full_config_happy_path(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_admin", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    tag_id = await _seed_tag(db_session, "ns=1;s=CFG_COD", "CFG_COD")

    permit_id = await _create_permit(client, h)

    # point
    rp = await client.post(
        f"/api/compliance/permits/{permit_id}/points",
        json={"code": "OUT", "name": "Outfall", "description": "Main outfall"},
        headers=h,
    )
    assert rp.status_code == 201, rp.text
    point_id = rp.json()["id"]
    assert rp.json()["permit_id"] == permit_id

    # parameter (scada with tag)
    rpar = await client.post(
        f"/api/compliance/permits/{permit_id}/parameters",
        json={
            "discharge_point_id": point_id,
            "parameter_name": "COD",
            "unit": "mg/L",
            "source_type": "scada",
            "tag_id": tag_id,
        },
        headers=h,
    )
    assert rpar.status_code == 201, rpar.text
    parameter_id = rpar.json()["id"]
    assert rpar.json()["permit_id"] == permit_id

    # limit
    rlim = await client.post(
        f"/api/compliance/parameters/{parameter_id}/limits",
        json={
            "limit_type": "value_limit",
            "aggregation": "instant",
            "max_value": 10.0,
            "severity": "critical",
        },
        headers=h,
    )
    assert rlim.status_code == 201, rlim.text
    assert rlim.json()["parameter_id"] == parameter_id
    assert rlim.json()["max_value"] == 10.0


# --------------------------------------------------------------------------
# GET /permits/{id} nested graph
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_permit_detail_returns_nested_graph(
    client: AsyncClient, db_session: AsyncSession
):
    tok = await _login(client, db_session, "cfg_nested", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    tag_id = await _seed_tag(db_session, "ns=1;s=NEST_COD", "NEST_COD")
    permit_id = await _create_permit(client, h, name="Nested Permit")

    point_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/points",
            json={"code": "OUT", "name": "Outfall"},
            headers=h,
        )
    ).json()["id"]
    parameter_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/parameters",
            json={
                "discharge_point_id": point_id,
                "parameter_name": "COD",
                "source_type": "scada",
                "tag_id": tag_id,
            },
            headers=h,
        )
    ).json()["id"]
    await client.post(
        f"/api/compliance/parameters/{parameter_id}/limits",
        json={"limit_type": "value_limit", "aggregation": "instant", "max_value": 10.0},
        headers=h,
    )

    r = await client.get(f"/api/compliance/permits/{permit_id}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == permit_id
    assert body["name"] == "Nested Permit"
    assert len(body["discharge_points"]) == 1
    assert body["discharge_points"][0]["id"] == point_id
    assert len(body["parameters"]) == 1
    param = body["parameters"][0]
    assert param["id"] == parameter_id
    assert len(param["limits"]) == 1
    assert param["limits"][0]["max_value"] == 10.0


@pytest.mark.asyncio
async def test_get_permit_detail_missing_404(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_404", role="viewer")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.get("/api/compliance/permits/999999", headers=h)
    assert r.status_code == 404


# --------------------------------------------------------------------------
# RBAC: operator 403 on config writes
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operator_cannot_create_point(client: AsyncClient, db_session: AsyncSession):
    admin_tok = await _login(client, db_session, "cfg_a1", role="admin")
    ah = {"Authorization": f"Bearer {admin_tok}"}
    permit_id = await _create_permit(client, ah)

    op_tok = await _login(client, db_session, "cfg_op1", role="operator")
    oh = {"Authorization": f"Bearer {op_tok}"}
    r = await client.post(
        f"/api/compliance/permits/{permit_id}/points",
        json={"code": "OUT", "name": "Outfall"},
        headers=oh,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_operator_cannot_create_parameter(client: AsyncClient, db_session: AsyncSession):
    admin_tok = await _login(client, db_session, "cfg_a2", role="admin")
    ah = {"Authorization": f"Bearer {admin_tok}"}
    tag_id = await _seed_tag(db_session, "ns=1;s=OP_COD", "OP_COD")
    permit_id = await _create_permit(client, ah)
    point_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/points",
            json={"code": "OUT", "name": "Outfall"},
            headers=ah,
        )
    ).json()["id"]

    op_tok = await _login(client, db_session, "cfg_op2", role="operator")
    oh = {"Authorization": f"Bearer {op_tok}"}
    r = await client.post(
        f"/api/compliance/permits/{permit_id}/parameters",
        json={
            "discharge_point_id": point_id,
            "parameter_name": "COD",
            "source_type": "scada",
            "tag_id": tag_id,
        },
        headers=oh,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_operator_cannot_create_limit(client: AsyncClient, db_session: AsyncSession):
    admin_tok = await _login(client, db_session, "cfg_a3", role="admin")
    ah = {"Authorization": f"Bearer {admin_tok}"}
    tag_id = await _seed_tag(db_session, "ns=1;s=OPL_COD", "OPL_COD")
    permit_id = await _create_permit(client, ah)
    point_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/points",
            json={"code": "OUT", "name": "Outfall"},
            headers=ah,
        )
    ).json()["id"]
    parameter_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/parameters",
            json={
                "discharge_point_id": point_id,
                "parameter_name": "COD",
                "source_type": "scada",
                "tag_id": tag_id,
            },
            headers=ah,
        )
    ).json()["id"]

    op_tok = await _login(client, db_session, "cfg_op3", role="operator")
    oh = {"Authorization": f"Bearer {op_tok}"}
    r = await client.post(
        f"/api/compliance/parameters/{parameter_id}/limits",
        json={"limit_type": "value_limit", "aggregation": "instant", "max_value": 10.0},
        headers=oh,
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------
# source_type validation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lab_source_without_lab_parameter_422(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_lab", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    permit_id = await _create_permit(client, h)
    point_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/points",
            json={"code": "OUT", "name": "Outfall"},
            headers=h,
        )
    ).json()["id"]

    r = await client.post(
        f"/api/compliance/permits/{permit_id}/parameters",
        json={
            "discharge_point_id": point_id,
            "parameter_name": "COD",
            "source_type": "lab",
        },
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_hybrid_source_without_both_422(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_hyb", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    tag_id = await _seed_tag(db_session, "ns=1;s=HYB_COD", "HYB_COD")
    permit_id = await _create_permit(client, h)
    point_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/points",
            json={"code": "OUT", "name": "Outfall"},
            headers=h,
        )
    ).json()["id"]

    # hybrid with only tag_id (missing lab_parameter_id) -> 422
    r = await client.post(
        f"/api/compliance/permits/{permit_id}/parameters",
        json={
            "discharge_point_id": point_id,
            "parameter_name": "COD",
            "source_type": "hybrid",
            "tag_id": tag_id,
        },
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invalid_source_type_422(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_badsrc", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    permit_id = await _create_permit(client, h)
    point_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/points",
            json={"code": "OUT", "name": "Outfall"},
            headers=h,
        )
    ).json()["id"]
    r = await client.post(
        f"/api/compliance/permits/{permit_id}/parameters",
        json={
            "discharge_point_id": point_id,
            "parameter_name": "COD",
            "source_type": "telepathy",
        },
        headers=h,
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------
# discharge_point belongs to another permit -> 400
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parameter_point_from_other_permit_400(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_cross", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    tag_id = await _seed_tag(db_session, "ns=1;s=X_COD", "X_COD")

    permit_a = await _create_permit(client, h, name="Permit A")
    permit_b = await _create_permit(client, h, name="Permit B")
    point_b = (
        await client.post(
            f"/api/compliance/permits/{permit_b}/points",
            json={"code": "OUT", "name": "Outfall B"},
            headers=h,
        )
    ).json()["id"]

    # create a parameter under permit_a but with a point that belongs to permit_b
    r = await client.post(
        f"/api/compliance/permits/{permit_a}/parameters",
        json={
            "discharge_point_id": point_b,
            "parameter_name": "COD",
            "source_type": "scada",
            "tag_id": tag_id,
        },
        headers=h,
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------
# limit validation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limit_invalid_type_422(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_lim", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    tag_id = await _seed_tag(db_session, "ns=1;s=LIM_COD", "LIM_COD")
    permit_id = await _create_permit(client, h)
    point_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/points",
            json={"code": "OUT", "name": "Outfall"},
            headers=h,
        )
    ).json()["id"]
    parameter_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/parameters",
            json={
                "discharge_point_id": point_id,
                "parameter_name": "COD",
                "source_type": "scada",
                "tag_id": tag_id,
            },
            headers=h,
        )
    ).json()["id"]

    r = await client.post(
        f"/api/compliance/parameters/{parameter_id}/limits",
        json={"limit_type": "nonsense", "aggregation": "instant"},
        headers=h,
    )
    assert r.status_code == 422

    r2 = await client.post(
        f"/api/compliance/parameters/{parameter_id}/limits",
        json={"limit_type": "value_limit", "aggregation": "nonsense"},
        headers=h,
    )
    assert r2.status_code == 422


# --------------------------------------------------------------------------
# PUT permit invalid frequency -> 422
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_permit_invalid_frequency_422(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_putfreq", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    permit_id = await _create_permit(client, h)
    r = await client.put(
        f"/api/compliance/permits/{permit_id}",
        json={"name": "Renamed", "report_frequency": "hourly"},
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_permit_updates_metadata(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_put", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    permit_id = await _create_permit(client, h)
    r = await client.put(
        f"/api/compliance/permits/{permit_id}",
        json={
            "name": "Renamed Permit",
            "facility_name": "Plant 2",
            "authority": "EPA",
            "report_frequency": "quarterly",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed Permit"
    assert body["facility_name"] == "Plant 2"
    assert body["report_frequency"] == "quarterly"


# --------------------------------------------------------------------------
# DELETE permit = soft delete (always)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_permit_soft_deletes(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_del", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    permit_id = await _create_permit(client, h)
    r = await client.delete(f"/api/compliance/permits/{permit_id}", headers=h)
    assert r.status_code == 200, r.text
    detail = (await client.get(f"/api/compliance/permits/{permit_id}", headers=h)).json()
    assert detail["is_active"] is False


@pytest.mark.asyncio
async def test_delete_permit_with_event_still_soft_deleted(
    client: AsyncClient, db_session: AsyncSession
):
    tok = await _login(client, db_session, "cfg_delev", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    permit_id = await _create_permit(client, h, name="Permit With Event")

    # seed an event directly on this permit (the parent legal record)
    point = ComplianceDischargePoint(permit_id=permit_id, code="OUT", name="Outfall")
    tag = Tag(node_id="ns=1;s=EVT_COD", name="EVT_COD")
    db_session.add_all([point, tag])
    await db_session.flush()
    parameter = ComplianceParameter(
        permit_id=permit_id,
        discharge_point_id=point.id,
        parameter_name="COD",
        source_type="scada",
        tag_id=tag.id,
    )
    db_session.add(parameter)
    await db_session.flush()
    limit = ComplianceLimit(
        parameter_id=parameter.id, limit_type="value_limit", aggregation="instant", max_value=10.0
    )
    db_session.add(limit)
    await db_session.flush()
    event = ComplianceEvent(
        permit_id=permit_id,
        parameter_id=parameter.id,
        limit_id=limit.id,
        event_type="limit_exceeded",
        period_start=_ts(2026, 6, 1),
        period_end=_ts(2026, 6, 2),
        event_key="cfg-delev-key",
    )
    db_session.add(event)
    await db_session.commit()

    r = await client.delete(f"/api/compliance/permits/{permit_id}", headers=h)
    assert r.status_code == 200, r.text

    # permit must still exist (not physically gone) and be inactive
    detail = (await client.get(f"/api/compliance/permits/{permit_id}", headers=h)).json()
    assert detail["is_active"] is False
    # the event is still present
    permit = await db_session.get(CompliancePermit, permit_id)
    assert permit is not None


# --------------------------------------------------------------------------
# Missing-id 404 on PUT/DELETE
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_permit_missing_404(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_put404", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.put(
        "/api/compliance/permits/999999",
        json={"name": "Nope", "report_frequency": "monthly"},
        headers=h,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_permit_missing_404(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_del404", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.delete("/api/compliance/permits/999999", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_point_missing_404(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_pt404", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.put(
        "/api/compliance/points/999999",
        json={"code": "X", "name": "Y"},
        headers=h,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_parameter_missing_404(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_par404", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.delete("/api/compliance/parameters/999999", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_limit_missing_404(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_lim404", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.delete("/api/compliance/limits/999999", headers=h)
    assert r.status_code == 404


# --------------------------------------------------------------------------
# list + update/delete round trips
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_points_parameters_limits(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cfg_list", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    tag_id = await _seed_tag(db_session, "ns=1;s=LST_COD", "LST_COD")
    lab_id = await _seed_lab_parameter(db_session, "LBOD", "BOD")
    permit_id = await _create_permit(client, h)
    point_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/points",
            json={"code": "OUT", "name": "Outfall"},
            headers=h,
        )
    ).json()["id"]
    parameter_id = (
        await client.post(
            f"/api/compliance/permits/{permit_id}/parameters",
            json={
                "discharge_point_id": point_id,
                "parameter_name": "BOD",
                "source_type": "hybrid",
                "tag_id": tag_id,
                "lab_parameter_id": lab_id,
            },
            headers=h,
        )
    ).json()["id"]
    limit_id = (
        await client.post(
            f"/api/compliance/parameters/{parameter_id}/limits",
            json={"limit_type": "value_limit", "aggregation": "daily_avg", "max_value": 25.0},
            headers=h,
        )
    ).json()["id"]

    rp = await client.get(f"/api/compliance/permits/{permit_id}/points", headers=h)
    assert rp.status_code == 200
    assert any(p["id"] == point_id for p in rp.json())

    rpar = await client.get(f"/api/compliance/permits/{permit_id}/parameters", headers=h)
    assert rpar.status_code == 200
    assert any(p["id"] == parameter_id for p in rpar.json())

    rlim = await client.get(f"/api/compliance/parameters/{parameter_id}/limits", headers=h)
    assert rlim.status_code == 200
    assert any(limit_item["id"] == limit_id for limit_item in rlim.json())

    # update point
    rup = await client.put(
        f"/api/compliance/points/{point_id}",
        json={"code": "OUT2", "name": "Outfall Renamed"},
        headers=h,
    )
    assert rup.status_code == 200
    assert rup.json()["code"] == "OUT2"

    # update limit
    rul = await client.put(
        f"/api/compliance/limits/{limit_id}",
        json={"limit_type": "value_limit", "aggregation": "daily_avg", "max_value": 30.0},
        headers=h,
    )
    assert rul.status_code == 200
    assert rul.json()["max_value"] == 30.0

    # delete limit
    rdl = await client.delete(f"/api/compliance/limits/{limit_id}", headers=h)
    assert rdl.status_code == 200
    assert (
        await client.get(f"/api/compliance/parameters/{parameter_id}/limits", headers=h)
    ).json() == []
