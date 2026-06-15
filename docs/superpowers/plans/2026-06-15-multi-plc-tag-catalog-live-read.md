# Plan: Multi-PLC Tag Catalog + Live PLC Read

**Date:** 2026-06-15
**Status:** Proposed
**Scope:** backend (collector, poller, model, migration, API, seed) + frontend (Tags page)

---

## 1. Context

SCADA Reporter currently connects to a **single PLC** (`settings.S7_HOST`) and uses each
tag's `node_id` field directly as its S7 address. The real plant has **30 separate PLCs**
(each on its own IP) and thousands of tags. These tags are described in three WinCC Excel
exports placed in `xlsx/`:

- **`full_export.xlsx`** — **all tags (30,620)**. The `Tags` sheet has `Name`, `Data type`,
  `Connection` (PLC name: PLC1, PLC4, CAMUR_DRYER1…), and `Address` (WinCC operand syntax,
  e.g. `DB301,DD7890`). The `Connections` sheet maps PLC name → IP (extracted from the
  connection params via the regex `S7ONLINE!::<IP>:`).
- **`archive_export.xlsx`** — **only the long-term archived tags (3,206)**. The `Tags` sheet has
  `Tag name`, `Acquisition cycle` / `Archiving cycle` (the recording interval, e.g. `5 second`),
  and `Relevant long term` = 1. **It has no absolute addresses** — each `Tag name` must be
  joined to the `Name` column in `full_export.xlsx` to obtain the PLC IP and S7 address.
- **`gunluk_rapor.xlsx`** — a human-formatted monthly report; daily-tracked device codes scattered
  across 60+ sheets.

**Goal:** import the real catalog (PLC IP + absolute address + recording interval); when a new
tag is added, read its value immediately from the correct PLC and show it to the user; and have
the poller read every tag from its own PLC at its own interval.

### 1.1 Why this change

Today's model conflates "tag name" with "S7 address" and assumes one PLC. That cannot represent
the plant. Without per-tag PLC IP + parsed WinCC address + per-tag interval, the system can neither
poll the real PLCs nor satisfy the core requirement: *adding a tag should read its live value*.

---

## 2. Data analysis (verified against the xlsx files)

All findings below were confirmed by parsing the actual files with `openpyxl`.

### 2.1 Connection → IP

All 30 connections resolved cleanly. Examples:

| Connection | IP | Connection | IP |
|---|---|---|---|
| PLC1 | 192.168.112.50 | PLC4 | 192.168.115.2 |
| PLC2 | 192.168.113.20 | CAMUR_DRYER1 | 192.168.115.56 |
| PLC3 | 192.168.114.20 | ENERJI_PLC1 | 192.168.112.119 |

(Full list in `full_export.xlsx` → `Connections` sheet, parsed from the `Connection Parameters` column.)

### 2.2 archive → full join

- 3,206 archive tags; **3,027 found** in `full_export.Name` → address + IP + data type resolved.
- **179–181 not found** — these are SiproTec relays / UMG energy meters (e.g. `Pompa1_SiproTec.S`,
  `Tr2_UMG.V-N-L3`). They are **not** in the S7 export at all → **cannot be read via S7** (different
  protocol). The importer **skips them and reports the count**.

### 2.3 Address operand → read mapping

Address size/area come from the WinCC operand; the **decode type comes from the `Data type` column**:

| Operand | Meaning | Bytes | Data type → decoder |
|---|---|---|---|
| `DB<n>,DD<off>` | DB double word | 4 | float32 / **float64** → `REAL` (`get_real`) |
| `DB<n>,DBW<off>` | DB word | 2 | uint16 → `WORD` (`get_word`) |
| `Q<byte>.<bit>` | output process-image bit | 1 | Binary → `BOOL` (bit) |

**Important:** float64-labeled tags still sit on **4-byte `DD`** addresses and are read as 4-byte
`REAL`. The 64-bit label is the OS-side value range, not the PLC read width.

Archive-tag distribution: float32 × 2,444 (DD), float64 × 667 (DD), uint16 × 172 (DBW), Binary × 8 (Q bit).

### 2.4 gunluk_rapor (daily report) — fuzzy

The tokens in the daily report (`crtCT01DB02`, `gtuTP01DBB01`, …) **do not match** `full_export.Name`
exactly (0/59 sampled). They are **device codes** appearing as substrings: `crtCT01DB02` →
`B110crtCT01DB02.ALARM_WORD`, `B110crtCT01DB02.BASINC_DEGERI`, etc. — i.e. **one token maps to many
tags**, and some tokens (`gtuTP01DBB01`, `crtT01DB03`) don't match at all. Therefore daily-tracking
resolution is **best-effort** (see §3.6); precise per-day value extraction is **out of scope** here.

---

## 3. Implementation

### 3.1 Tag model + migration

Add the following **nullable / server_default** columns to `Tag` in `app/models/tag.py` (additive
columns are safe via `op.add_column` on both SQLite-dev and Postgres-prod):

| Column | Type | Notes |
|---|---|---|
| `plc_name` | `String(255)` default `""` | connection name (e.g. `CAMUR_DRYER1`); also mirrored into `device` for UI compat |
| `plc_ip` | `String(45)` nullable, **indexed** | PLC IPv4; poller groups by this |
| `plc_rack` | `Integer` server_default `"0"` | |
| `plc_slot` | `Integer` server_default `"1"` | |
| `s7_address` | `String(128)` nullable | WinCC operand string (`DB301,DD7890`, `Q254.1`) — parser input |
| `data_type` | `String(32)` default `""` | WinCC data type (`float32`/`uint16`/`Binary`) — selects decoder |
| `sample_interval` | `Integer` server_default `"5"` | seconds, parsed from `"5 second"` |
| `long_term` | `Boolean` server_default `false` | archive flag |
| `daily_tracking` | `Boolean` server_default `false` | gunluk_rapor flag (best-effort) |

- **Keep `node_id`** as the unique business key (used by import dedup and `tag_map`); it stops being
  the parser input. On import set `node_id = <WinCC tag Name>` (already unique).
- New Alembic revision with `down_revision = "decf6c1fe08b"` (current head — verified:
  `97421fc62374 → f7b7e5a26253 → decf6c1fe08b`).
  - `upgrade()`: plain `op.add_column(...)` calls + `op.create_index("ix_tags_plc_ip", "tags", ["plc_ip"])`.
  - `downgrade()`: wrap drops in `with op.batch_alter_table("tags") as b:` for older SQLite.
  - Pattern reference: `alembic/versions/f7b7e5a26253_alarm_thresholds_and_report_history.py`.

### 3.2 Address parser (`app/collector/s7_collector.py`)

Replace `_parse_address` with a pure function returning a fully resolved spec:

```python
@dataclass(frozen=True)
class ReadSpec:
    area: str          # "DB" | "PA" (Q outputs) | "PE" (I inputs)
    db_number: int     # 0 for non-DB
    byte_offset: int
    bit: int           # 0 if not a bit access
    size: int          # bytes to read
    decoder: str       # "REAL" | "WORD" | "INT" | "DINT" | "BOOL"

def parse_address(address: str, data_type: str | None = None) -> ReadSpec: ...
```

- **DB family** regex `^DB(\d+),([A-Z]+)(\d+)(?:\.(\d+))?$`; operand→size:
  `DD/DBD=4, DW/DBW=2, DBB=1, DBX=1`, plus legacy `REAL=4, INT=2, DINT=4, WORD=2, BOOL=1` (back-compat).
- **Non-DB family** regex `^([QIE])(\d+)\.(\d+)$` → `Q`→`Areas.PA`, `I`/`E`→`Areas.PE`, decode `BOOL`.
- **Decoder** from `data_type`: `float32/float64/REAL → REAL(4)`, `uint16/WORD → WORD(2)`,
  `int16 → INT(2)`, `int32 → DINT(4)`, `Binary/BOOL → BOOL(1)`. Fall back to operand if `data_type` missing.
- Unknown form → `ValueError`. Callers (poller / create-tag) catch it, log once, and emit quality=0 —
  the loop **never crashes**.
- `_read_sync`: DB → `client.db_read(db, off, size)`; non-DB → `client.read_area(area, 0, off, size)`;
  decode via `snap7.util` keyed by `decoder`.

### 3.3 Multi-PLC connection management (`app/collector/s7_collector.py`)

Replace the single global `collector` with a `PLCManager` registry. One snap7 client per
`(ip, rack, slot)`, each guarded by its own `threading.Lock` (snap7 clients are **not** thread-safe).

```python
class PLCConnection:
    def __init__(self, ip, rack=0, slot=1, name=""): ...
    def _ensure_connected_sync(self) -> bool: ...     # lazy connect + reconnect backoff (~10s)
    def read_batch_sync(self, specs) -> list[tuple]:  # (value, quality) per spec
        # acquire self._lock; ensure connected; read each; on snap7 error → mark
        # disconnected and return quality=0 for remaining items
    def disconnect_sync(self): ...

class PLCManager:
    def get(self, ip, rack=0, slot=1, name="") -> PLCConnection: ...   # lazy create, registry lock
    async def read_one(self, ip, rack, slot, spec) -> tuple: ...        # run_in_executor
    async def read_plc_batch(self, ip, rack, slot, specs) -> list: ...  # run_in_executor
    def status(self) -> dict: ...                                       # {ip: connected_bool}
    async def disconnect_all(self): ...

plc_manager = PLCManager()
```

- **Lazy connect**: nothing opens at startup; first read for a PLC connects.
- **Simulation mode preserved**: unreachable PLC → `(None, 0)`; the app keeps running.
- Resize executor: `ThreadPoolExecutor(max_workers=min(16, n_plcs + 4))` (config `S7_MAX_WORKERS`).
  Concurrency exists **across** PLCs (different clients); reads are serialized **within** a PLC by its lock.
- `app/main.py` lifespan: drop the global connect (lazy now), call `disconnect_all()` on shutdown,
  and change `/health` from `collector.client is not None` to `plc_manager.status()`.

### 3.4 Poller redesign (`app/collector/poller.py`)

Group active tags by `(plc_ip, rack, slot)`, read each PLC's due tags as one batch in the executor,
run PLC batches concurrently with `asyncio.gather`, and honor per-tag intervals via an in-memory
`last_read: dict[tag_id, float]` (monotonic).

```
last_read = {}
while True:
    tick_start = monotonic()
    tags = active tags where s7_address and plc_ip are set
    now = monotonic()
    due = [t for t in tags if now - last_read.get(t.id, -inf) >= (t.sample_interval or 5)]

    groups = defaultdict(list)            # (ip,rack,slot) -> [(tag, ReadSpec)]
    for t in due:
        try: spec = parse_address(t.s7_address, t.data_type)
        except ValueError: log once; continue
        groups[(t.plc_ip, t.plc_rack, t.plc_slot)].append((t, spec))

    async def read_group(key, items):
        results = await plc_manager.read_plc_batch(*key, [s for _, s in items])  # offline → (None,0)
        for (tag, _), _ in zip(items, results): last_read[tag.id] = now
        return [(tag.id, value, quality) for (tag, _), (value, quality) in zip(items, results)]

    batches = await gather(*[read_group(k, v) for k, v in groups.items()])
    write TagReading(tag_id, value, quality, ts) for all rows   # single ts per tick; PK safe
    sleep(max(0, TICK - (monotonic() - tick_start)))            # TICK = min(sample_interval), >=1s
```

- `last_read` is updated even for offline PLCs to avoid hammering an unreachable PLC every tick.
- Storing quality=0 rows on failure keeps gap visibility (matches current behavior).
- In-memory `last_read` is lost on restart → all tags due at once on the first tick (bounded by
  `max_workers`; acceptable).

### 3.5 Read-on-add (`app/api/tags.py` `POST /tags/`)

- `TagCreate` gains: `plc_name, plc_ip, plc_rack=0, plc_slot=1, s7_address, data_type,
  sample_interval=5, long_term=False`. If `node_id` is omitted, derive `f"{plc_name}:{s7_address}"`.
- `TagResponse` gains: `current_value: float | None`, `quality: int`, `read_at: datetime | None`.
- After persisting the tag: `parse_address` → `plc_manager.read_one(...)` wrapped in
  `asyncio.wait_for(timeout=settings.S7_READ_TIMEOUT)` (default 3s). The blocking snap7 call runs in
  the executor, so the event loop is never blocked. If quality=192, also write a `TagReading`.
- Offline PLC / timeout / parse error → tag is still created with `current_value=null`, `quality=0`;
  the poller picks it up later when the PLC recovers.
- Add `S7_READ_TIMEOUT=3` and `S7_MAX_WORKERS` to `config.py`.

### 3.6 Server-side seed/import (`app/seed_tags.py` or new `app/import_catalog.py`, + `api/tags.py`)

A server-side importer (exposed via a `just seed-catalog` recipe) that reads from the `xlsx/` folder:

1. **`full_export.xlsx`**:
   - `Connections` → `{plc_name: ip}` (regex `S7ONLINE!::([\d.]+):`).
   - `Tags` → `{Name: (connection, address, data_type)}`.
2. **`archive_export.xlsx`** `Tags` → for each row: `Tag name`, `Acquisition cycle` → seconds, `long_term`.
3. **Join** archive `Tag name` → full map. Resolved → create
   `Tag(node_id=Name, plc_name=conn, plc_ip=ip_map[conn], s7_address=address, data_type,
   sample_interval, long_term=True, device=plc_name)`. Unresolved (the ~181 SiproTec/UMG) → skip and
   report the count.
4. **gunluk_rapor (best-effort)**: collect tag-like tokens across all sheets; for each token find
   `full_export` tags whose `Name` starts with `B110<token>`, mark the matches `daily_tracking=True`.
   Tokens that don't match (`gtuTP01DBB01`, …) are **reported, not forced** — left for manual mapping.
   Interval parse: `re.match(r"(\d+)\s*(second|minute|hour)")` → seconds.
5. Provide a `--reset` option to clear the legacy 27 seed tags (old `node_id`=address format) before reseeding.
6. **Fix `/import` endpoint**: replace the single-sheet "Connections-as-tags" logic with the same
   multi-sheet join (the UI still uploads one file, but the backend processes the correct sheets).

### 3.7 Frontend (`frontend/src/pages/Tags.tsx`, `src/api/client.ts`, `justfile`)

- `AddTagModal`: fields `plc_name, plc_ip, s7_address, data_type` (select: float32/uint16/Binary),
  `sample_interval`, `unit`, `name`. After creation, show the returned `current_value` / `quality`
  ("Live value: 12.3 m³/h · quality: Good / —").
- Tag table: add `PLC IP`, `Address`, `Interval`, `Type` columns; `long_term` / `daily_tracking` badges.
- `FormatGuideModal`: add WinCC operand examples (`DB301,DD7890`, `DB310,DBW90`, `Q254.1`).
- Run `just gen-client` (backend running) to regenerate the TS client.

---

## 4. Critical files

- `scada-reporter/backend/app/models/tag.py` — new columns
- `scada-reporter/backend/alembic/versions/<new>_multi_plc_catalog.py` — migration (down=`decf6c1fe08b`)
- `scada-reporter/backend/app/collector/s7_collector.py` — `parse_address` + `PLCManager`
- `scada-reporter/backend/app/collector/poller.py` — grouped, interval-aware polling
- `scada-reporter/backend/app/api/tags.py` — read-on-add + import fix
- `scada-reporter/backend/app/core/config.py` — `S7_READ_TIMEOUT`, `S7_MAX_WORKERS`
- `scada-reporter/backend/app/main.py` — lazy connect lifespan + `/health`
- `scada-reporter/backend/app/seed_tags.py` (or new `import_catalog.py`) — catalog seed
- `scada-reporter/frontend/src/pages/Tags.tsx`, `src/api/client.ts`, `justfile`

---

## 5. Verification

1. **Unit (pytest)** — `parse_address`: `DB301,DD7890`+float32 → REAL/4B/DB; `DB310,DBW90`+uint16 →
   WORD/2B; `Q254.1`+Binary → BOOL/PA bit; unknown → `ValueError`. Interval parse (`"5 second"` → 5).
   `PLCManager.get` returns one instance per `(ip,rack,slot)`. Run via `just test`.
2. **Migration** — `just migrate` (SQLite dev), then `just migrate-down` / up round-trip; confirm columns exist.
3. **Seed** — `just seed-catalog` → ~3,027 tags created, ~181 skipped (reported); verify `plc_ip` /
   `s7_address` / `sample_interval` populated. Cross-check with `just agent cli_args="explore tags"`.
4. **Read-on-add** — with backend running and PLC reachable, add a tag in the UI → live value shown;
   with PLC offline, tag is created with "—" quality (app does not crash).
5. **Poller** — `just run-backend`; logs show per-PLC reads; `GET /tags/{id}/readings` shows the value
   stream; confirm tags with different `sample_interval` are written at different cadences.
6. **Lint/type** — `just check` (ruff + mypy green).

---

## 6. Risks / open items

- **PLC reachability**: if the dev host cannot reach the 192.168.x PLC subnets, read-on-add and the
  poller stay in simulation mode (null values). Code is correct; this is environment-dependent.
- **gunluk_rapor**: token→tag mapping is fuzzy (device code → many tags; some tokens unmatched).
  Best-effort `daily_tracking` flag + an unmatched-token report; precise daily-value extraction is a
  **separate task**.
- **Legacy 27 seed tags** use the old `node_id`=address format. Re-seeding with the new schema is
  cleaner — use the seed `--reset` option to clear them first.
- **`create_all` vs Alembic**: startup `create_all` does **not** alter an existing prod DB — prod must
  run `alembic upgrade head` to get the new columns.
