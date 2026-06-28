"""Tests for the deterministic AI Compliance Assistant.

The assistant is READ + DRAFT only: it surfaces deterministic data, links real
event/pack/permit IDs, drafts templated explanation text, and proposes (never
executes) report-pack creation. No server-side LLM, no autonomous writes.
"""

from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance import (
    ComplianceDischargePoint,
    ComplianceLimit,
    ComplianceParameter,
    CompliancePermit,
    ComplianceReportPack,
)
from app.models.tag import Tag, TagReading
from app.services import compliance_engine
from app.services.compliance_assistant import answer_compliance_question


def _ts(year=2026, month=5, day=1, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute)


async def _seed_breach(
    db: AsyncSession, *, requires_explanation: bool = False
) -> tuple[int, datetime, datetime]:
    """Seed a permit with a single COD value_limit and a breaching reading."""
    permit = CompliancePermit(name="Assistant Permit")
    point = ComplianceDischargePoint(permit=permit, code="OUT", name="Outfall")
    tag = Tag(node_id="ns=1;s=ASSIST_COD", name="ASSIST_COD")
    parameter = ComplianceParameter(
        permit=permit,
        discharge_point=point,
        parameter_name="COD",
        source_type="scada",
        tag=tag,
    )
    limit = ComplianceLimit(
        parameter=parameter,
        limit_type="value_limit",
        aggregation="instant",
        max_value=10.0,
        requires_explanation=requires_explanation,
    )
    db.add_all([permit, point, tag, parameter, limit])
    await db.flush()
    db.add(TagReading(tag_id=tag.id, value=12.0, quality=192, timestamp=_ts(2026, 5, 1, 12)))
    await db.commit()

    start, end = _ts(2026, 5, 1), _ts(2026, 6, 1)
    await compliance_engine.evaluate_permit(db, permit.id, start, end)
    await db.commit()
    return permit.id, start, end


@pytest.mark.asyncio
async def test_breaches_intent_links_event_ids(db_session: AsyncSession):
    permit_id, start, end = await _seed_breach(db_session)
    res = await answer_compliance_question(
        db_session,
        "Which permit limits were exceeded?",
        permit_id=permit_id,
        period_start=start,
        period_end=end,
    )
    assert res["intent"] == "breaches"
    assert any(link["type"] == "event" for link in res["links"])
    assert res["answer"]
    assert res["data"]["events"]


@pytest.mark.asyncio
async def test_breaches_intent_turkish(db_session: AsyncSession):
    permit_id, start, end = await _seed_breach(db_session)
    res = await answer_compliance_question(
        db_session,
        "Hangi limitler aşıldı?",
        permit_id=permit_id,
        period_start=start,
        period_end=end,
    )
    assert res["intent"] == "breaches"
    assert res["links"]


@pytest.mark.asyncio
async def test_missing_explanations_intent(db_session: AsyncSession):
    permit_id, start, end = await _seed_breach(db_session, requires_explanation=True)
    res = await answer_compliance_question(
        db_session,
        "What explanations are missing?",
        permit_id=permit_id,
        period_start=start,
        period_end=end,
    )
    assert res["intent"] == "missing_explanations"
    # there must be at least one open needs_explanation event linked
    assert any(link["type"] == "event" for link in res["links"])
    assert res["data"]["events"]


@pytest.mark.asyncio
async def test_readiness_not_ready_with_open_explanation(db_session: AsyncSession):
    permit_id, start, end = await _seed_breach(db_session, requires_explanation=True)
    res = await answer_compliance_question(
        db_session,
        "Is this month ready for reporting?",
        permit_id=permit_id,
        period_start=start,
        period_end=end,
    )
    assert res["intent"] == "readiness"
    assert res["data"]["ready"] is False
    assert res["data"]["open_required_explanations"] >= 1
    assert any(link["type"] == "permit" and link["id"] == permit_id for link in res["links"])


@pytest.mark.asyncio
async def test_readiness_ready_without_required_explanations(db_session: AsyncSession):
    permit_id, start, end = await _seed_breach(db_session, requires_explanation=False)
    res = await answer_compliance_question(
        db_session,
        "rapora hazır mı?",
        permit_id=permit_id,
        period_start=start,
        period_end=end,
    )
    assert res["intent"] == "readiness"
    assert res["data"]["ready"] is True
    assert res["data"]["open_required_explanations"] == 0


@pytest.mark.asyncio
async def test_draft_explanation_references_event_and_saves_nothing(db_session: AsyncSession):
    permit_id, start, end = await _seed_breach(db_session)
    # find the limit_exceeded event id
    from app.models.compliance import ComplianceEvent, ComplianceEventNote

    event = (
        await db_session.execute(
            select(ComplianceEvent).where(ComplianceEvent.event_type == "limit_exceeded")
        )
    ).scalar_one()

    notes_before = (
        await db_session.execute(select(func.count()).select_from(ComplianceEventNote))
    ).scalar_one()

    res = await answer_compliance_question(
        db_session,
        f"Draft an operator explanation for event {event.id}",
    )
    assert res["intent"] == "draft_explanation"
    draft = res["data"]["draft"]
    assert isinstance(draft, str) and draft.strip()
    # the draft must reference the parameter and the observed/limit values
    assert "COD" in draft
    assert "12" in draft
    assert "10" in draft
    assert any(link["type"] == "event" and link["id"] == event.id for link in res["links"])

    notes_after = (
        await db_session.execute(select(func.count()).select_from(ComplianceEventNote))
    ).scalar_one()
    assert notes_after == notes_before  # MUST NOT save a note


@pytest.mark.asyncio
async def test_draft_explanation_turkish(db_session: AsyncSession):
    permit_id, start, end = await _seed_breach(db_session)
    from app.models.compliance import ComplianceEvent

    event = (
        await db_session.execute(
            select(ComplianceEvent).where(ComplianceEvent.event_type == "limit_exceeded")
        )
    ).scalar_one()
    res = await answer_compliance_question(db_session, f"{event.id} için açıklama taslağı")
    assert res["intent"] == "draft_explanation"
    assert res["data"]["draft"].strip()


@pytest.mark.asyncio
async def test_draft_explanation_unknown_event(db_session: AsyncSession):
    res = await answer_compliance_question(
        db_session, "Draft an operator explanation for event 99999"
    )
    assert res["intent"] == "draft_explanation"
    # no event -> no draft, no event link
    assert not res["data"].get("draft")
    assert not res["links"]


@pytest.mark.asyncio
async def test_create_pack_proposes_without_writing(db_session: AsyncSession):
    permit_id, start, end = await _seed_breach(db_session)
    packs_before = (
        await db_session.execute(select(func.count()).select_from(ComplianceReportPack))
    ).scalar_one()

    res = await answer_compliance_question(
        db_session,
        "Create the May report pack",
        permit_id=permit_id,
        period_start=start,
        period_end=end,
    )
    assert res["intent"] == "create_pack"
    proposed = res["proposed_action"]
    assert proposed is not None
    assert proposed["action"] == "create_report_pack"
    assert proposed["permit_id"] == permit_id
    assert proposed["period_start"]
    assert proposed["period_end"]
    assert any(link["type"] == "permit" and link["id"] == permit_id for link in res["links"])

    packs_after = (
        await db_session.execute(select(func.count()).select_from(ComplianceReportPack))
    ).scalar_one()
    assert packs_after == packs_before  # MUST NOT create a pack


@pytest.mark.asyncio
async def test_create_pack_turkish(db_session: AsyncSession):
    permit_id, start, end = await _seed_breach(db_session)
    res = await answer_compliance_question(
        db_session,
        "mayıs paketini oluştur",
        permit_id=permit_id,
        period_start=start,
        period_end=end,
    )
    assert res["intent"] == "create_pack"
    assert res["proposed_action"]["action"] == "create_report_pack"


@pytest.mark.asyncio
async def test_fallback_for_nonsense(db_session: AsyncSession):
    res = await answer_compliance_question(db_session, "qwertyuiop zxcvbnm")
    assert res["intent"] == "fallback"
    assert res["answer"]
    assert res["links"] == []
    assert res["proposed_action"] is None


@pytest.mark.asyncio
async def test_assistant_endpoint(client, db_session: AsyncSession):
    from app.core.security import hash_password
    from app.models.user import User

    permit_id, start, end = await _seed_breach(db_session)
    user = User(
        username="assist_user",
        email="assist@t.com",
        hashed_password=hash_password("pw123"),
        role="viewer",
    )
    db_session.add(user)
    await db_session.commit()
    tok = (
        await client.post("/api/auth/token", data={"username": "assist_user", "password": "pw123"})
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    r = await client.post(
        "/api/compliance/assistant",
        json={
            "question": "Which limits were exceeded?",
            "permit_id": permit_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "breaches"
    assert "links" in body
    assert "answer" in body
