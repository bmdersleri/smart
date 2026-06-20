from __future__ import annotations

import json
from typing import Any


def banner() -> str:
    return """
╔══════════════════════════════════════════╗
║        EKONT SMART REPORT Agent CLI        ║
║     Su/Atıksu Tesisi SCADA Sistemi       ║
╚══════════════════════════════════════════╝
"""


def success(msg: str) -> str:
    return f"✓ {msg}"


def error(msg: str) -> str:
    return f"✗ {msg}"


def warn(msg: str) -> str:
    return f"⚠ {msg}"


def info(msg: str) -> str:
    return f"ℹ {msg}"


def fmt_table(rows: list[dict[str, Any]], keys: list[str] | None = None) -> str:
    if not rows:
        return "(empty)"
    if keys is None:
        keys = list(rows[0].keys())
    col_widths = {k: len(k) for k in keys}
    for r in rows:
        for k in keys:
            col_widths[k] = max(col_widths[k], len(str(r.get(k, ""))))
    sep = " | ".join(k.ljust(col_widths[k]) for k in keys)
    line = "-+-".join("-" * col_widths[k] for k in keys)
    out = [sep, line]
    for r in rows:
        out.append(" | ".join(str(r.get(k, "")).ljust(col_widths[k]) for k in keys))
    return "\n".join(out)


def fmt_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)
