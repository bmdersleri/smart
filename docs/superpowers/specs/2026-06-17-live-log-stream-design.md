# Live Backend Log Stream — Design

**Date:** 2026-06-17
**Status:** Approved, ready for implementation plan
**Page:** Metrics (`/metrics` frontend route)

## Goal

Add a live console panel to the Metrics page where backend messages can be
followed in real time. "Backend messages" covers three sources, all of which
already flow through Python `logging`:

- General Python log lines (INFO/WARNING/ERROR) — app-wide.
- Poller events — tick errors, address errors, DB-write/backpressure warnings
  (`app/collector/poller.py`).
- PLC connection status — connect / disconnect / connect-failed
  (`app/collector/s7_collector.py:242,271,294`).

Because all three already emit via `logging`, a single in-memory log handler
captures everything. No edits to poller or collector code are required.

## Decisions

- **Transport:** Server-Sent Events (SSE), matching the existing
  `app/api/realtime.py` + `frontend/src/hooks/useLatestStream.ts` pattern.
  Auth via query-param token (EventSource cannot send headers).
- **Persistence:** In-memory bounded ring buffer, ~500 lines. RAM only, cleared
  on restart. No DB table, no migration.

## Architecture

### Backend

**1. `app/core/log_buffer.py` (new)**

A `logging.Handler` subclass plus a module-level singleton.

```
LogRecordOut = { seq: int, ts: str (ISO), level: str, name: str, msg: str }
```

- `RingLogHandler(logging.Handler)`
  - `__init__(maxlen=500)` — holds a `collections.deque(maxlen=maxlen)` and a
    monotonic `seq` counter (starts at 1).
  - `emit(record)` — format `record` into a `LogRecordOut` dict (use
    `record.getMessage()` for the rendered message; `record.levelname`;
    `record.name`; timestamp from `record.created` → ISO via
    `datetime.fromtimestamp(record.created, tz=UTC)`), assign next `seq`,
    append to deque. Must never raise (wrap in the handler's own
    `handleError` contract) and must do no blocking I/O.
  - Thread safety: poller/collector run via executors/threads, so guard deque
    mutation + seq increment with a `threading.Lock`.
- `snapshot(after_seq: int = 0, min_level: int = logging.INFO) -> list[LogRecordOut]`
  - Returns records with `seq > after_seq` and numeric level `>= min_level`,
    in order. Level comparison uses `logging.getLevelName`-derived numeric
    value stored at emit time (store numeric `levelno` in the record dict as
    an internal field, or re-map levelname → levelno in `snapshot`).
  - Note: store `levelno` in the dict for filtering; it may be omitted from the
    wire payload or kept — keep it, it is small and useful client-side.
- `log_buffer = RingLogHandler()` — module singleton.

**2. `app/main.py` (1 logical change)**

After `logging.basicConfig(...)` (line 44), attach the singleton handler to the
**root** logger so it captures app, poller, s7_collector, and uvicorn records:

```python
from app.core.log_buffer import log_buffer
log_buffer.setLevel(logging.INFO)
logging.getLogger().addHandler(log_buffer)
```

(Keep `basicConfig` — console output stays; the ring handler is additive.)

**3. `app/api/realtime.py` (new endpoint)**

`GET /dashboard/logs/stream?token=&after=&level=`

- Query params:
  - `token: str` (required) — authenticated via existing
    `authenticate_token(token, db)`.
  - `after: int = 0` — only stream records with `seq > after`.
  - `level: str = "INFO"` — one of `INFO|WARNING|ERROR`; mapped to numeric via
    `logging.getLevelName`. Unknown → default INFO.
  - `limit: int | None` — optional max_events bound for tests (mirror existing
    `stream` endpoint's `limit`).
- SSE generator:
  - On connect, compute `last = after`. Loop:
    - `recs = log_buffer.snapshot(after_seq=last, min_level=numeric_level)`
    - If `recs`: emit one SSE frame `data: {json.dumps(recs)}\n\n` and set
      `last = recs[-1]["seq"]`.
    - `await asyncio.sleep(1.0)` between polls.
  - Respect `limit` as a max number of emitted frames (for deterministic tests),
    same shape as the existing `latest_event_stream(max_events=...)`.
- Response: `StreamingResponse(..., media_type="text/event-stream",
  headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})`.

Frame payload is a JSON **array** of `LogRecordOut` (batch of new lines since
`last`), distinct from the existing `/stream` endpoint's object payload.

### Frontend

**4. `src/hooks/useLogStream.ts` (new)**

Mirror `useLatestStream`:

```ts
export interface LogLine { seq: number; ts: string; level: string; name: string; msg: string }
export function useLogStream(level: string, enabled = true, cap = 500): {
  lines: LogLine[]; clear: () => void
}
```

- Opens `EventSource('/api/dashboard/logs/stream?token=&level=')`.
- `onmessage`: parse JSON array, append to state, keep only the last `cap`
  entries (slice). Skip malformed frames (existing pattern).
- Re-subscribes when `level` or `enabled` changes (new EventSource, reset
  lines). Browser auto-reconnect on drop is fine; on reconnect we re-send from
  `after=0` and the client cap dedupes by trimming — acceptable for a live tail.
  (Optional: track max seq seen and pass as `after` on reconnect — list as a
  plan sub-task, not required for MVP.)
- Cleanup closes the EventSource.

**5. `src/pages/Metrics.tsx` (add Live Console panel)**

New section below the existing stat cards / latency table:

- Header: title + level filter `<select>` (All=INFO / WARNING+ / ERROR), a
  pause/resume toggle, and a clear button.
- Body: scrollable monospace list (`max-h`, `overflow-y-auto`), newest at
  bottom, auto-scroll to bottom when not paused and user is at bottom.
- Each line: `HH:MM:SS · LEVEL · logger.name · message`.
  - Color by level: ERROR `text-red-400`, WARNING `text-amber-400`,
    INFO `text-gray-400`. Level badge styled accordingly.
- Pause: stops auto-scroll and freezes append display (keep buffering in hook,
  or disable via `enabled` — plan picks one; simplest is a local "paused" flag
  that stops auto-scroll while the hook keeps the latest `cap` lines).
- Empty state: localized "waiting for messages…".

Styling follows existing Metrics dark cards (`bg-gray-900 border-gray-800
rounded-xl`).

**6. i18n**

Add keys to the `metrics` namespace for en/tr/ru/de:
- `console_title`, `console_sub`
- `filter_all`, `filter_warning`, `filter_error`
- `btn_pause`, `btn_resume`, `btn_clear`
- `console_empty`

Respect existing parity test (`frontend/src/i18n/parity.test.ts`) — all four
locales must define the same keys.

## Error handling

- Bad/expired token → endpoint raises via `authenticate_token` → 401, EventSource
  surfaces `onerror`; browser retries. No special client handling beyond skip.
- Malformed SSE frame → client `try/catch` skip (existing convention).
- Logging path never blocks: `emit` only does in-memory deque append under a
  lock; no I/O, no awaits, cannot back-pressure the poller.
- Ring overflow is intentional: oldest lines drop silently (deque maxlen).

## Testing

**Backend — `tests/test_log_buffer.py` (new)**
- Handler captures emitted records into the ring.
- `seq` is monotonic and strictly increasing.
- Ring caps at `maxlen` (emit > 500, length stays 500, oldest dropped).
- `snapshot(after_seq=N)` returns only `seq > N`.
- `snapshot(min_level=WARNING)` filters out INFO.
- `emit` is exception-safe on a weird record.

**Backend — extend `tests/test_realtime.py`**
- `GET /dashboard/logs/stream` with valid token + `limit` returns SSE frames
  containing buffered log lines (seed the buffer first).
- Invalid token → 401.
- `level=WARNING` excludes INFO lines from frames.
- `after=<seq>` excludes already-seen lines.

**Frontend**
- `useLogStream` unit test (mock EventSource): appends parsed frames, caps at
  `cap`, `clear()` empties, skips malformed frames.
- Metrics page: console panel renders lines, level filter changes subscription,
  pause stops auto-scroll. (Match existing Metrics/i18n test depth.)
- i18n parity test passes with new keys.

## Scope boundary

Touched: `app/core/log_buffer.py` (new), `app/main.py` (attach handler),
`app/api/realtime.py` (new endpoint), `frontend/src/hooks/useLogStream.ts`
(new), `frontend/src/pages/Metrics.tsx` (panel), i18n locale files, tests.

**Not** touched: poller, s7_collector, OPC UA server, DB models, migrations,
Prometheus metrics. No new dependencies.

## Out of scope (YAGNI)

- DB persistence of logs / historical log search.
- Log download/export.
- Per-logger filtering, full-text search box.
- WebSocket transport.
- Reconnect-with-cursor optimization (listed as optional plan sub-task only).
