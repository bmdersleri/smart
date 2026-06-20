from __future__ import annotations

import os
from typing import Any

import httpx

from . import endpoints as ep
from .envelope import Result, from_http_error, ok, fail

DEFAULT_BASE = os.environ.get("SCADA_API_URL", "http://localhost:8001")


class AsyncScadaClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=30.0,
            transport=transport,
            follow_redirects=True,
        )

    def set_token(self, token: str) -> None:
        self._token = token
        self._client.headers["Authorization"] = f"Bearer {token}"

    async def _request(self, method: str, path: str, **kw: Any) -> Result:
        try:
            resp = await self._client.request(method, "/" + path.lstrip("/"), **kw)
        except httpx.HTTPError as exc:
            return fail("connection", str(exc))
        if resp.status_code >= 400:
            return from_http_error(resp)
        try:
            return ok(resp.json())
        except ValueError:
            return ok(resp.content)

    # -- Auth ----------------------------------------------------------------
    async def login(self, username: str, password: str) -> Result:
        res = await self._request(
            "POST", ep.AUTH_TOKEN, data={"username": username, "password": password}
        )
        if res.ok and isinstance(res.data, dict) and res.data.get("access_token"):
            self.set_token(res.data["access_token"])
        return res

    # -- Simple reads --------------------------------------------------------
    async def list_tags(self) -> Result:
        return await self._request("GET", ep.TAGS)

    async def list_plcs(self) -> Result:
        return await self._request("GET", ep.PLC)

    async def run_sql(self, sql: str, params: dict | None = None, limit: int = 5000) -> Result:
        return await self._request(
            "POST", ep.QUERY_RUN, json={"sql": sql, "params": params, "limit": limit}
        )

    async def detect_anomalies(
        self, tag_name: str, window: str = "7d", threshold: float = 3.0
    ) -> Result:
        return await self._request(
            "POST",
            ep.AI_ANOMALIES,
            json={"tag_name": tag_name, "window": window, "threshold": threshold},
        )

    async def predict_trend(self, tag_name: str, horizon: str = "24h") -> Result:
        return await self._request(
            "POST", ep.AI_PREDICT, json={"tag_name": tag_name, "horizon": horizon}
        )

    async def generate_report(
        self,
        tags: list[str],
        start: str,
        end: str,
        fmt: str = "excel",
        aggregation: str = "raw",
    ) -> Result:
        return await self._request(
            "POST",
            ep.AI_REPORTS_GENERATE,
            json={
                "tags": tags,
                "start": start,
                "end": end,
                "format": fmt,
                "aggregation": aggregation,
            },
        )

    async def health(self) -> Result:
        return await self._request("GET", ep.HEALTH)

    async def aclose(self) -> None:
        await self._client.aclose()
