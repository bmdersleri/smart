"""Tesis değişkeni ifade ağacı değerlendiricisi.

scalar veya series (dict[bucket_key -> value|None]) üretir. Aritmetik SQL-benzeri
null yayar: bir operand None ise sonuç None. series+series bucket anahtarına göre
hizalanır; series+scalar yayınlanır (broadcast). ref bir geri çağrımla çözülür.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.facility_variables.buckets import agg_window, bucket_series, resolve_window

ResolveRef = Callable[[int], Awaitable["EvalResult"]]


@dataclass
class EvalResult:
    kind: str  # scalar | series
    scalar: float | None = None
    series: dict[datetime, float | None] | None = None


def excel_round(value: float, ndigits: int) -> float:
    """Excel ROUND ile aynı: half-away-from-zero (bankers değil)."""
    if value == 0:
        return 0.0
    factor = 10**ndigits
    return math.floor(abs(value) * factor + 0.5) / factor * (1 if value > 0 else -1)


async def evaluate(
    db: AsyncSession,
    node: dict,
    *,
    start: datetime,
    end: datetime,
    grain: str,
    tz_offset_hours: int,
    resolve_ref: ResolveRef,
) -> EvalResult:
    op = node["op"]

    if op == "const":
        return EvalResult(kind="scalar", scalar=float(node["value"]))

    if op == "ref":
        return await resolve_ref(int(node["variable_id"]))

    if op == "agg":
        window = node["window"]
        w_start, w_end = _window_bounds(window, start, end)
        val = await agg_window(
            db, int(node["source"]["tag_id"]), w_start, w_end, node["agg"], tz_offset_hours
        )
        return EvalResult(kind="scalar", scalar=val)

    if op == "series":
        window = node["window"]
        w_start, w_end = _window_bounds(window, start, end)
        data = await bucket_series(
            db,
            int(node["source"]["tag_id"]),
            w_start,
            w_end,
            node["grain"],
            node["agg"],
            tz_offset_hours,
        )
        return EvalResult(kind="series", series=dict(data))

    if op == "abs":
        inner = await _ev(db, node["source"], start, end, grain, tz_offset_hours, resolve_ref)
        return _map_unary(inner, lambda v: abs(v))

    if op == "round":
        ndigits = int(node.get("ndigits", 0))
        inner = await _ev(db, node["source"], start, end, grain, tz_offset_hours, resolve_ref)
        return _map_unary(inner, lambda v: excel_round(v, ndigits))

    if op == "reduce":
        from app.services.template_fill.daily_rollup import reduce_values

        inner = await _ev(db, node["source"], start, end, grain, tz_offset_hours, resolve_ref)
        vals = [v for v in (inner.series or {}).values() if v is not None]
        return EvalResult(kind="scalar", scalar=reduce_values(vals, node["reduce"]))

    if op == "moving_avg":
        inner = await _ev(db, node["source"], start, end, grain, tz_offset_hours, resolve_ref)
        return _moving_avg(inner, int(node["window_size"]))

    if op == "coalesce":
        return await _coalesce(db, node["args"], start, end, grain, tz_offset_hours, resolve_ref)

    if op in ("add", "sub", "mul", "div"):
        return await _arith(db, node, op, start, end, grain, tz_offset_hours, resolve_ref)

    raise ValueError(f"Değerlendirilemeyen op: {op!r}")


async def _ev(db, node, start, end, grain, tz, resolve_ref) -> EvalResult:
    return await evaluate(
        db, node, start=start, end=end, grain=grain, tz_offset_hours=tz, resolve_ref=resolve_ref
    )


def _window_bounds(window: str, start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Excel-ay değerlendirmesinde pencere = verilen [start, end). Göreli sözcükler
    (7d/24h/30d) end'e göre çözülür; 'day'/'2d' gibi tam-pencere sözcükleri verilen
    aralığı kullanır."""
    if window in ("day", "2d", "month") or window.endswith("d") is False:
        return start, end
    try:
        w_start, _ = resolve_window(window, ref_end=end)
        return w_start, end
    except ValueError:
        return start, end


def _map_unary(res: EvalResult, fn) -> EvalResult:
    if res.kind == "scalar":
        return EvalResult(kind="scalar", scalar=None if res.scalar is None else fn(res.scalar))
    out = {k: (None if v is None else fn(v)) for k, v in (res.series or {}).items()}
    return EvalResult(kind="series", series=out)


def _moving_avg(res: EvalResult, size: int) -> EvalResult:
    series = res.series or {}
    keys = sorted(series)
    out: dict[datetime, float | None] = {}
    for i, k in enumerate(keys):
        window = [series[keys[j]] for j in range(max(0, i - size + 1), i + 1)]
        vals = [v for v in window if v is not None]
        out[k] = sum(vals) / len(vals) if vals else None
    return EvalResult(kind="series", series=out)


def _apply(op: str, a: float, b: float) -> float:
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    return a / b  # div — sıfır kontrolü çağıran yerde


async def _arith(db, node, op, start, end, grain, tz, resolve_ref) -> EvalResult:
    results = [await _ev(db, a, start, end, grain, tz, resolve_ref) for a in node["args"]]
    on_zero = node.get("on_zero", "null")
    is_series = any(r.kind == "series" for r in results)

    if not is_series:
        acc = results[0].scalar
        for r in results[1:]:
            acc = _combine(op, acc, r.scalar, on_zero)
        return EvalResult(kind="scalar", scalar=acc)

    keys: set[datetime] = set()
    for r in results:
        if r.kind == "series":
            keys |= set((r.series or {}).keys())
    out: dict[datetime, float | None] = {}
    for k in keys:
        acc = _at(results[0], k)
        for r in results[1:]:
            acc = _combine(op, acc, _at(r, k), on_zero)
        out[k] = acc
    return EvalResult(kind="series", series=out)


def _at(res: EvalResult, key: datetime) -> float | None:
    if res.kind == "scalar":
        return res.scalar
    return (res.series or {}).get(key)


def _combine(op: str, a: float | None, b: float | None, on_zero: str) -> float | None:
    if a is None or b is None:
        return None
    if op == "div" and b == 0:
        if on_zero == "zero":
            return 0.0
        if on_zero == "fail":
            raise ZeroDivisionError("div on_zero=fail")
        return None
    return _apply(op, a, b)


async def _coalesce(db, args, start, end, grain, tz, resolve_ref) -> EvalResult:
    results = [await _ev(db, a, start, end, grain, tz, resolve_ref) for a in args]
    is_series = any(r.kind == "series" for r in results)
    if not is_series:
        for r in results:
            if r.scalar is not None:
                return EvalResult(kind="scalar", scalar=r.scalar)
        return EvalResult(kind="scalar", scalar=None)
    keys: set[datetime] = set()
    for r in results:
        if r.kind == "series":
            keys |= set((r.series or {}).keys())
    out: dict[datetime, float | None] = {}
    for k in keys:
        chosen: float | None = None
        for r in results:
            v = _at(r, k)
            if v is not None:
                chosen = v
                break
        out[k] = chosen
    return EvalResult(kind="series", series=out)
