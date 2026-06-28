"""Deterministic AI Compliance Assistant.

Mirrors the heuristic en/tr keyword-intent style of ``app/services/ai_service.py``:
there is NO server-side LLM. The external agent is the LLM; this service only
classifies the question into a deterministic intent, surfaces real compliance
data, and links durable event/pack/permit IDs.

Guardrails (from the compliance design Non-Goals):
- READ + DRAFT only. The assistant never makes a compliance decision.
- It does NOT create/approve packs or change event status. ``create_pack``
  returns a *proposed action*; ``draft_explanation`` returns templated text in
  ``data.draft`` and never persists a note.
- Every answer references deterministic IDs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance import ComplianceEvent, CompliancePermit, ComplianceReportPack

# --- Intent keyword vocabularies (en + tr) --------------------------------

_READINESS_KW = (
    "ready for reporting",
    "report ready",
    "report-ready",
    "ready to report",
    "rapora hazir",
    "rapora hazır",
    "hazir mi",
    "hazır mı",
    "bu ay hazir",
    "bu ay hazır",
    "raporlamaya hazir",
    "raporlamaya hazır",
)
_BREACHES_KW = (
    "exceeded",
    "exceed",
    "breach",
    "limit was",
    "limits were",
    "over the limit",
    "asildi",
    "aşıldı",
    "asilan",
    "aşılan",
    "limit asim",
    "limit aşım",
    "ihlal",
)
_MISSING_EXPL_KW = (
    "explanation",
    "explanations",
    "missing explanation",
    "aciklama eksik",
    "açıklama eksik",
    "aciklamalar eksik",
    "açıklamalar eksik",
    "eksik aciklama",
    "eksik açıklama",
    "aciklama gerek",
    "açıklama gerek",
)
_DRAFT_KW = (
    "draft",
    "write an explanation",
    "write explanation",
    "taslak",
    "aciklama yaz",
    "açıklama yaz",
    "aciklama tasla",
    "açıklama tasla",
)
_CREATE_PACK_KW = (
    "create the",
    "create a report pack",
    "create report pack",
    "create pack",
    "olustur",
    "oluştur",
    "paketi olustur",
    "paketi oluştur",
    "paket olustur",
    "paket oluştur",
)

_PARAMETER_LABELS = {
    "value_limit": "limit aşımı / limit exceedance",
    "sample_count": "eksik numune / missing sample",
    "sample_frequency": "geç numune / late sample",
    "quality": "kötü kalite / bad quality",
}


def _is_turkish(q: str) -> bool:
    return any(c in q for c in ("ı", "ğ", "ü", "ş", "ö", "ç")) or any(
        w in q for w in (" mi", " mı", "asildi", "aşıldı", "hazir", "hazır", "olustur", "oluştur")
    )


def _norm(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def _classify(q: str) -> str:
    # Order matters: draft + create_pack are more specific verbs and must win
    # over the breach/explanation noun keywords they may co-occur with.
    if any(kw in q for kw in _DRAFT_KW):
        return "draft_explanation"
    if any(kw in q for kw in _CREATE_PACK_KW) and ("pack" in q or "paket" in q):
        return "create_pack"
    if any(kw in q for kw in _READINESS_KW):
        return "readiness"
    if any(kw in q for kw in _MISSING_EXPL_KW):
        return "missing_explanations"
    if any(kw in q for kw in _BREACHES_KW):
        return "breaches"
    return "fallback"


def _event_to_dict(event: ComplianceEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "parameter_id": event.parameter_id,
        "severity": event.severity,
        "status": event.status,
        "observed_value": event.observed_value,
        "limit_value": event.limit_value,
        "period_start": _norm(event.period_start).isoformat(),
        "period_end": _norm(event.period_end).isoformat(),
    }


async def _events_for(
    db: AsyncSession,
    *,
    event_type: str | None = None,
    status: str | None = None,
    permit_id: int | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> list[ComplianceEvent]:
    filters = []
    if event_type is not None:
        filters.append(ComplianceEvent.event_type == event_type)
    if status is not None:
        filters.append(ComplianceEvent.status == status)
    if permit_id is not None:
        filters.append(ComplianceEvent.permit_id == permit_id)
    if period_start is not None:
        filters.append(ComplianceEvent.period_start == _norm(period_start))
    if period_end is not None:
        filters.append(ComplianceEvent.period_end == _norm(period_end))
    rows = (
        await db.execute(
            select(ComplianceEvent)
            .where(*filters)
            .order_by(ComplianceEvent.period_start.desc(), ComplianceEvent.id.desc())
        )
    ).scalars()
    return list(rows)


def _result(
    intent: str,
    answer: str,
    *,
    links: list[dict[str, Any]] | None = None,
    data: dict[str, Any] | None = None,
    proposed_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "intent": intent,
        "answer": answer,
        "links": links or [],
        "data": data or {},
        "proposed_action": proposed_action,
    }


async def answer_compliance_question(
    db: AsyncSession,
    question: str,
    *,
    permit_id: int | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[str, Any]:
    q = question.lower().strip()
    tr = _is_turkish(q)
    intent = _classify(q)

    if intent == "readiness":
        return await _readiness(db, permit_id, period_start, period_end, tr)
    if intent == "breaches":
        return await _breaches(db, permit_id, period_start, period_end, tr)
    if intent == "missing_explanations":
        return await _missing_explanations(db, permit_id, period_start, period_end, tr)
    if intent == "draft_explanation":
        return await _draft_explanation(db, question, q, tr)
    if intent == "create_pack":
        return await _create_pack(db, permit_id, period_start, period_end, tr)
    return _fallback(tr)


async def _readiness(
    db: AsyncSession,
    permit_id: int | None,
    period_start: datetime | None,
    period_end: datetime | None,
    tr: bool,
) -> dict[str, Any]:
    links: list[dict[str, Any]] = []
    open_required = await _events_for(
        db,
        event_type="needs_explanation",
        status="open",
        permit_id=permit_id,
        period_start=period_start,
        period_end=period_end,
    )
    for event in open_required:
        links.append({"type": "event", "id": event.id})

    pack_status: str | None = None
    if permit_id is not None:
        links.append({"type": "permit", "id": permit_id})
        pack_filters = [ComplianceReportPack.permit_id == permit_id]
        if period_start is not None:
            pack_filters.append(ComplianceReportPack.period_start == _norm(period_start))
        if period_end is not None:
            pack_filters.append(ComplianceReportPack.period_end == _norm(period_end))
        pack = (
            (
                await db.execute(
                    select(ComplianceReportPack)
                    .where(*pack_filters)
                    .order_by(ComplianceReportPack.id.desc())
                )
            )
            .scalars()
            .first()
        )
        if pack is not None:
            pack_status = pack.status
            links.append({"type": "pack", "id": pack.id})

    ready = len(open_required) == 0
    data = {
        "ready": ready,
        "open_required_explanations": len(open_required),
        "pack_status": pack_status,
    }

    if tr:
        if ready:
            answer = "Dönem raporlamaya hazır: bekleyen zorunlu açıklama yok."
        else:
            answer = (
                f"Dönem raporlamaya hazır DEĞİL: {len(open_required)} açık zorunlu "
                "açıklama bekliyor. Bu olaylara not ekleyin."
            )
        if pack_status:
            answer += f" Mevcut paket durumu: {pack_status}."
    else:
        if ready:
            answer = "Period is report-ready: no required explanations are pending."
        else:
            answer = (
                f"Period is NOT report-ready: {len(open_required)} required explanation(s) "
                "are still open. Add a note to those events."
            )
        if pack_status:
            answer += f" Existing pack status: {pack_status}."

    return _result("readiness", answer, links=links, data=data)


async def _breaches(
    db: AsyncSession,
    permit_id: int | None,
    period_start: datetime | None,
    period_end: datetime | None,
    tr: bool,
) -> dict[str, Any]:
    events = await _events_for(
        db,
        event_type="limit_exceeded",
        permit_id=permit_id,
        period_start=period_start,
        period_end=period_end,
    )
    links = [{"type": "event", "id": event.id} for event in events]
    data = {"events": [_event_to_dict(event) for event in events]}
    if tr:
        answer = f"{len(events)} limit aşımı olayı bulundu."
    else:
        answer = f"Found {len(events)} limit-exceeded event(s)."
    return _result("breaches", answer, links=links, data=data)


async def _missing_explanations(
    db: AsyncSession,
    permit_id: int | None,
    period_start: datetime | None,
    period_end: datetime | None,
    tr: bool,
) -> dict[str, Any]:
    events = await _events_for(
        db,
        event_type="needs_explanation",
        status="open",
        permit_id=permit_id,
        period_start=period_start,
        period_end=period_end,
    )
    links = [{"type": "event", "id": event.id} for event in events]
    data = {"events": [_event_to_dict(event) for event in events]}
    if tr:
        answer = f"{len(events)} olay hâlâ operatör açıklaması bekliyor."
    else:
        answer = f"{len(events)} event(s) still need an operator explanation."
    return _result("missing_explanations", answer, links=links, data=data)


def _extract_event_id(question: str) -> int | None:
    match = re.search(r"\b(\d+)\b", question)
    return int(match.group(1)) if match else None


async def _draft_explanation(
    db: AsyncSession,
    question: str,
    q: str,
    tr: bool,
) -> dict[str, Any]:
    event_id = _extract_event_id(q)
    if event_id is None:
        answer = (
            "Hangi olay için taslak istediğinizi belirtin (olay numarası)."
            if tr
            else "Specify which event to draft for (event id)."
        )
        return _result("draft_explanation", answer, data={"draft": None})

    event = await db.get(ComplianceEvent, event_id)
    if event is None:
        answer = (
            f"{event_id} numaralı olay bulunamadı." if tr else f"Event {event_id} was not found."
        )
        return _result("draft_explanation", answer, data={"draft": None})

    try:
        evidence = json.loads(event.evidence_json) if event.evidence_json else {}
    except ValueError, TypeError:
        evidence = {}

    parameter = evidence.get("parameter", f"parameter#{event.parameter_id}")
    observed = (
        event.observed_value if event.observed_value is not None else evidence.get("observed_value")
    )
    limit_value = (
        event.limit_value if event.limit_value is not None else evidence.get("limit_value")
    )
    limit_type = evidence.get("limit_type", "value_limit")
    period_start = _norm(event.period_start).date().isoformat()
    period_end = _norm(event.period_end).date().isoformat()
    kind = _PARAMETER_LABELS.get(limit_type, limit_type)

    if tr:
        draft = (
            f"{period_start} – {period_end} döneminde '{parameter}' parametresi için "
            f"{kind} kaydedildi. Gözlemlenen değer {observed}, izin limiti {limit_value}. "
            "Kök neden: [operatör tarafından doldurulacak]. Alınan düzeltici önlem: "
            "[operatör tarafından doldurulacak]. Bu taslak otomatik üretildi; "
            "kaydedilmeden önce operatör tarafından gözden geçirilip onaylanmalıdır."
        )
        answer = (
            f"{event_id} numaralı olay için açıklama taslağı hazırlandı. "
            "Kaydetmek için operatör onayı gerekir."
        )
    else:
        draft = (
            f"For period {period_start} to {period_end}, a {kind} was recorded for "
            f"parameter '{parameter}'. Observed value was {observed} against a permitted "
            f"limit of {limit_value}. Root cause: [to be completed by the operator]. "
            "Corrective action taken: [to be completed by the operator]. This is an "
            "auto-generated draft and must be reviewed and confirmed by an operator "
            "before it is saved."
        )
        answer = (
            f"Drafted an operator explanation for event {event_id}. "
            "Saving it requires explicit operator confirmation."
        )

    links = [{"type": "event", "id": event.id}]
    data = {
        "draft": draft,
        "event": _event_to_dict(event),
    }
    return _result("draft_explanation", answer, links=links, data=data)


async def _create_pack(
    db: AsyncSession,
    permit_id: int | None,
    period_start: datetime | None,
    period_end: datetime | None,
    tr: bool,
) -> dict[str, Any]:
    if permit_id is None:
        answer = (
            "Paket için izin (permit_id) ve dönem belirtin."
            if tr
            else "Provide a permit_id and period for the report pack."
        )
        return _result("create_pack", answer, proposed_action=None)

    permit = await db.get(CompliancePermit, permit_id)
    if permit is None:
        answer = (
            f"{permit_id} numaralı izin bulunamadı." if tr else f"Permit {permit_id} was not found."
        )
        return _result("create_pack", answer, proposed_action=None)

    ps = _norm(period_start).isoformat() if period_start is not None else None
    pe = _norm(period_end).isoformat() if period_end is not None else None
    proposed = {
        "action": "create_report_pack",
        "permit_id": permit_id,
        "period_start": ps,
        "period_end": pe,
    }
    links = [{"type": "permit", "id": permit_id}]
    if tr:
        answer = (
            f"{permit_id} numaralı izin için rapor paketi oluşturulması önerildi "
            f"({ps} – {pe}). Bu işlem otomatik yapılmaz; onaylamak için "
            "'report-pack create' komutunu çalıştırın veya arayüzdeki düğmeyi kullanın."
        )
    else:
        answer = (
            f"Proposed creating a report pack for permit {permit_id} ({ps} to {pe}). "
            "This is not executed automatically; confirm by running the "
            "'report-pack create' command or the UI button."
        )
    return _result("create_pack", answer, links=links, proposed_action=proposed)


def _fallback(tr: bool) -> dict[str, Any]:
    if tr:
        answer = (
            "Sorunuzu anlayamadım. Şunları sorabilirsiniz: bu ay rapora hazır mı, "
            "hangi limitler aşıldı, hangi açıklamalar eksik, N için açıklama taslağı, "
            "mayıs paketini oluştur."
        )
    else:
        answer = (
            "I couldn't understand the question. Try: is this month ready for reporting, "
            "which limits were exceeded, what explanations are missing, draft an explanation "
            "for event N, create the May report pack."
        )
    return _result("fallback", answer)


__all__ = ["answer_compliance_question"]
