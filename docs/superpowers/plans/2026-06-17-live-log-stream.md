# Live Backend Log Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live console panel to the Metrics page that streams backend log messages (app + poller + PLC connection) in real time via SSE.

**Architecture:** A custom `logging.Handler` pushes every Python log record into an in-memory ring buffer (deque, maxlen 500) with a monotonic sequence id. A new SSE endpoint tails the buffer and pushes new records as JSON-array frames. A React hook consumes the EventSource; the Metrics page renders the lines in a color-coded auto-scrolling console.

**Tech Stack:** Python `logging` + `collections.deque` + FastAPI `StreamingResponse` (SSE); React 19 + `EventSource` + TanStack/i18next; pytest-asyncio + vitest.

## Global Constraints

- Backend Python 3.14, FastAPI; tests are `pytest` async (`@pytest.mark.asyncio`).
- No new dependencies, no DB models, no migrations.
- Do NOT edit `app/collector/poller.py` or `app/collector/s7_collector.py` — they already log via `logging`.
- SSE auth uses query-param token via existing `authenticate_token(token, db)` (EventSource cannot send headers).
- Lint/type gates run on commit (ruff + mypy); keep type hints complete.
- Frontend i18n: every key added to `en/metrics.json` MUST also exist in `tr`, `ru`, `de` metrics.json (parity test `src/i18n/parity.test.ts` enforces it). `{{placeholder}}` tokens must match across locales.
- SSE frame format: `data: <json>\n\n`. The logs endpoint payload is a JSON **array** of record objects (distinct from the existing `/stream` object payload).
- Record wire shape: `{ "seq": int, "ts": ISO8601 str, "level": str, "levelno": int, "name": str, "msg": str }`.

---

### Task 1: Ring log buffer + handler (backend core)

**Files:**
- Create: `scada-reporter/backend/app/core/log_buffer.py`
- Test: `scada-reporter/backend/tests/test_log_buffer.py`

**Interfaces:**
- Consumes: nothing (leaf module; stdlib only).
- Produces:
  - `class RingLogHandler(logging.Handler)` with `__init__(self, maxlen: int = 500)`.
  - `RingLogHandler.snapshot(self, after_seq: int = 0, min_level: int = logging.INFO) -> list[dict]` returning records with `seq > after_seq` and `levelno >= min_level`, oldest-first.
  - Module singleton `log_buffer: RingLogHandler` (maxlen 500).

- [ ] **Step 1: Write the failing test**

```python
# scada-reporter/backend/tests/test_log_buffer.py
"""In-memory ring log buffer + handler."""

import logging

from app.core.log_buffer import RingLogHandler


def _rec(handler: RingLogHandler, level: int, msg: str, name: str = "test") -> None:
    handler.emit(logging.LogRecord(name, level, __file__, 1, msg, None, None))


def test_emit_captures_record_fields():
    h = RingLogHandler(maxlen=10)
    _rec(h, logging.INFO, "hello world", name="app.poller")
    snap = h.snapshot()
    assert len(snap) == 1
    r = snap[0]
    assert r["seq"] == 1
    assert r["level"] == "INFO"
    assert r["levelno"] == logging.INFO
    assert r["name"] == "app.poller"
    assert r["msg"] == "hello world"
    assert "T" in r["ts"]  # ISO timestamp


def test_seq_is_monotonic():
    h = RingLogHandler(maxlen=10)
    for i in range(5):
        _rec(h, logging.INFO, f"m{i}")
    seqs = [r["seq"] for r in h.snapshot()]
    assert seqs == [1, 2, 3, 4, 5]


def test_ring_caps_at_maxlen_and_drops_oldest():
    h = RingLogHandler(maxlen=3)
    for i in range(5):
        _rec(h, logging.INFO, f"m{i}")
    snap = h.snapshot()
    assert len(snap) == 3
    assert [r["msg"] for r in snap] == ["m2", "m3", "m4"]
    assert [r["seq"] for r in snap] == [3, 4, 5]


def test_snapshot_after_seq_filters_seen():
    h = RingLogHandler(maxlen=10)
    for i in range(4):
        _rec(h, logging.INFO, f"m{i}")
    snap = h.snapshot(after_seq=2)
    assert [r["seq"] for r in snap] == [3, 4]


def test_snapshot_min_level_filters_lower():
    h = RingLogHandler(maxlen=10)
    _rec(h, logging.INFO, "info-line")
    _rec(h, logging.WARNING, "warn-line")
    _rec(h, logging.ERROR, "err-line")
    msgs = [r["msg"] for r in h.snapshot(min_level=logging.WARNING)]
    assert msgs == ["warn-line", "err-line"]


def test_emit_never_raises_on_bad_record():
    h = RingLogHandler(maxlen=10)
    bad = logging.LogRecord("x", logging.INFO, __file__, 1, "%d", ("not-int",), None)
    h.emit(bad)  # must not raise
    assert len(h.snapshot()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv\Scripts\python -m pytest tests/test_log_buffer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.log_buffer'`

- [ ] **Step 3: Write minimal implementation**

```python
# scada-reporter/backend/app/core/log_buffer.py
"""Bellek içi halka tampon log handler'ı — canlı log akışı için.

Her log kaydını sınırlı bir deque'e (varsayılan 500) monoton bir ``seq``
ile yazar. Metrics sayfasındaki canlı konsol bu tamponu SSE ile tail eder.
Poller ve s7_collector zaten ``logging`` üzerinden yazdığından ek kod
gerektirmez; handler root logger'a bağlanır (main.py).
"""

import logging
import threading
from collections import deque
from datetime import UTC, datetime


class RingLogHandler(logging.Handler):
    """Log kayıtlarını sınırlı bir halka tampona yazan thread-safe handler."""

    def __init__(self, maxlen: int = 500) -> None:
        super().__init__()
        self._buf: deque[dict] = deque(maxlen=maxlen)
        self._seq = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
            with self._lock:
                self._seq += 1
                self._buf.append(
                    {
                        "seq": self._seq,
                        "ts": ts,
                        "level": record.levelname,
                        "levelno": record.levelno,
                        "name": record.name,
                        "msg": msg,
                    }
                )
        except Exception:  # logging handler sözleşmesi: asla yükseltme
            self.handleError(record)

    def snapshot(self, after_seq: int = 0, min_level: int = logging.INFO) -> list[dict]:
        with self._lock:
            items = list(self._buf)
        return [r for r in items if r["seq"] > after_seq and r["levelno"] >= min_level]


log_buffer = RingLogHandler(maxlen=500)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv\Scripts\python -m pytest tests/test_log_buffer.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/core/log_buffer.py scada-reporter/backend/tests/test_log_buffer.py
git commit -m "feat(metrics): in-memory ring log buffer handler"
```

---

### Task 2: Wire handler + SSE logs endpoint (backend API)

**Files:**
- Modify: `scada-reporter/backend/app/main.py` (after `logging.basicConfig` at line 44)
- Modify: `scada-reporter/backend/app/api/realtime.py` (add generator + endpoint)
- Test: `scada-reporter/backend/tests/test_realtime.py` (append cases)

**Interfaces:**
- Consumes: `from app.core.log_buffer import log_buffer`, `log_buffer.snapshot(after_seq, min_level)` from Task 1; `authenticate_token` and `settings` already imported in `realtime.py`.
- Produces:
  - `async def log_event_stream(after: int = 0, min_level: int = logging.INFO, interval: float = 1.0, *, max_events: int | None = None) -> AsyncGenerator[str, None]` in `realtime.py` — yields `data: <json-array>\n\n` frames of new records.
  - Endpoint `GET /api/dashboard/logs/stream?token=&after=&level=&limit=`.

- [ ] **Step 1: Write the failing test (append to test_realtime.py)**

```python
# append to scada-reporter/backend/tests/test_realtime.py
import logging

from app.api.realtime import log_event_stream
from app.core.log_buffer import log_buffer


def _parse_list(frame: str) -> list:
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    return json.loads(frame[len("data: ") :].strip())


@pytest.mark.asyncio
async def test_log_stream_yields_buffered_lines():
    log_buffer.emit(
        logging.LogRecord("app.poller", logging.INFO, __file__, 1, "tick ok", None, None)
    )
    frames = [f async for f in log_event_stream(interval=0.01, max_events=1)]
    assert len(frames) == 1
    rows = _parse_list(frames[0])
    assert any(r["msg"] == "tick ok" and r["level"] == "INFO" for r in rows)


@pytest.mark.asyncio
async def test_log_stream_min_level_excludes_info():
    log_buffer.emit(
        logging.LogRecord("x", logging.INFO, __file__, 1, "noise-info", None, None)
    )
    log_buffer.emit(
        logging.LogRecord("x", logging.WARNING, __file__, 1, "real-warn", None, None)
    )
    frames = [
        f
        async for f in log_event_stream(min_level=logging.WARNING, interval=0.01, max_events=1)
    ]
    rows = _parse_list(frames[0])
    msgs = [r["msg"] for r in rows]
    assert "real-warn" in msgs
    assert "noise-info" not in msgs


@pytest.mark.asyncio
async def test_logs_stream_endpoint_requires_valid_token(client: AsyncClient):
    r = await client.get("/api/dashboard/logs/stream", params={"token": "garbage", "limit": 1})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logs_stream_endpoint_serves_event_stream(client: AsyncClient, db_session):
    log_buffer.emit(
        logging.LogRecord("app", logging.INFO, __file__, 1, "endpoint-line", None, None)
    )
    token = await _token(client, db_session)
    r = await client.get(
        "/api/dashboard/logs/stream", params={"token": token, "limit": 1}
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    rows = _parse_list(r.text)
    assert any(x["msg"] == "endpoint-line" for x in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv\Scripts\python -m pytest tests/test_realtime.py -v -k log`
Expected: FAIL — `ImportError: cannot import name 'log_event_stream'`

- [ ] **Step 3a: Implement generator + endpoint in realtime.py**

Add imports at top of `realtime.py` (alongside existing imports):

```python
import logging
```

Add `log_buffer` import next to the existing `from app.collector.cache import ...` line:

```python
from app.core.log_buffer import log_buffer
```

Append to `realtime.py` (after the existing `stream` endpoint):

```python
async def log_event_stream(
    after: int = 0,
    min_level: int = logging.INFO,
    interval: float = 1.0,
    *,
    max_events: int | None = None,
) -> AsyncGenerator[str, None]:
    """Halka tampondaki yeni log kayıtlarını SSE frame'i (JSON dizisi) olarak akıt."""
    last = after
    sent = 0
    while max_events is None or sent < max_events:
        recs = log_buffer.snapshot(after_seq=last, min_level=min_level)
        if recs:
            last = recs[-1]["seq"]
            yield f"data: {json.dumps(recs)}\n\n"
            sent += 1
            if max_events is not None and sent >= max_events:
                break
        await asyncio.sleep(interval)


@router.get("/logs/stream")
async def logs_stream(
    token: str = Query(...),
    after: int = Query(default=0, ge=0),
    level: str = Query(default="INFO"),
    limit: int | None = Query(default=None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    await authenticate_token(token, db)
    min_level = logging.getLevelName(level.upper())
    if not isinstance(min_level, int):
        min_level = logging.INFO
    return StreamingResponse(
        log_event_stream(after, min_level, max_events=limit),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

> Note: in `log_event_stream`, when `max_events` is set and the buffer is empty, the loop sleeps `interval`. Tests seed the buffer first and use `max_events=1`, so the first snapshot is non-empty and the generator returns promptly.

- [ ] **Step 3b: Attach handler to root logger in main.py**

After line 44 (`logging.basicConfig(...)`) and its `logger = logging.getLogger(__name__)`, add:

```python
from app.core.log_buffer import log_buffer

log_buffer.setLevel(logging.INFO)
logging.getLogger().addHandler(log_buffer)
```

(Place the import with the other `from app.core...` imports near the top; place the two attach lines right after `logger = logging.getLogger(__name__)`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scada-reporter/backend && .venv\Scripts\python -m pytest tests/test_realtime.py -v`
Expected: PASS (existing + 4 new)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/main.py scada-reporter/backend/app/api/realtime.py scada-reporter/backend/tests/test_realtime.py
git commit -m "feat(metrics): SSE /dashboard/logs/stream endpoint + root handler wiring"
```

---

### Task 3: `useLogStream` hook (frontend)

**Files:**
- Create: `scada-reporter/frontend/src/hooks/useLogStream.ts`
- Test: `scada-reporter/frontend/src/hooks/useLogStream.test.ts`

**Interfaces:**
- Consumes: backend `GET /api/dashboard/logs/stream?token=&level=` from Task 2; payload is a JSON array of `{ seq, ts, level, levelno, name, msg }`.
- Produces:
  - `export interface LogLine { seq: number; ts: string; level: string; levelno: number; name: string; msg: string }`
  - `export function useLogStream(level: string, enabled?: boolean, cap?: number): { lines: LogLine[]; clear: () => void }` (defaults `enabled = true`, `cap = 500`).

- [ ] **Step 1: Write the failing test**

```ts
// scada-reporter/frontend/src/hooks/useLogStream.test.ts
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useLogStream } from './useLogStream'

class FakeEventSource {
  static last: FakeEventSource | null = null
  url: string
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: ((e: unknown) => void) | null = null
  closed = false
  constructor(url: string) {
    this.url = url
    FakeEventSource.last = this
  }
  close() {
    this.closed = true
  }
  push(rows: unknown) {
    this.onmessage?.({ data: JSON.stringify(rows) })
  }
}

beforeEach(() => {
  vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource)
  localStorage.setItem('token', 'tok')
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  FakeEventSource.last = null
})

const line = (seq: number, msg: string) => ({
  seq,
  ts: '2026-06-17T00:00:00Z',
  level: 'INFO',
  levelno: 20,
  name: 'app',
  msg,
})

describe('useLogStream', () => {
  it('appends parsed frames in order', () => {
    const { result } = renderHook(() => useLogStream('INFO'))
    act(() => FakeEventSource.last!.push([line(1, 'a'), line(2, 'b')]))
    expect(result.current.lines.map((l) => l.msg)).toEqual(['a', 'b'])
  })

  it('caps the buffer at cap, dropping oldest', () => {
    const { result } = renderHook(() => useLogStream('INFO', true, 2))
    act(() => FakeEventSource.last!.push([line(1, 'a'), line(2, 'b'), line(3, 'c')]))
    expect(result.current.lines.map((l) => l.msg)).toEqual(['b', 'c'])
  })

  it('clear() empties the buffer', () => {
    const { result } = renderHook(() => useLogStream('INFO'))
    act(() => FakeEventSource.last!.push([line(1, 'a')]))
    act(() => result.current.clear())
    expect(result.current.lines).toEqual([])
  })

  it('skips malformed frames without throwing', () => {
    const { result } = renderHook(() => useLogStream('INFO'))
    act(() => FakeEventSource.last!.onmessage?.({ data: 'not-json' }))
    expect(result.current.lines).toEqual([])
  })

  it('passes the level into the EventSource URL', () => {
    renderHook(() => useLogStream('WARNING'))
    expect(FakeEventSource.last!.url).toContain('level=WARNING')
    expect(FakeEventSource.last!.url).toContain('token=tok')
  })

  it('does not open a stream when disabled', () => {
    FakeEventSource.last = null
    renderHook(() => useLogStream('INFO', false))
    expect(FakeEventSource.last).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm vitest run src/hooks/useLogStream.test.ts`
Expected: FAIL — cannot resolve `./useLogStream`

- [ ] **Step 3: Write minimal implementation**

```ts
// scada-reporter/frontend/src/hooks/useLogStream.ts
import { useCallback, useEffect, useState } from 'react'

export interface LogLine {
  seq: number
  ts: string
  level: string
  levelno: number
  name: string
  msg: string
}

/**
 * SSE ile canlı backend log akışı. Backend /api/dashboard/logs/stream halka
 * tampondan yeni kayıtları JSON dizisi olarak push eder. EventSource başlık
 * gönderemediği için token query-param ile iletilir. `level` değiştiğinde
 * akış yeniden açılır ve tampon sıfırlanır.
 */
export function useLogStream(
  level: string,
  enabled = true,
  cap = 500,
): { lines: LogLine[]; clear: () => void } {
  const [lines, setLines] = useState<LogLine[]>([])
  const clear = useCallback(() => setLines([]), [])

  useEffect(() => {
    if (!enabled) return
    const token = localStorage.getItem('token')
    if (!token) return

    setLines([])
    const params = new URLSearchParams()
    params.set('token', token)
    params.set('level', level)
    const es = new EventSource(`/api/dashboard/logs/stream?${params.toString()}`)

    es.onmessage = (e) => {
      try {
        const rows = JSON.parse(e.data) as LogLine[]
        if (!Array.isArray(rows)) return
        setLines((prev) => {
          const next = [...prev, ...rows]
          return next.length > cap ? next.slice(next.length - cap) : next
        })
      } catch {
        /* hatalı frame -> atla */
      }
    }
    // Hata durumunda tarayıcı otomatik yeniden bağlanır.

    return () => es.close()
  }, [level, enabled, cap])

  return { lines, clear }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/frontend && pnpm vitest run src/hooks/useLogStream.test.ts`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/hooks/useLogStream.ts scada-reporter/frontend/src/hooks/useLogStream.test.ts
git commit -m "feat(metrics): useLogStream SSE hook for live backend logs"
```

---

### Task 4: Live Console panel + i18n (frontend page)

**Files:**
- Modify: `scada-reporter/frontend/src/pages/Metrics.tsx` (add panel + component)
- Modify: `scada-reporter/frontend/src/i18n/locales/en/metrics.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/tr/metrics.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/ru/metrics.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/de/metrics.json`
- Test: `scada-reporter/frontend/src/pages/Metrics.console.test.tsx`

**Interfaces:**
- Consumes: `useLogStream(level, enabled, cap)` → `{ lines, clear }` from Task 3; `metrics` i18n namespace.
- Produces: a `LiveConsole` section rendered inside `Metrics`. No new exports consumed elsewhere.

- [ ] **Step 1: Add i18n keys (all four locales)**

Append these keys to `en/metrics.json` (before the closing `}`; add a comma after the current last entry `"empty_plcs"`):

```json
  "console_title": "Live Backend Console",
  "console_sub": "Real-time log stream — poller, PLC connection, app",
  "filter_all": "All (INFO+)",
  "filter_warning": "Warnings+",
  "filter_error": "Errors only",
  "btn_pause": "Pause",
  "btn_resume": "Resume",
  "btn_clear": "Clear",
  "console_empty": "Waiting for backend messages…"
```

Append the SAME keys with translations to `tr/metrics.json`:

```json
  "console_title": "Canlı Backend Konsolu",
  "console_sub": "Gerçek-zamanlı log akışı — poller, PLC bağlantısı, uygulama",
  "filter_all": "Tümü (INFO+)",
  "filter_warning": "Uyarılar+",
  "filter_error": "Sadece hatalar",
  "btn_pause": "Duraklat",
  "btn_resume": "Devam",
  "btn_clear": "Temizle",
  "console_empty": "Backend mesajları bekleniyor…"
```

Append to `ru/metrics.json`:

```json
  "console_title": "Живая консоль бэкенда",
  "console_sub": "Поток логов в реальном времени — поллер, связь с ПЛК, приложение",
  "filter_all": "Все (INFO+)",
  "filter_warning": "Предупреждения+",
  "filter_error": "Только ошибки",
  "btn_pause": "Пауза",
  "btn_resume": "Продолжить",
  "btn_clear": "Очистить",
  "console_empty": "Ожидание сообщений бэкенда…"
```

Append to `de/metrics.json`:

```json
  "console_title": "Live-Backend-Konsole",
  "console_sub": "Echtzeit-Log-Stream — Poller, SPS-Verbindung, App",
  "filter_all": "Alle (INFO+)",
  "filter_warning": "Warnungen+",
  "filter_error": "Nur Fehler",
  "btn_pause": "Pause",
  "btn_resume": "Fortsetzen",
  "btn_clear": "Leeren",
  "console_empty": "Warte auf Backend-Nachrichten…"
```

> Remember to add a comma after the previous last key (`"empty_plcs": "..."`) in each file.

- [ ] **Step 2: Write the failing test**

```tsx
// scada-reporter/frontend/src/pages/Metrics.console.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

// Mock the hook so the panel renders deterministically.
vi.mock('../hooks/useLogStream', () => ({
  useLogStream: () => ({
    lines: [
      { seq: 1, ts: '2026-06-17T10:00:00Z', level: 'INFO', levelno: 20, name: 'app.poller', msg: 'tick ok' },
      { seq: 2, ts: '2026-06-17T10:00:01Z', level: 'ERROR', levelno: 40, name: 'app', msg: 'boom' },
    ],
    clear: vi.fn(),
  }),
}))

// Stub the metrics queries so the page body mounts without a backend.
vi.mock('../api/client', () => ({
  getMetrics: () => Promise.resolve({ data: { rows_written_total: 0, bad_quality_total: 0, bad_ratio: null, tick_count: 0, tick_avg_seconds: null, plcs: [] } }),
  getDeadbandSavings: () => Promise.resolve({ data: null }),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Metrics from './Metrics'

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Metrics />
    </QueryClientProvider>,
  )
}

describe('Metrics live console', () => {
  it('renders streamed log lines', async () => {
    renderPage()
    expect(await screen.findByText('tick ok')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('shows the console title', async () => {
    renderPage()
    expect(await screen.findByText('Live Backend Console')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm vitest run src/pages/Metrics.console.test.tsx`
Expected: FAIL — no element with text "tick ok" / "Live Backend Console"

- [ ] **Step 4: Add the LiveConsole panel to Metrics.tsx**

Add imports at the top of `Metrics.tsx` (after the existing imports):

```tsx
import { useMemo, useRef, useEffect, useState } from 'react'
import { useLogStream } from '../hooks/useLogStream'
import type { LogLine } from '../hooks/useLogStream'
```

Add this component above `export default function Metrics()`:

```tsx
const LEVEL_COLOR: Record<string, string> = {
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-400',
  WARNING: 'text-amber-400',
  INFO: 'text-gray-400',
  DEBUG: 'text-gray-600',
}

function LiveConsole() {
  const { t, i18n } = useTranslation(['metrics', 'common'])
  const [level, setLevel] = useState('INFO')
  const [paused, setPaused] = useState(false)
  const { lines, clear } = useLogStream(level, !paused)
  const bodyRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new lines unless paused.
  useEffect(() => {
    if (!paused && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [lines, paused])

  const fmtTime = (ts: string) => {
    const d = new Date(ts)
    return isNaN(d.getTime()) ? ts : d.toLocaleTimeString(i18n.language)
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-white">{t('console_title')}</h2>
          <p className="text-xs text-gray-500">{t('console_sub')}</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
          >
            <option value="INFO">{t('filter_all')}</option>
            <option value="WARNING">{t('filter_warning')}</option>
            <option value="ERROR">{t('filter_error')}</option>
          </select>
          <button
            onClick={() => setPaused((p) => !p)}
            className="px-2 py-1 text-xs rounded border border-gray-700 text-gray-200 hover:bg-gray-800"
          >
            {paused ? t('btn_resume') : t('btn_pause')}
          </button>
          <button
            onClick={clear}
            className="px-2 py-1 text-xs rounded border border-gray-700 text-gray-200 hover:bg-gray-800"
          >
            {t('btn_clear')}
          </button>
        </div>
      </div>
      <div ref={bodyRef} className="h-72 overflow-y-auto font-mono text-xs p-3 space-y-0.5">
        {lines.length === 0 && (
          <p className="text-gray-600 text-center py-8">{t('console_empty')}</p>
        )}
        {lines.map((l: LogLine) => (
          <div key={l.seq} className="flex gap-2 whitespace-pre-wrap break-all">
            <span className="text-gray-600 shrink-0">{fmtTime(l.ts)}</span>
            <span className={`shrink-0 w-16 ${LEVEL_COLOR[l.level] ?? 'text-gray-400'}`}>{l.level}</span>
            <span className="text-gray-500 shrink-0">{l.name}</span>
            <span className={LEVEL_COLOR[l.level] ?? 'text-gray-300'}>{l.msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

Then render it inside the returned JSX of `Metrics`, immediately AFTER the closing `</div>` of the PLC read-latency table card and BEFORE the closing `</>` fragment (i.e. as the last child of the `{m && ( <> ... </> )}` block). If `useMemo` ends up unused, drop it from the import to satisfy the lint gate:

```tsx
          <LiveConsole />
        </>
      )}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd scada-reporter/frontend && pnpm vitest run src/pages/Metrics.console.test.tsx src/i18n/parity.test.ts`
Expected: PASS (console panel renders lines + i18n parity intact)

- [ ] **Step 6: Type-check and build**

Run: `cd scada-reporter/frontend && pnpm tsc -b && pnpm build`
Expected: no type errors, build succeeds. (If `useMemo` import is unused, remove it.)

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/frontend/src/pages/Metrics.tsx scada-reporter/frontend/src/pages/Metrics.console.test.tsx scada-reporter/frontend/src/i18n/locales/*/metrics.json
git commit -m "feat(metrics): live backend console panel on Metrics page"
```

---

## Self-Review

**Spec coverage:**
- Ring buffer handler (spec §Architecture/Backend 1) → Task 1. ✓
- Root logger wiring (Backend 2) → Task 2 Step 3b. ✓
- SSE `/dashboard/logs/stream` endpoint (Backend 3) → Task 2. ✓
- `useLogStream` hook (Frontend 4) → Task 3. ✓
- Live Console panel: filter, pause/resume, clear, color-by-level, auto-scroll, empty state (Frontend 5) → Task 4. ✓
- i18n keys en/tr/ru/de (Frontend 6) → Task 4 Step 1. ✓
- Tests: `test_log_buffer.py`, extended `test_realtime.py`, `useLogStream` unit, console panel render, parity → Tasks 1–4. ✓
- Error handling: bad token 401 (Task 2 test), malformed frame skip (Task 3 test), non-blocking emit (Task 1 `test_emit_never_raises`). ✓
- Scope boundary: no poller/collector/DB edits — confirmed, no task touches them. ✓

**Placeholder scan:** No TBD/TODO; every code step contains full code. ✓

**Type consistency:** `LogLine`/record shape `{ seq, ts, level, levelno, name, msg }` identical across backend wire payload (Task 1 dict, Task 2 frames), hook interface (Task 3), and page consumer (Task 4). `log_event_stream` / `snapshot` signatures match their consumers. ✓

**Deferred (optional, per spec YAGNI):** reconnect-with-cursor (`after` on reconnect) — hook reopens from `after=0` and the `cap` slice trims; acceptable for a live tail, not implemented.
