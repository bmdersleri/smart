from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Result:
    ok: bool
    data: Any = None
    error: dict | None = None

    def legacy(self) -> Any:
        """CLI geriye-uyum çıktısı: başarıda ham data, hatada eski hata sözlüğü."""
        if self.ok:
            return self.data
        err = self.error or {}
        return {"error": True, "status": err.get("status"), "detail": err.get("detail")}


def ok(data: Any) -> Result:
    return Result(ok=True, data=data)


def fail(kind: str, detail: Any, status: int | None = None) -> Result:
    return Result(ok=False, error={"kind": kind, "detail": detail, "status": status})


def from_http_error(resp: httpx.Response) -> Result:
    try:
        detail: Any = resp.json()
    except ValueError:
        detail = resp.text
    return Result(ok=False, error={"kind": "http", "status": resp.status_code, "detail": detail})
