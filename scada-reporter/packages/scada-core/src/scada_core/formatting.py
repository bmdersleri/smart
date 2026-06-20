from __future__ import annotations

import json
from typing import Any

from .envelope import Result


def to_json(result: Result, indent: int = 2) -> str:
    return json.dumps(
        {"ok": result.ok, "data": result.data, "error": result.error},
        indent=indent,
        default=str,
        ensure_ascii=False,
    )


def to_text(data: Any) -> str:
    return json.dumps(data, default=str, ensure_ascii=False)
