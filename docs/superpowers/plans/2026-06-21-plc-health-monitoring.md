# PLC Health Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PLC bağlantı/veri sağlığını izleyen, sorunları kalıcı incident'lar olarak kaydedip UI/e-posta/webhook ile uyaran bir özellik.

**Architecture:** Collector process'inde bir `PlcHealthTracker` poller'dan per-PLC okuma sonuçlarını (good/bad) ve bağlantı geçişlerini toplar. Periyodik `plc_monitor_loop` her döngüde saf bir `evaluate()` fonksiyonuyla durum geçişlerini tespit eder, `plc_health` (anlık) + `plc_incident` (geçmiş) tablolarına yazar ve `notifier` ile uyarı gönderir. API ve frontend DB'den okur — collector ayrı process'te olsa bile çalışır.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), APScheduler, pytest-asyncio, React 19 + TanStack Query + Tailwind v4 + i18next, vitest, httpx.

## Global Constraints

- Python 3.14; SQLAlchemy 2.0 `Mapped`/`mapped_column` stili; `Base` `from app.core.database`.
- Modeller `app/main.py` import listesine ve `alembic/env.py`'ye eklenmeli (Base.metadata kaydı; testler `create_all` ile tablo alır).
- Async testler: `pytest-asyncio`, in-memory SQLite StaticPool, autouse table-clear fixture (sıra bağımsız). API testleri token için `_admin_token(client, db, username)` desenini kullanır (bkz. `tests/test_groups.py`).
- `just check` (ruff + ruff format + mypy + test) ve pre-commit geçmeli. Tüm yeni kod tip-anotasyonlu.
- Bildirimler fire-and-forget: `try/except` ile sarılı, poller/monitor'ı asla kırmaz.
- E-posta ve webhook **varsayılan kapalı**; sadece yapılandırılınca aktif.
- RBAC: okuma endpoint'leri `Depends(get_current_user)`; ack `Depends(require_perm("plc:manage"))`.
- PLC kimliği `(plc_ip, rack, slot)` üçlüsü. `plc_manager.status()` ip→bool döner; bağlantı eşlemesi ip üzerinden.
- i18n: yeni stringler 5 dilde (en, tr, ru, de, ar) — `UserUpdate.language` Literal'i bu seti tanımlar.
- Frequent commits: her task sonunda commit.

---

### Task 1: Veri modelleri + migration

**Files:**
- Create: `scada-reporter/backend/app/models/plc_health.py`
- Create: `scada-reporter/backend/app/models/plc_incident.py`
- Modify: `scada-reporter/backend/app/main.py` (model import listesi)
- Modify: `scada-reporter/backend/alembic/env.py` (model import listesi)
- Test: `scada-reporter/backend/tests/test_plc_health_models.py`

**Interfaces:**
- Produces: `PlcHealth` ORM (tablo `plc_health`), `PlcIncident` ORM (tablo `plc_incidents`).
  - `PlcHealth`: `id, plc_ip:str, plc_name:str, rack:int, slot:int, connected:bool, last_success_at:datetime|None, consecutive_fail:int, last_error:str|None, good_last_cycle:int, bad_last_cycle:int, reconnects_last_min:int, open_incident_count:int, updated_at:datetime`. Unique `(plc_ip, rack, slot)`.
  - `PlcIncident`: `id, plc_ip:str, plc_name:str, rack:int, slot:int, kind:str, severity:str, message:str, detail:dict(JSON), opened_at:datetime, resolved_at:datetime|None, acknowledged_by:str|None, acknowledged_at:datetime|None, notified:bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plc_health_models.py
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident


@pytest.mark.asyncio
async def test_plc_health_row_roundtrip(db_session: AsyncSession):
    db_session.add(
        PlcHealth(plc_ip="10.0.0.1", plc_name="PLC1", rack=0, slot=1, connected=True)
    )
    await db_session.commit()
    row = (await db_session.execute(select(PlcHealth))).scalar_one()
    assert row.plc_ip == "10.0.0.1"
    assert row.connected is True
    assert row.consecutive_fail == 0
    assert row.open_incident_count == 0


@pytest.mark.asyncio
async def test_plc_incident_open_query(db_session: AsyncSession):
    db_session.add(
        PlcIncident(
            plc_ip="10.0.0.1", plc_name="PLC1", rack=0, slot=1,
            kind="disconnected", severity="critical", message="down",
            detail={"reason": "timeout"},
        )
    )
    await db_session.commit()
    open_rows = (
        await db_session.execute(select(PlcIncident).where(PlcIncident.resolved_at.is_(None)))
    ).scalars().all()
    assert len(open_rows) == 1
    assert open_rows[0].detail == {"reason": "timeout"}
    assert open_rows[0].notified is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_health_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.plc_health'`

- [ ] **Step 3: Write the models**

```python
# app/models/plc_health.py
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlcHealth(Base):
    __tablename__ = "plc_health"
    __table_args__ = (UniqueConstraint("plc_ip", "rack", "slot", name="uq_plc_health_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plc_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    plc_name: Mapped[str] = mapped_column(String(255), default="")
    rack: Mapped[int] = mapped_column(Integer, default=0)
    slot: Mapped[int] = mapped_column(Integer, default=1)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_fail: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    good_last_cycle: Mapped[int] = mapped_column(Integer, default=0)
    bad_last_cycle: Mapped[int] = mapped_column(Integer, default=0)
    reconnects_last_min: Mapped[int] = mapped_column(Integer, default=0)
    open_incident_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
```

```python
# app/models/plc_incident.py
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


class PlcIncident(Base):
    __tablename__ = "plc_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plc_ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    plc_name: Mapped[str] = mapped_column(String(255), default="")
    rack: Mapped[int] = mapped_column(Integer, default=0)
    slot: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 4: Register models for metadata**

In `app/main.py`, add to the model import block (after the existing `from app.models import ...` lines, near line 39-43):

```python
from app.models import plc_health as _plc_health  # noqa: F401
from app.models import plc_incident as _plc_incident  # noqa: F401
```

In `alembic/env.py`, add to the import block (after the other `import app.models.*` lines):

```python
import app.models.plc_health  # noqa: F401 — registers PlcHealth with Base.metadata
import app.models.plc_incident  # noqa: F401 — registers PlcIncident with Base.metadata
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_health_models.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Generate the migration**

Run: `just makemigration msg="plc health + incident tables"`
Then confirm a new file exists under `scada-reporter/backend/alembic/versions/` containing `create_table('plc_health'` and `create_table('plc_incidents'`. Open it and verify both tables + the unique constraint are present.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/models/plc_health.py scada-reporter/backend/app/models/plc_incident.py scada-reporter/backend/app/main.py scada-reporter/backend/alembic/env.py scada-reporter/backend/alembic/versions/ scada-reporter/backend/tests/test_plc_health_models.py
git commit -m "feat(plc-health): plc_health + plc_incident models and migration"
```

---

### Task 2: Settings — eşikler + uyarı kanalı config

**Files:**
- Modify: `scada-reporter/backend/app/core/config.py` (Settings alanları + config_warnings)
- Test: `scada-reporter/backend/tests/test_plc_monitor_config.py`

**Interfaces:**
- Produces: `Settings` üzerinde yeni alanlar:
  `PLC_MONITOR_INTERVAL:int=10`, `PLC_STALE_SECONDS:float=60.0`, `PLC_PARTIAL_BAD_RATIO:float=0.5`, `PLC_PARTIAL_BAD_CYCLES:int=3`, `PLC_FLAP_WINDOW_SECONDS:float=120.0`, `PLC_FLAP_COUNT:int=3`, `PLC_RECOVER_CYCLES:int=2`, `PLC_INCIDENT_RETENTION_DAYS:int=90`, `ALERT_MIN_SEVERITY:str="warning"`, `ALERT_EMAIL_ENABLED:bool=False`, `SMTP_HOST:str=""`, `SMTP_PORT:int=587`, `SMTP_USER:str=""`, `SMTP_PASSWORD:str=""`, `ALERT_EMAIL_FROM:str=""`, `ALERT_EMAIL_TO:str=""`, `ALERT_WEBHOOK_URL:str=""`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plc_monitor_config.py
from app.core.config import Settings


def test_monitor_defaults():
    s = Settings()
    assert s.PLC_MONITOR_INTERVAL == 10
    assert s.PLC_STALE_SECONDS == 60.0
    assert s.PLC_PARTIAL_BAD_RATIO == 0.5
    assert s.PLC_FLAP_COUNT == 3
    assert s.PLC_RECOVER_CYCLES == 2
    assert s.ALERT_EMAIL_ENABLED is False
    assert s.ALERT_WEBHOOK_URL == ""


def test_config_warns_when_email_enabled_but_unconfigured():
    s = Settings(ENVIRONMENT="production", ALERT_EMAIL_ENABLED=True, SMTP_HOST="")
    warnings = s.config_warnings()
    assert any("SMTP" in w for w in warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_monitor_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'PLC_MONITOR_INTERVAL'`

- [ ] **Step 3: Add settings fields + warning**

In `app/core/config.py`, add these fields inside `class Settings` (after `REPORT_TZ_OFFSET_HOURS`):

```python
    # ── PLC sağlık izleme ──
    PLC_MONITOR_INTERVAL: int = 10  # monitor değerlendirme periyodu (sn)
    PLC_STALE_SECONDS: float = 60.0  # bağlı ama bu süre GOOD okuma yoksa stale
    PLC_PARTIAL_BAD_RATIO: float = 0.5  # tick BAD oranı bu üstündeyse kısmi hata
    PLC_PARTIAL_BAD_CYCLES: int = 3  # kısmi hata için ardışık tick
    PLC_FLAP_WINDOW_SECONDS: float = 120.0  # flapping penceresi
    PLC_FLAP_COUNT: int = 3  # pencerede bu kadar reconnect = flapping
    PLC_RECOVER_CYCLES: int = 2  # auto-resolve için temiz tick (histerezis)
    PLC_INCIDENT_RETENTION_DAYS: int = 90  # resolved incident saklama

    # ── Uyarı kanalları (varsayılan kapalı) ──
    ALERT_MIN_SEVERITY: str = "warning"  # warning | critical (e-posta/webhook kapısı)
    ALERT_EMAIL_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_FROM: str = ""
    ALERT_EMAIL_TO: str = ""  # virgülle ayrılmış alıcılar
    ALERT_WEBHOOK_URL: str = ""
```

In `config_warnings`, before `return warnings`, add:

```python
        if self.ALERT_EMAIL_ENABLED and not (self.SMTP_HOST and self.ALERT_EMAIL_TO):
            warnings.append(
                "ALERT_EMAIL_ENABLED=True ama SMTP_HOST/ALERT_EMAIL_TO eksik —"
                " e-posta uyarıları gönderilemez."
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_monitor_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/core/config.py scada-reporter/backend/tests/test_plc_monitor_config.py
git commit -m "feat(plc-health): monitor thresholds + alert channel settings"
```

---

### Task 3: detector.evaluate (saf algılama — sistemin kalbi)

**Files:**
- Create: `scada-reporter/backend/app/monitor/__init__.py` (boş)
- Create: `scada-reporter/backend/app/monitor/detector.py`
- Test: `scada-reporter/backend/tests/test_plc_detector.py`

**Interfaces:**
- Consumes: yok (saf modül, bağımsız).
- Produces:
  - `@dataclass(frozen=True) PlcObservation`: `key:tuple[str,int,int]`, `name:str`, `connected:bool`, `good_count:int`, `bad_count:int`, `seconds_since_success:float`, `reconnects_in_window:int`.
  - `@dataclass(frozen=True) DetectorConfig`: `stale_seconds:float`, `partial_bad_ratio:float`, `partial_bad_cycles:int`, `flap_count:int`, `recover_cycles:int`.
  - `@dataclass OpenIncident`: `kind:str`, `severity:str`, `opened_at_mono:float`, `clean_cycles:int=0`, `detail:dict`.
  - `@dataclass PlcMonitorState`: `open:dict[str,OpenIncident]`, `partial_bad_streak:int=0`, `disconnected_streak:int=0`.
  - `@dataclass EvalResult`: `state:PlcMonitorState`, `opened:list[OpenIncident]`, `resolved:list[str]`.
  - `evaluate(prev:PlcMonitorState, obs:PlcObservation, cfg:DetectorConfig, now:float) -> EvalResult`.
  - Kind→severity sabiti: disconnected/stale_data = critical, partial_bad/flapping = warning.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plc_detector.py
from app.monitor.detector import (
    DetectorConfig,
    PlcMonitorState,
    PlcObservation,
    evaluate,
)

CFG = DetectorConfig(
    stale_seconds=60.0, partial_bad_ratio=0.5, partial_bad_cycles=3,
    flap_count=3, recover_cycles=2,
)
KEY = ("10.0.0.1", 0, 1)


def _obs(connected=True, good=10, bad=0, sss=0.0, reconnects=0):
    return PlcObservation(
        key=KEY, name="PLC1", connected=connected, good_count=good,
        bad_count=bad, seconds_since_success=sss, reconnects_in_window=reconnects,
    )


def _fresh():
    return PlcMonitorState(open={})


def test_disconnect_needs_two_cycles():
    s = _fresh()
    r1 = evaluate(s, _obs(connected=False, good=0, bad=0), CFG, now=1.0)
    assert r1.opened == []  # 1. tick: henüz açma
    r2 = evaluate(r1.state, _obs(connected=False, good=0, bad=0), CFG, now=2.0)
    assert [i.kind for i in r2.opened] == ["disconnected"]
    assert r2.opened[0].severity == "critical"
    assert "disconnected" in r2.state.open


def test_disconnect_resolves_after_recover_cycles():
    s = _fresh()
    s = evaluate(s, _obs(connected=False), CFG, now=1.0).state
    r = evaluate(s, _obs(connected=False), CFG, now=2.0)  # opened
    s = r.state
    s = evaluate(s, _obs(connected=True), CFG, now=3.0).state  # clean 1
    r2 = evaluate(s, _obs(connected=True), CFG, now=4.0)       # clean 2 -> resolve
    assert r2.resolved == ["disconnected"]
    assert "disconnected" not in r2.state.open


def test_stale_data_when_connected_no_good_reads():
    s = _fresh()
    r = evaluate(s, _obs(connected=True, good=0, bad=0, sss=65.0), CFG, now=10.0)
    assert [i.kind for i in r.opened] == ["stale_data"]
    assert r.opened[0].severity == "critical"


def test_partial_bad_requires_consecutive_cycles():
    s = _fresh()
    obs = _obs(connected=True, good=2, bad=8, sss=0.0)  # bad ratio 0.8 > 0.5
    s = evaluate(s, obs, CFG, now=1.0).state  # streak 1
    s = evaluate(s, obs, CFG, now=2.0).state  # streak 2
    r = evaluate(s, obs, CFG, now=3.0)        # streak 3 -> open
    assert [i.kind for i in r.opened] == ["partial_bad"]
    assert r.opened[0].severity == "warning"


def test_flapping_when_reconnects_exceed_count():
    s = _fresh()
    r = evaluate(s, _obs(connected=True, reconnects=3), CFG, now=1.0)
    assert [i.kind for i in r.opened] == ["flapping"]


def test_no_duplicate_open_for_same_kind():
    s = _fresh()
    s = evaluate(s, _obs(connected=False), CFG, now=1.0).state
    r = evaluate(s, _obs(connected=False), CFG, now=2.0)  # opens
    s = r.state
    r2 = evaluate(s, _obs(connected=False), CFG, now=3.0)  # still down
    assert r2.opened == []  # no second incident
    assert "disconnected" in r2.state.open
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.monitor'`

- [ ] **Step 3: Implement the detector**

Create empty `app/monitor/__init__.py`. Then:

```python
# app/monitor/detector.py
from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY = {
    "disconnected": "critical",
    "stale_data": "critical",
    "partial_bad": "warning",
    "flapping": "warning",
}


@dataclass(frozen=True)
class PlcObservation:
    key: tuple[str, int, int]
    name: str
    connected: bool
    good_count: int
    bad_count: int
    seconds_since_success: float
    reconnects_in_window: int


@dataclass(frozen=True)
class DetectorConfig:
    stale_seconds: float
    partial_bad_ratio: float
    partial_bad_cycles: int
    flap_count: int
    recover_cycles: int


@dataclass
class OpenIncident:
    kind: str
    severity: str
    opened_at_mono: float
    clean_cycles: int = 0
    detail: dict = field(default_factory=dict)


@dataclass
class PlcMonitorState:
    open: dict[str, OpenIncident] = field(default_factory=dict)
    partial_bad_streak: int = 0
    disconnected_streak: int = 0


@dataclass
class EvalResult:
    state: PlcMonitorState
    opened: list[OpenIncident]
    resolved: list[str]


def _detail(kind: str, obs: PlcObservation, cfg: DetectorConfig) -> dict:
    return {
        "kind": kind,
        "good": obs.good_count,
        "bad": obs.bad_count,
        "seconds_since_success": round(obs.seconds_since_success, 1),
        "reconnects_in_window": obs.reconnects_in_window,
    }


def evaluate(
    prev: PlcMonitorState, obs: PlcObservation, cfg: DetectorConfig, now: float
) -> EvalResult:
    state = PlcMonitorState(
        open={k: OpenIncident(**vars(v)) for k, v in prev.open.items()},
        partial_bad_streak=prev.partial_bad_streak,
        disconnected_streak=prev.disconnected_streak,
    )
    opened: list[OpenIncident] = []
    resolved: list[str] = []

    # streak güncellemeleri
    state.disconnected_streak = state.disconnected_streak + 1 if not obs.connected else 0

    total = obs.good_count + obs.bad_count
    bad_ratio = (obs.bad_count / total) if total else 0.0
    if obs.connected and total > 0 and bad_ratio > cfg.partial_bad_ratio:
        state.partial_bad_streak += 1
    else:
        state.partial_bad_streak = 0

    conditions = {
        "disconnected": state.disconnected_streak >= 2,
        "stale_data": obs.connected and obs.seconds_since_success >= cfg.stale_seconds,
        "partial_bad": state.partial_bad_streak >= cfg.partial_bad_cycles,
        "flapping": obs.reconnects_in_window >= cfg.flap_count,
    }

    for kind, active in conditions.items():
        existing = state.open.get(kind)
        if active:
            if existing is None:
                inc = OpenIncident(
                    kind=kind,
                    severity=SEVERITY[kind],
                    opened_at_mono=now,
                    clean_cycles=0,
                    detail=_detail(kind, obs, cfg),
                )
                state.open[kind] = inc
                opened.append(inc)
            else:
                existing.clean_cycles = 0
                existing.detail = _detail(kind, obs, cfg)
        elif existing is not None:
            existing.clean_cycles += 1
            if existing.clean_cycles >= cfg.recover_cycles:
                del state.open[kind]
                resolved.append(kind)

    return EvalResult(state=state, opened=opened, resolved=resolved)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_detector.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/monitor/__init__.py scada-reporter/backend/app/monitor/detector.py scada-reporter/backend/tests/test_plc_detector.py
git commit -m "feat(plc-health): pure detector.evaluate state machine"
```

---

### Task 4: PlcHealthTracker (in-memory)

**Files:**
- Create: `scada-reporter/backend/app/collector/plc_health_tracker.py`
- Test: `scada-reporter/backend/tests/test_plc_health_tracker.py`

**Interfaces:**
- Consumes: `PlcObservation` from `app.monitor.detector` (Task 3 — already implemented).
- Produces: `PlcHealthTracker` with:
  - `record_read(key: tuple[str,int,int], name: str, good: int, bad: int, now: float) -> None`
  - `observe_connection(key: tuple[str,int,int], name: str, connected: bool, now: float) -> None`
  - `known_keys() -> list[tuple[str,int,int]]`
  - `snapshot(now: float, flap_window: float) -> list[PlcObservation]` — resets per-cycle good/bad counters, prunes reconnect timestamps outside `flap_window`.
  - module-level singleton `health_tracker = PlcHealthTracker()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plc_health_tracker.py
from app.collector.plc_health_tracker import PlcHealthTracker

KEY = ("10.0.0.1", 0, 1)


def test_record_read_tallies_and_resets_on_snapshot():
    t = PlcHealthTracker()
    t.record_read(KEY, "PLC1", good=5, bad=1, now=100.0)
    t.observe_connection(KEY, "PLC1", connected=True, now=100.0)
    obs = t.snapshot(now=100.0, flap_window=120.0)
    assert len(obs) == 1
    o = obs[0]
    assert o.key == KEY
    assert o.good_count == 5 and o.bad_count == 1
    assert o.connected is True
    # last success was now -> ~0 seconds since success
    assert o.seconds_since_success < 1.0
    # second snapshot: counters reset
    obs2 = t.snapshot(now=101.0, flap_window=120.0)
    assert obs2[0].good_count == 0 and obs2[0].bad_count == 0


def test_reconnect_transitions_counted_within_window():
    t = PlcHealthTracker()
    t.observe_connection(KEY, "PLC1", connected=False, now=0.0)
    t.observe_connection(KEY, "PLC1", connected=True, now=1.0)   # reconnect #1
    t.observe_connection(KEY, "PLC1", connected=False, now=2.0)
    t.observe_connection(KEY, "PLC1", connected=True, now=3.0)   # reconnect #2
    obs = t.snapshot(now=4.0, flap_window=120.0)
    assert obs[0].reconnects_in_window == 2
    # outside window -> pruned
    obs_later = t.snapshot(now=200.0, flap_window=120.0)
    assert obs_later[0].reconnects_in_window == 0


def test_seconds_since_success_uses_first_seen_when_never_good():
    t = PlcHealthTracker()
    t.record_read(KEY, "PLC1", good=0, bad=3, now=10.0)
    obs = t.snapshot(now=80.0, flap_window=120.0)
    assert obs[0].seconds_since_success >= 70.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_health_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.collector.plc_health_tracker'`

- [ ] **Step 3: Implement the tracker**

```python
# app/collector/plc_health_tracker.py
from __future__ import annotations

import threading

from app.monitor.detector import PlcObservation

Key = tuple[str, int, int]


class PlcHealthTracker:
    """Poller'dan beslenen, monitor'ün okuduğu in-memory PLC sağlık sayaçları."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[Key, dict] = {}

    def _blank(self, name: str, now: float) -> dict:
        return {
            "name": name,
            "good": 0,
            "bad": 0,
            "connected": False,
            "last_success_mono": None,
            "first_mono": now,
            "reconnect_times": [],
        }

    def record_read(self, key: Key, name: str, good: int, bad: int, now: float) -> None:
        with self._lock:
            d = self._data.setdefault(key, self._blank(name, now))
            if name:
                d["name"] = name
            d["good"] += good
            d["bad"] += bad
            if good > 0:
                d["last_success_mono"] = now

    def observe_connection(self, key: Key, name: str, connected: bool, now: float) -> None:
        with self._lock:
            d = self._data.setdefault(key, self._blank(name, now))
            if name:
                d["name"] = name
            if connected and not d["connected"]:
                d["reconnect_times"].append(now)
            d["connected"] = connected

    def known_keys(self) -> list[Key]:
        with self._lock:
            return list(self._data.keys())

    def snapshot(self, now: float, flap_window: float) -> list[PlcObservation]:
        with self._lock:
            out: list[PlcObservation] = []
            for key, d in self._data.items():
                d["reconnect_times"] = [t for t in d["reconnect_times"] if now - t <= flap_window]
                last = d["last_success_mono"]
                sss = (now - last) if last is not None else (now - d["first_mono"])
                out.append(
                    PlcObservation(
                        key=key,
                        name=d["name"],
                        connected=d["connected"],
                        good_count=d["good"],
                        bad_count=d["bad"],
                        seconds_since_success=sss,
                        reconnects_in_window=len(d["reconnect_times"]),
                    )
                )
                d["good"] = 0
                d["bad"] = 0
            return out


health_tracker = PlcHealthTracker()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_health_tracker.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/collector/plc_health_tracker.py scada-reporter/backend/tests/test_plc_health_tracker.py
git commit -m "feat(plc-health): in-memory PlcHealthTracker fed by poller"
```

---

### Task 5: notifier (webhook + e-posta kanalları)

**Files:**
- Create: `scada-reporter/backend/app/monitor/notifier.py`
- Test: `scada-reporter/backend/tests/test_plc_notifier.py`

**Interfaces:**
- Consumes: `settings` (Task 2).
- Produces:
  - `@dataclass(frozen=True) AlertPayload`: `plc_ip:str`, `plc_name:str`, `kind:str`, `severity:str`, `message:str`, `event:str` ("opened"|"resolved"), `detail:dict`.
  - `async def dispatch(payload: AlertPayload) -> None` — severity kapısını uygular, etkin kanallara gönderir, her kanal `try/except` ile sarılı (asla raise etmez).
  - `async def _send_webhook(payload) -> None`, `async def _send_email(payload) -> None` (test bunları monkeypatch'ler).
  - `_passes_severity(severity:str) -> bool` — `ALERT_MIN_SEVERITY`'e göre.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plc_notifier.py
import pytest

from app.monitor import notifier
from app.monitor.notifier import AlertPayload


def _payload(severity="critical", event="opened"):
    return AlertPayload(
        plc_ip="10.0.0.1", plc_name="PLC1", kind="disconnected",
        severity=severity, message="down", event=event, detail={},
    )


@pytest.mark.asyncio
async def test_dispatch_calls_enabled_channels(monkeypatch):
    calls = []
    monkeypatch.setattr(notifier.settings, "ALERT_WEBHOOK_URL", "http://hook")
    monkeypatch.setattr(notifier.settings, "ALERT_EMAIL_ENABLED", True)
    monkeypatch.setattr(notifier.settings, "ALERT_MIN_SEVERITY", "warning")
    monkeypatch.setattr(notifier, "_send_webhook", lambda p: calls.append("webhook") or _noop())
    monkeypatch.setattr(notifier, "_send_email", lambda p: calls.append("email") or _noop())
    await notifier.dispatch(_payload())
    assert set(calls) == {"webhook", "email"}


@pytest.mark.asyncio
async def test_severity_gate_blocks_low_severity(monkeypatch):
    calls = []
    monkeypatch.setattr(notifier.settings, "ALERT_WEBHOOK_URL", "http://hook")
    monkeypatch.setattr(notifier.settings, "ALERT_MIN_SEVERITY", "critical")
    monkeypatch.setattr(notifier, "_send_webhook", lambda p: calls.append("webhook") or _noop())
    await notifier.dispatch(_payload(severity="warning"))
    assert calls == []  # warning < critical -> blocked


@pytest.mark.asyncio
async def test_channel_error_is_swallowed(monkeypatch):
    monkeypatch.setattr(notifier.settings, "ALERT_WEBHOOK_URL", "http://hook")

    async def _boom(p):
        raise RuntimeError("network down")

    monkeypatch.setattr(notifier, "_send_webhook", _boom)
    # must not raise
    await notifier.dispatch(_payload())


async def _noop():
    return None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_notifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.monitor.notifier'`

- [ ] **Step 3: Implement the notifier**

```python
# app/monitor/notifier.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"warning": 0, "critical": 1}


@dataclass(frozen=True)
class AlertPayload:
    plc_ip: str
    plc_name: str
    kind: str
    severity: str
    message: str
    event: str  # "opened" | "resolved"
    detail: dict


def _passes_severity(severity: str) -> bool:
    floor = _SEVERITY_RANK.get(settings.ALERT_MIN_SEVERITY, 0)
    return _SEVERITY_RANK.get(severity, 0) >= floor


async def _send_webhook(payload: AlertPayload) -> None:
    body = {
        "plc_ip": payload.plc_ip,
        "plc_name": payload.plc_name,
        "kind": payload.kind,
        "severity": payload.severity,
        "message": payload.message,
        "event": payload.event,
        "detail": payload.detail,
    }
    async with httpx.AsyncClient(timeout=10.0) as cx:
        await cx.post(settings.ALERT_WEBHOOK_URL, json=body)


async def _send_email(payload: AlertPayload) -> None:
    recipients = [r.strip() for r in settings.ALERT_EMAIL_TO.split(",") if r.strip()]
    if not recipients:
        return
    msg = EmailMessage()
    msg["Subject"] = f"[SCADA {payload.severity.upper()}] {payload.plc_name} {payload.kind} ({payload.event})"
    msg["From"] = settings.ALERT_EMAIL_FROM or settings.SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg.set_content(
        f"PLC: {payload.plc_name} ({payload.plc_ip})\n"
        f"Sorun: {payload.kind} / {payload.severity}\n"
        f"Durum: {payload.event}\n"
        f"Mesaj: {payload.message}\n"
        f"Detay: {payload.detail}\n"
    )

    def _send_sync() -> None:
        import smtplib

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)

    await asyncio.get_event_loop().run_in_executor(None, _send_sync)


async def dispatch(payload: AlertPayload) -> None:
    """Etkin kanallara uyarı gönder. Severity kapısı + kanal hatalarını yut."""
    if not _passes_severity(payload.severity):
        return
    if settings.ALERT_WEBHOOK_URL:
        try:
            await _send_webhook(payload)
        except Exception as e:
            logger.warning("Webhook uyarı gönderilemedi: %s", e)
    if settings.ALERT_EMAIL_ENABLED:
        try:
            await _send_email(payload)
        except Exception as e:
            logger.warning("E-posta uyarı gönderilemedi: %s", e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_notifier.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/monitor/notifier.py scada-reporter/backend/tests/test_plc_notifier.py
git commit -m "feat(plc-health): notifier with webhook + email channels"
```

---

### Task 6: Monitor persist katmanı + loop

**Files:**
- Create: `scada-reporter/backend/app/monitor/monitor.py`
- Test: `scada-reporter/backend/tests/test_plc_monitor.py`

**Interfaces:**
- Consumes: `evaluate`, `PlcObservation`, `DetectorConfig`, `PlcMonitorState`, `EvalResult` (Task 3); `health_tracker` (Task 4); `notifier.dispatch`, `AlertPayload` (Task 5); `plc_manager` (s7_collector); models (Task 1); `settings` (Task 2).
- Produces:
  - `_cfg() -> DetectorConfig` — settings'ten.
  - `_message(kind, obs) -> str` — insan-okur mesaj.
  - `async def apply_result(obs: PlcObservation, result: EvalResult, sessionmaker=AsyncSessionLocal) -> None` — `plc_health` upsert + `plc_incident` open/resolve + notifier çağrısı. **Test bunu doğrudan çağırır.**
  - `async def plc_monitor_loop() -> None` — sonsuz döngü; her `PLC_MONITOR_INTERVAL` sn snapshot→evaluate→apply_result.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plc_monitor.py
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident
from app.monitor import monitor
from app.monitor.detector import (
    DetectorConfig,
    EvalResult,
    OpenIncident,
    PlcMonitorState,
    PlcObservation,
)

KEY = ("10.0.0.1", 0, 1)


def _obs(connected=False, good=0, bad=0):
    return PlcObservation(
        key=KEY, name="PLC1", connected=connected, good_count=good,
        bad_count=bad, seconds_since_success=99.0, reconnects_in_window=0,
    )


@pytest.fixture
def _no_notify(monkeypatch):
    async def _noop(payload):
        return None
    monkeypatch.setattr(monitor.notifier, "dispatch", _noop)


@pytest.mark.asyncio
async def test_apply_result_opens_incident_and_upserts_health(
    db_engine, db_session: AsyncSession, _no_notify
):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    inc = OpenIncident(kind="disconnected", severity="critical", opened_at_mono=1.0, detail={"x": 1})
    result = EvalResult(state=PlcMonitorState(open={"disconnected": inc}), opened=[inc], resolved=[])
    await monitor.apply_result(_obs(), result, sessionmaker=sm)

    incidents = (await db_session.execute(select(PlcIncident))).scalars().all()
    assert len(incidents) == 1
    assert incidents[0].kind == "disconnected"
    assert incidents[0].resolved_at is None

    health = (await db_session.execute(select(PlcHealth))).scalar_one()
    assert health.plc_ip == "10.0.0.1"
    assert health.open_incident_count == 1


@pytest.mark.asyncio
async def test_apply_result_resolves_open_incident(
    db_engine, db_session: AsyncSession, _no_notify
):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    # önce aç
    inc = OpenIncident(kind="disconnected", severity="critical", opened_at_mono=1.0, detail={})
    await monitor.apply_result(
        _obs(), EvalResult(PlcMonitorState(open={"disconnected": inc}), [inc], []), sessionmaker=sm
    )
    # sonra çöz
    await monitor.apply_result(
        _obs(connected=True, good=5),
        EvalResult(PlcMonitorState(open={}), [], ["disconnected"]),
        sessionmaker=sm,
    )
    row = (await db_session.execute(select(PlcIncident))).scalar_one()
    assert row.resolved_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_monitor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.monitor.monitor'`

- [ ] **Step 3: Implement monitor**

```python
# app/monitor/monitor.py
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.collector.plc_health_tracker import health_tracker
from app.collector.s7_collector import plc_manager
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident
from app.monitor import notifier
from app.monitor.detector import (
    DetectorConfig,
    EvalResult,
    PlcMonitorState,
    PlcObservation,
    evaluate,
)
from app.monitor.notifier import AlertPayload

logger = logging.getLogger(__name__)

_MESSAGES = {
    "disconnected": "PLC bağlantısı koptu",
    "stale_data": "Bağlı ama veri akmıyor (bayat)",
    "partial_bad": "Bazı tag'ler sürekli hatalı (kısmi)",
    "flapping": "PLC sürekli bağlanıp kopuyor",
}


def _cfg() -> DetectorConfig:
    return DetectorConfig(
        stale_seconds=settings.PLC_STALE_SECONDS,
        partial_bad_ratio=settings.PLC_PARTIAL_BAD_RATIO,
        partial_bad_cycles=settings.PLC_PARTIAL_BAD_CYCLES,
        flap_count=settings.PLC_FLAP_COUNT,
        recover_cycles=settings.PLC_RECOVER_CYCLES,
    )


def _message(kind: str) -> str:
    return _MESSAGES.get(kind, kind)


async def apply_result(
    obs: PlcObservation, result: EvalResult, sessionmaker=AsyncSessionLocal
) -> None:
    ip, rack, slot = obs.key
    now_dt = datetime.now(UTC)
    payloads: list[AlertPayload] = []

    async with sessionmaker() as db:
        # açılan incident'lar
        for inc in result.opened:
            db.add(
                PlcIncident(
                    plc_ip=ip, plc_name=obs.name, rack=rack, slot=slot,
                    kind=inc.kind, severity=inc.severity, message=_message(inc.kind),
                    detail=inc.detail, opened_at=now_dt, notified=True,
                )
            )
            payloads.append(
                AlertPayload(ip, obs.name, inc.kind, inc.severity, _message(inc.kind), "opened", inc.detail)
            )

        # çözülen incident'lar
        for kind in result.resolved:
            rows = (
                await db.execute(
                    select(PlcIncident).where(
                        PlcIncident.plc_ip == ip,
                        PlcIncident.rack == rack,
                        PlcIncident.slot == slot,
                        PlcIncident.kind == kind,
                        PlcIncident.resolved_at.is_(None),
                    )
                )
            ).scalars().all()
            for row in rows:
                row.resolved_at = now_dt
            sev = rows[0].severity if rows else "warning"
            payloads.append(
                AlertPayload(ip, obs.name, kind, sev, _message(kind), "resolved", {})
            )

        # plc_health upsert
        health = (
            await db.execute(
                select(PlcHealth).where(
                    PlcHealth.plc_ip == ip, PlcHealth.rack == rack, PlcHealth.slot == slot
                )
            )
        ).scalar_one_or_none()
        if health is None:
            health = PlcHealth(plc_ip=ip, rack=rack, slot=slot)
            db.add(health)
        health.plc_name = obs.name
        health.connected = obs.connected
        health.good_last_cycle = obs.good_count
        health.bad_last_cycle = obs.bad_count
        health.reconnects_last_min = obs.reconnects_in_window
        health.consecutive_fail = result.state.disconnected_streak
        health.open_incident_count = len(result.state.open)
        health.updated_at = now_dt
        if obs.good_count > 0:
            health.last_success_at = now_dt

        await db.commit()

    # bildirim (DB commit'ten sonra, döngüyü kırmadan)
    for p in payloads:
        try:
            await notifier.dispatch(p)
        except Exception as e:  # defansif — dispatch zaten yutar
            logger.warning("Uyarı gönderilemedi: %s", e)


async def plc_monitor_loop() -> None:
    """Periyodik PLC sağlık değerlendirme döngüsü."""
    import time

    logger.info("PLC monitor basladi (periyot: %ds)", settings.PLC_MONITOR_INTERVAL)
    cfg = _cfg()
    states: dict[tuple[str, int, int], PlcMonitorState] = {}
    while True:
        try:
            now = time.monotonic()
            status = plc_manager.status()  # {ip: connected}
            for key in health_tracker.known_keys():
                health_tracker.observe_connection(key, "", status.get(key[0], False), now)
            for obs in health_tracker.snapshot(now, settings.PLC_FLAP_WINDOW_SECONDS):
                prev = states.get(obs.key, PlcMonitorState())
                result = evaluate(prev, obs, cfg, now)
                states[obs.key] = result.state
                await apply_result(obs, result)
        except Exception as e:
            logger.error("PLC monitor hatasi: %s", e)
        await asyncio.sleep(settings.PLC_MONITOR_INTERVAL)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_monitor.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/monitor/monitor.py scada-reporter/backend/tests/test_plc_monitor.py
git commit -m "feat(plc-health): monitor persist layer + evaluation loop"
```

---

### Task 7: Poller'ı tracker'a bağla + monitor'ü lifespan'de başlat

**Files:**
- Modify: `scada-reporter/backend/app/collector/poller.py` (`read_plc_group` — tracker.record_read)
- Modify: `scada-reporter/backend/app/main.py` (lifespan — monitor task)
- Test: `scada-reporter/backend/tests/test_poller_feeds_tracker.py`

**Interfaces:**
- Consumes: `health_tracker.record_read` (Task 4); `plc_monitor_loop` (Task 6).
- Produces: poller her PLC grup okumasından sonra `health_tracker.record_read(key, name?, good, bad, now)` çağırır; lifespan `RUN_COLLECTOR` iken `plc_monitor_loop`'u task olarak başlatır ve kapanışta iptal eder.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_poller_feeds_tracker.py
import pytest

from app.collector import poller
from app.collector.plc_health_tracker import PlcHealthTracker
from app.collector.s7_collector import BAD, GOOD


@pytest.mark.asyncio
async def test_read_plc_group_records_good_bad(monkeypatch):
    tracker = PlcHealthTracker()
    monkeypatch.setattr(poller, "health_tracker", tracker)

    async def fake_batch(ip, rack, slot, specs):
        return [(1.0, GOOD), (None, BAD), (2.0, GOOD)]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", fake_batch)

    key = ("10.0.0.9", 0, 1)
    # items: (tag_id, spec) — spec opaque burada
    items = [(1, object()), (2, object()), (3, object())]
    await poller.read_plc_group(key, items, timeout=5.0)

    obs = tracker.snapshot(now=1.0, flap_window=120.0)
    assert len(obs) == 1
    assert obs[0].good_count == 2
    assert obs[0].bad_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_poller_feeds_tracker.py -v`
Expected: FAIL — `AttributeError: module 'app.collector.poller' has no attribute 'health_tracker'`

- [ ] **Step 3: Wire tracker into poller**

In `app/collector/poller.py`, add to imports (near the other `from app.collector...` imports):

```python
from app.collector.plc_health_tracker import health_tracker
```

In `read_plc_group`, replace the final `return [...]` block so it records before returning:

```python
    rows = [
        (tag_id, value, quality)
        for (tag_id, _), (value, quality) in zip(items, results, strict=False)
    ]
    good = sum(1 for _, _, q in rows if q == GOOD)
    bad = len(rows) - good
    health_tracker.record_read(key, "", good, bad, time.monotonic())
    return rows
```

(Ensure `GOOD` is imported in poller — it imports from `app.collector.s7_collector`; add `GOOD` to that import if missing. `BAD` is already imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_poller_feeds_tracker.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Wire monitor into lifespan**

In `app/main.py` lifespan, inside the `if settings.RUN_COLLECTOR:` block (after `opcua_task = asyncio.create_task(_start_opcua())`), add:

```python
        from app.monitor.monitor import plc_monitor_loop

        monitor_task = asyncio.create_task(plc_monitor_loop())
        logger.info("PLC monitor baslatildi")
```

Declare `monitor_task: asyncio.Task | None = None` next to `poll_task`/`opcua_task` declarations, and in the shutdown section (after `if poll_task:` block) add:

```python
    if monitor_task:
        monitor_task.cancel()
```

- [ ] **Step 6: Run full backend suite to verify no regression**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/ -q`
Expected: PASS (all green, including new tests)

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/collector/poller.py scada-reporter/backend/app/main.py scada-reporter/backend/tests/test_poller_feeds_tracker.py
git commit -m "feat(plc-health): feed tracker from poller + start monitor in lifespan"
```

---

### Task 8: API endpoint'leri (health / incidents / summary / ack)

**Files:**
- Modify: `scada-reporter/backend/app/api/plc.py` (yeni endpoint'ler)
- Test: `scada-reporter/backend/tests/test_plc_health_api.py`

**Interfaces:**
- Consumes: models (Task 1); `get_current_user`, `require_perm` (auth).
- Produces (router prefix `/plc` zaten var):
  - `GET /api/plc/health` → `list[dict]` her PLC sağlık satırı.
  - `GET /api/plc/incidents?open=<bool>&plc=<ip>&limit=<int>` → `list[dict]` incident.
  - `GET /api/plc/incidents/summary` → `{"open_total":int,"critical":int,"warning":int}`.
  - `POST /api/plc/incidents/{id}/ack` → `{"acknowledged":true,"id":id}` (perm `plc:manage`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plc_health_api.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident
from app.models.user import User


async def _admin_token(client: AsyncClient, db: AsyncSession, username: str) -> str:
    db.add(User(username=username, email=f"{username}@t.com",
                hashed_password=hash_password("pw123"), role="admin"))
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_health_endpoint_returns_rows(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "h_admin")
    db_session.add(PlcHealth(plc_ip="10.0.0.1", plc_name="P1", connected=True))
    await db_session.commit()
    r = await client.get("/api/plc/health", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()[0]["plc_ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_incidents_open_filter_and_summary(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "i_admin")
    from datetime import UTC, datetime
    db_session.add(PlcIncident(plc_ip="10.0.0.1", plc_name="P1", kind="disconnected",
                               severity="critical", message="down"))
    db_session.add(PlcIncident(plc_ip="10.0.0.2", plc_name="P2", kind="flapping",
                               severity="warning", message="flap",
                               resolved_at=datetime.now(UTC)))
    await db_session.commit()
    h = {"Authorization": f"Bearer {tok}"}

    r_open = await client.get("/api/plc/incidents?open=true", headers=h)
    assert r_open.status_code == 200
    assert len(r_open.json()) == 1
    assert r_open.json()[0]["kind"] == "disconnected"

    r_sum = await client.get("/api/plc/incidents/summary", headers=h)
    assert r_sum.json() == {"open_total": 1, "critical": 1, "warning": 0}


@pytest.mark.asyncio
async def test_ack_incident(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "a_admin")
    inc = PlcIncident(plc_ip="10.0.0.1", plc_name="P1", kind="disconnected",
                      severity="critical", message="down")
    db_session.add(inc)
    await db_session.commit()
    await db_session.refresh(inc)
    r = await client.post(f"/api/plc/incidents/{inc.id}/ack",
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["acknowledged"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_health_api.py -v`
Expected: FAIL — 404 on `/api/plc/health` (endpoint yok)

- [ ] **Step 3: Add endpoints to plc.py**

In `app/api/plc.py`, add imports at top:

```python
from datetime import UTC, datetime

from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident
```

Append these endpoints to the router:

```python
@router.get("/health")
async def plc_health(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    rows = (await db.execute(select(PlcHealth).order_by(PlcHealth.plc_name))).scalars().all()
    return [
        {
            "plc_ip": r.plc_ip,
            "plc_name": r.plc_name,
            "rack": r.rack,
            "slot": r.slot,
            "connected": r.connected,
            "last_success_at": r.last_success_at,
            "consecutive_fail": r.consecutive_fail,
            "last_error": r.last_error,
            "good_last_cycle": r.good_last_cycle,
            "bad_last_cycle": r.bad_last_cycle,
            "reconnects_last_min": r.reconnects_last_min,
            "open_incident_count": r.open_incident_count,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


def _incident_dict(r: PlcIncident) -> dict:
    return {
        "id": r.id,
        "plc_ip": r.plc_ip,
        "plc_name": r.plc_name,
        "kind": r.kind,
        "severity": r.severity,
        "message": r.message,
        "detail": r.detail,
        "opened_at": r.opened_at,
        "resolved_at": r.resolved_at,
        "acknowledged_by": r.acknowledged_by,
        "acknowledged_at": r.acknowledged_at,
    }


@router.get("/incidents")
async def list_incidents(
    open: bool | None = None,
    plc: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(PlcIncident).order_by(PlcIncident.opened_at.desc())
    if open is True:
        stmt = stmt.where(PlcIncident.resolved_at.is_(None))
    elif open is False:
        stmt = stmt.where(PlcIncident.resolved_at.is_not(None))
    if plc:
        stmt = stmt.where(PlcIncident.plc_ip == plc)
    stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [_incident_dict(r) for r in rows]


@router.get("/incidents/summary")
async def incidents_summary(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    rows = (
        await db.execute(select(PlcIncident).where(PlcIncident.resolved_at.is_(None)))
    ).scalars().all()
    critical = sum(1 for r in rows if r.severity == "critical")
    warning = sum(1 for r in rows if r.severity == "warning")
    return {"open_total": len(rows), "critical": critical, "warning": warning}


@router.post("/incidents/{incident_id}/ack")
async def ack_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_perm("plc:manage")),
):
    inc = await db.get(PlcIncident, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident bulunamadı")
    inc.acknowledged_by = user.username
    inc.acknowledged_at = datetime.now(UTC)
    await db.commit()
    return {"acknowledged": True, "id": incident_id}
```

> **Routing note:** `/incidents/summary` ile `/incidents/{incident_id}/ack` çakışmaz çünkü farklı path yapısı; ancak FastAPI'de statik path'i parametreli path'ten önce tanımladık (summary ack'ten önce gelmesine gerek yok, biri GET biri POST). Sıra önemli değil.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_health_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/plc.py scada-reporter/backend/tests/test_plc_health_api.py
git commit -m "feat(plc-health): health/incidents/summary/ack API endpoints"
```

---

### Task 9: Resolved incident retention (scheduler prune job)

**Files:**
- Create: `scada-reporter/backend/app/monitor/retention.py`
- Modify: `scada-reporter/backend/app/services/scheduler.py` (start_scheduler — prune job ekle)
- Test: `scada-reporter/backend/tests/test_plc_retention.py`

**Interfaces:**
- Consumes: `PlcIncident` (Task 1); `settings.PLC_INCIDENT_RETENTION_DAYS`.
- Produces: `async def prune_resolved_incidents(sessionmaker=AsyncSessionLocal, now: datetime | None = None) -> int` — `resolved_at` retention'dan eski satırları siler, silinen sayısı döner. Açık incident'lara dokunmaz.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plc_retention.py
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.plc_incident import PlcIncident
from app.monitor.retention import prune_resolved_incidents


@pytest.mark.asyncio
async def test_prune_removes_old_resolved_keeps_open_and_recent(db_engine, db_session):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    now = datetime(2026, 6, 21, tzinfo=UTC)
    old = now - timedelta(days=200)
    recent = now - timedelta(days=5)
    db_session.add_all([
        PlcIncident(plc_ip="1", kind="disconnected", severity="critical", message="o",
                    resolved_at=old),                       # silinmeli
        PlcIncident(plc_ip="2", kind="disconnected", severity="critical", message="r",
                    resolved_at=recent),                    # kalmalı
        PlcIncident(plc_ip="3", kind="disconnected", severity="critical", message="open"),  # açık, kalmalı
    ])
    await db_session.commit()

    deleted = await prune_resolved_incidents(sessionmaker=sm, now=now)
    assert deleted == 1
    remaining = (await db_session.execute(select(PlcIncident))).scalars().all()
    assert len(remaining) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_retention.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.monitor.retention'`

- [ ] **Step 3: Implement retention + register job**

```python
# app/monitor/retention.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.plc_incident import PlcIncident


async def prune_resolved_incidents(
    sessionmaker=AsyncSessionLocal, now: datetime | None = None
) -> int:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=settings.PLC_INCIDENT_RETENTION_DAYS)
    async with sessionmaker() as db:
        result = await db.execute(
            delete(PlcIncident).where(
                PlcIncident.resolved_at.is_not(None), PlcIncident.resolved_at < cutoff
            )
        )
        await db.commit()
        return result.rowcount or 0
```

In `app/services/scheduler.py`, inside `start_scheduler` after `await _sync_db_to_scheduler()`, add a daily prune job:

```python
    from app.monitor.retention import prune_resolved_incidents

    _scheduler.add_job(
        prune_resolved_incidents,
        "cron",
        id="plc_incident_prune",
        hour=3,
        minute=30,
        replace_existing=True,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/pytest tests/test_plc_retention.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/monitor/retention.py scada-reporter/backend/app/services/scheduler.py scada-reporter/backend/tests/test_plc_retention.py
git commit -m "feat(plc-health): daily prune job for resolved incidents"
```

---

### Task 10: Frontend API client (types + functions)

**Files:**
- Modify: `scada-reporter/frontend/src/api/client.ts` (PLC health/incident tipleri + fonksiyonlar)
- Test: `scada-reporter/frontend/src/api/__tests__/plcHealth.test.ts`

**Interfaces:**
- Produces (client.ts'e ek):
  - `interface PlcHealthRow { plc_ip:string; plc_name:string; rack:number; slot:number; connected:boolean; last_success_at:string|null; consecutive_fail:number; last_error:string|null; good_last_cycle:number; bad_last_cycle:number; reconnects_last_min:number; open_incident_count:number; updated_at:string }`
  - `interface PlcIncidentRow { id:number; plc_ip:string; plc_name:string; kind:string; severity:'critical'|'warning'; message:string; detail:Record<string,unknown>; opened_at:string; resolved_at:string|null; acknowledged_by:string|null; acknowledged_at:string|null }`
  - `interface IncidentSummary { open_total:number; critical:number; warning:number }`
  - `getPlcHealth()`, `getPlcIncidents(params?)`, `getIncidentSummary()`, `ackIncident(id)`.

- [ ] **Step 1: Write the failing test**

```typescript
// src/api/__tests__/plcHealth.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../client'
import { getPlcIncidents, getIncidentSummary, ackIncident } from '../client'

describe('plc health api', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('getPlcIncidents passes open + plc query params', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: [] } as never)
    await getPlcIncidents({ open: true, plc: '10.0.0.1' })
    expect(spy).toHaveBeenCalledWith('/plc/incidents?open=true&plc=10.0.0.1')
  })

  it('getIncidentSummary hits summary endpoint', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: { open_total: 0, critical: 0, warning: 0 } } as never)
    await getIncidentSummary()
    expect(spy).toHaveBeenCalledWith('/plc/incidents/summary')
  })

  it('ackIncident posts to ack endpoint', async () => {
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: { acknowledged: true } } as never)
    await ackIncident(7)
    expect(spy).toHaveBeenCalledWith('/plc/incidents/7/ack')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm test -- plcHealth`
Expected: FAIL — `getPlcIncidents is not exported` (veya import hatası)

- [ ] **Step 3: Add types + functions to client.ts**

In `src/api/client.ts`, after the existing PLC block (the `deletePlc` line, ~184), add:

```typescript
// PLC sağlık & incident'lar
export interface PlcHealthRow {
  plc_ip: string; plc_name: string; rack: number; slot: number; connected: boolean
  last_success_at: string | null; consecutive_fail: number; last_error: string | null
  good_last_cycle: number; bad_last_cycle: number; reconnects_last_min: number
  open_incident_count: number; updated_at: string
}
export interface PlcIncidentRow {
  id: number; plc_ip: string; plc_name: string; kind: string
  severity: 'critical' | 'warning'; message: string; detail: Record<string, unknown>
  opened_at: string; resolved_at: string | null
  acknowledged_by: string | null; acknowledged_at: string | null
}
export interface IncidentSummary { open_total: number; critical: number; warning: number }

export const getPlcHealth = () => api.get<PlcHealthRow[]>('/plc/health')
export const getPlcIncidents = (params?: { open?: boolean; plc?: string; limit?: number }) => {
  const q = new URLSearchParams()
  if (params?.open !== undefined) q.set('open', String(params.open))
  if (params?.plc) q.set('plc', params.plc)
  if (params?.limit) q.set('limit', String(params.limit))
  const qs = q.toString()
  return api.get<PlcIncidentRow[]>(`/plc/incidents${qs ? `?${qs}` : ''}`)
}
export const getIncidentSummary = () => api.get<IncidentSummary>('/plc/incidents/summary')
export const ackIncident = (id: number) => api.post(`/plc/incidents/${id}/ack`)
```

> If `api` is not already an exported symbol in client.ts, add `export` to its declaration (the test imports it). Verify the axios instance is named `api`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/frontend && pnpm test -- plcHealth`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/api/__tests__/plcHealth.test.ts
git commit -m "feat(plc-health): frontend API client for health/incidents"
```

---

### Task 11: PlcHealth sayfası + alert badge bileşeni

**Files:**
- Create: `scada-reporter/frontend/src/pages/PlcHealth.tsx`
- Create: `scada-reporter/frontend/src/components/PlcAlertBadge.tsx`
- Create: `scada-reporter/frontend/src/pages/__tests__/PlcHealth.test.tsx`

**Interfaces:**
- Consumes: `getPlcHealth`, `getPlcIncidents`, `getIncidentSummary`, `ackIncident` (Task 10); `useAuth().can` (RBAC); `useTranslation('plcHealth')`.
- Produces: `PlcHealth` default export (route component); `PlcAlertBadge` default export (layout badge).

- [ ] **Step 1: Write the failing test**

```tsx
// src/pages/__tests__/PlcHealth.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PlcHealth from '../PlcHealth'
import * as client from '../../api/client'

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ can: () => true }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('PlcHealth page', () => {
  it('renders open incidents from api', async () => {
    vi.spyOn(client, 'getIncidentSummary').mockResolvedValue({ data: { open_total: 1, critical: 1, warning: 0 } } as never)
    vi.spyOn(client, 'getPlcIncidents').mockResolvedValue({
      data: [{ id: 1, plc_ip: '10.0.0.1', plc_name: 'P1', kind: 'disconnected', severity: 'critical', message: 'down', detail: {}, opened_at: '2026-06-21T00:00:00Z', resolved_at: null, acknowledged_by: null, acknowledged_at: null }],
    } as never)
    vi.spyOn(client, 'getPlcHealth').mockResolvedValue({ data: [] } as never)

    render(wrap(<PlcHealth />))
    await waitFor(() => expect(screen.getByText('P1')).toBeInTheDocument())
    expect(screen.getByText('down')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm test -- PlcHealth`
Expected: FAIL — `Cannot find module '../PlcHealth'`

- [ ] **Step 3: Implement page + badge**

```tsx
// src/components/PlcAlertBadge.tsx
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getIncidentSummary } from '../api/client'

export default function PlcAlertBadge() {
  const { t } = useTranslation('plcHealth')
  const { data } = useQuery({
    queryKey: ['plc-incident-summary'],
    queryFn: () => getIncidentSummary().then((r) => r.data),
    refetchInterval: 10000,
  })
  const open = data?.open_total ?? 0
  if (open === 0) return null
  const critical = data?.critical ?? 0
  return (
    <Link
      to="/plc-health"
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium ${critical > 0 ? 'bg-red-900/40 text-red-300' : 'bg-yellow-900/40 text-yellow-300'}`}
      title={t('open_problems', { count: open })}
    >
      <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
      {t('alerts', { count: open })}
    </Link>
  )
}
```

```tsx
// src/pages/PlcHealth.tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import {
  getPlcHealth, getPlcIncidents, getIncidentSummary, ackIncident,
  type PlcIncidentRow,
} from '../api/client'

function sevClass(sev: string) {
  return sev === 'critical' ? 'bg-red-900/30 text-red-300' : 'bg-yellow-900/30 text-yellow-300'
}

export default function PlcHealth() {
  const { t } = useTranslation('plcHealth')
  const { can } = useAuth()
  const qc = useQueryClient()

  const { data: summary } = useQuery({
    queryKey: ['plc-incident-summary'],
    queryFn: () => getIncidentSummary().then((r) => r.data),
    refetchInterval: 10000,
  })
  const { data: open = [] } = useQuery({
    queryKey: ['plc-incidents-open'],
    queryFn: () => getPlcIncidents({ open: true }).then((r) => r.data),
    refetchInterval: 10000,
  })
  const { data: health = [] } = useQuery({
    queryKey: ['plc-health'],
    queryFn: () => getPlcHealth().then((r) => r.data),
    refetchInterval: 10000,
  })
  const { data: history = [] } = useQuery({
    queryKey: ['plc-incidents-history'],
    queryFn: () => getPlcIncidents({ open: false, limit: 50 }).then((r) => r.data),
    refetchInterval: 30000,
  })

  const ack = useMutation({
    mutationFn: (id: number) => ackIncident(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plc-incidents-open'] }),
  })

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">{t('title')}</h1>
          <p className="text-sm text-gray-500 mt-0.5">{t('subtitle')}</p>
        </div>
        <div className="flex gap-2 text-sm">
          <span className="px-3 py-1.5 rounded-lg bg-red-900/30 text-red-300">
            {t('critical')}: {summary?.critical ?? 0}
          </span>
          <span className="px-3 py-1.5 rounded-lg bg-yellow-900/30 text-yellow-300">
            {t('warning')}: {summary?.warning ?? 0}
          </span>
        </div>
      </div>

      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2">{t('open_incidents')}</h2>
        {open.length === 0 ? (
          <p className="text-sm text-green-400">{t('all_healthy')}</p>
        ) : (
          <div className="grid gap-2">
            {open.map((i: PlcIncidentRow) => (
              <div key={i.id} className={`flex items-center justify-between px-4 py-2.5 rounded-lg ${sevClass(i.severity)}`}>
                <div>
                  <span className="font-medium">{i.plc_name || i.plc_ip}</span>
                  <span className="mx-2 opacity-60">·</span>
                  <span>{i.message}</span>
                  <span className="ml-2 text-xs opacity-60">{new Date(i.opened_at).toLocaleString()}</span>
                </div>
                {can('plc:manage') && !i.acknowledged_by && (
                  <button onClick={() => ack.mutate(i.id)} className="text-xs px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-200">
                    {t('ack')}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2">{t('per_plc')}</h2>
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 uppercase">
                <th className="px-4 py-2 text-start">{t('col_plc')}</th>
                <th className="px-4 py-2 text-start">{t('col_status')}</th>
                <th className="px-4 py-2 text-start">{t('col_last_success')}</th>
                <th className="px-4 py-2 text-start">{t('col_fail')}</th>
                <th className="px-4 py-2 text-start">{t('col_reconnects')}</th>
              </tr>
            </thead>
            <tbody>
              {health.map((h) => (
                <tr key={`${h.plc_ip}-${h.rack}-${h.slot}`} className="border-t border-gray-800">
                  <td className="px-4 py-2 text-gray-200">{h.plc_name || h.plc_ip}</td>
                  <td className="px-4 py-2">
                    <span className={h.connected ? 'text-green-400' : 'text-red-400'}>
                      {h.connected ? t('connected') : t('disconnected')}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-400">{h.last_success_at ? new Date(h.last_success_at).toLocaleString() : '—'}</td>
                  <td className="px-4 py-2 text-gray-400">{h.consecutive_fail}</td>
                  <td className="px-4 py-2 text-gray-400">{h.reconnects_last_min}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2">{t('history')}</h2>
        <div className="text-xs text-gray-500 space-y-1">
          {history.map((i: PlcIncidentRow) => (
            <div key={i.id}>
              {new Date(i.opened_at).toLocaleString()} — {i.plc_name || i.plc_ip}: {i.message}
              {i.resolved_at && ` (${t('resolved')}: ${new Date(i.resolved_at).toLocaleString()})`}
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/frontend && pnpm test -- PlcHealth`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/pages/PlcHealth.tsx scada-reporter/frontend/src/components/PlcAlertBadge.tsx scada-reporter/frontend/src/pages/__tests__/PlcHealth.test.tsx
git commit -m "feat(plc-health): PlcHealth page + alert badge component"
```

---

### Task 12: Route + nav + i18n stringleri + client regen

**Files:**
- Modify: `scada-reporter/frontend/src/App.tsx` (route)
- Modify: `scada-reporter/frontend/src/components/Layout.tsx` (nav item + badge)
- Modify: i18n locale dosyaları (en, tr, ru, de, ar) — yeni `plcHealth` namespace
- Test: manuel doğrulama (aşağıda) + `just frontend-check`

**Interfaces:**
- Consumes: `PlcHealth` page, `PlcAlertBadge` (Task 11).
- Produces: `/plc-health` route + nav linki + 5 dilde `plcHealth` çevirileri.

- [ ] **Step 1: Add route to App.tsx**

In `src/App.tsx`, add import: `import PlcHealth from './pages/PlcHealth'`. Add route inside the Layout `<Route>` block (after the `plc` route):

```tsx
              <Route path="plc-health" element={<PlcHealth />} />
```

- [ ] **Step 2: Add nav item + badge to Layout**

First inspect `src/components/Layout.tsx` to find the nav-items array/list and the top bar. Add a nav entry pointing to `/plc-health` (label `t('plcHealth:nav')`) following the existing nav pattern (copy the shape of the `plc` nav item). In the top bar, render `<PlcAlertBadge />` (import it). Match the file's existing structure — do not invent a new nav system.

- [ ] **Step 3: Add i18n strings (5 languages)**

Locate the i18n resource files (likely `src/i18n/` or `src/locales/<lang>/`). For EACH language (en, tr, ru, de, ar) add a `plcHealth` namespace. Turkish values:

```json
{
  "title": "PLC Sağlık",
  "subtitle": "PLC bağlantı ve veri sağlığı izleme",
  "nav": "PLC Sağlık",
  "open_incidents": "Açık Sorunlar",
  "all_healthy": "Tüm PLC'ler sağlıklı",
  "per_plc": "PLC Bazında Durum",
  "history": "Geçmiş",
  "critical": "Kritik",
  "warning": "Uyarı",
  "ack": "Onayla",
  "resolved": "çözüldü",
  "connected": "Bağlı",
  "disconnected": "Kopuk",
  "col_plc": "PLC",
  "col_status": "Durum",
  "col_last_success": "Son Başarılı Okuma",
  "col_fail": "Ardışık Hata",
  "col_reconnects": "Reconnect/dk",
  "alerts": "{{count}} sorun",
  "open_problems": "{{count}} açık sorun",
  "all_healthy_short": "Sağlıklı"
}
```

English values:

```json
{
  "title": "PLC Health",
  "subtitle": "PLC connection and data health monitoring",
  "nav": "PLC Health",
  "open_incidents": "Open Incidents",
  "all_healthy": "All PLCs healthy",
  "per_plc": "Per-PLC Status",
  "history": "History",
  "critical": "Critical",
  "warning": "Warning",
  "ack": "Acknowledge",
  "resolved": "resolved",
  "connected": "Connected",
  "disconnected": "Disconnected",
  "col_plc": "PLC",
  "col_status": "Status",
  "col_last_success": "Last Successful Read",
  "col_fail": "Consecutive Failures",
  "col_reconnects": "Reconnects/min",
  "alerts": "{{count}} issues",
  "open_problems": "{{count}} open issues",
  "all_healthy_short": "Healthy"
}
```

For ru, de, ar: translate the same keys (use the existing translations in other namespaces as the tone/quality reference; keep `{{count}}` placeholders intact). If the project loads namespaces from a central registry, register `plcHealth` there following the existing pattern (copy how `plc` namespace is registered).

- [ ] **Step 4: Verify frontend builds + tests pass**

Run: `cd scada-reporter/frontend && pnpm tsc --noEmit && pnpm test`
Expected: no TS errors, all tests pass.

- [ ] **Step 5: Regenerate the OpenAPI client (optional consistency)**

With the backend running (`just run-backend`), run `just gen-client` to refresh the generated client under `src/api/`. (The hand-written `client.ts` additions in Task 10 are the source of truth for these endpoints; this step only keeps the generated artifacts in sync.) Skip if the generated client is not consumed by the new code.

- [ ] **Step 6: Manual smoke test**

Start backend + frontend (`just dev`). Log in, navigate to `/plc-health`. With PLCs simulated/offline, confirm: page loads, per-PLC table populates after a monitor cycle (~10s), and (if a PLC is down) an incident card + the top-bar badge appear. Acknowledge an incident as admin and confirm the ack button disappears.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/frontend/src/App.tsx scada-reporter/frontend/src/components/Layout.tsx scada-reporter/frontend/src/i18n scada-reporter/frontend/src/locales
git commit -m "feat(plc-health): route, nav, alert badge wiring + i18n (5 langs)"
```

---

## Final verification

- [ ] Run full backend suite: `cd scada-reporter/backend && .venv/Scripts/pytest tests/ -q` — all green.
- [ ] Run `just backend-check` (lint + format + typecheck + test) — clean.
- [ ] Run `just frontend-check` (tsc + lint + test) — clean.
- [ ] Apply migration on a fresh prod-like DB: `just migrate` — succeeds.
- [ ] Manual: trigger a disconnect (stop a PLC / point to bad IP), confirm incident opens within ~2 monitor cycles, badge shows, and resolves after recovery.
