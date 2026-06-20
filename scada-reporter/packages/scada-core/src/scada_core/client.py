from __future__ import annotations

import asyncio
import inspect
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

    # -- Composed capabilities ----------------------------------------------
    async def resolve_ids(self, names: list[str]) -> Result:
        # /api/ai/resolve gövdesi düz JSON listesidir (descriptions: list[str])
        return await self._request("POST", ep.AI_RESOLVE, json=names)

    async def current_values(self, tag_names: list[str] | None = None) -> Result:
        res = await self._request("GET", ep.DASHBOARD_TAGS)
        if not res.ok:
            return res
        rows = res.data.get("items", res.data) if isinstance(res.data, dict) else res.data
        if tag_names:
            wanted = set(tag_names)
            rows = [r for r in rows if r.get("name") in wanted]
        return ok(rows)

    async def query_trend(self, tags: list[str], start: str, end: str) -> Result:
        resolved = await self.resolve_ids(tags)
        if not resolved.ok:
            return resolved
        tag_ids = resolved.data.get("tag_ids", [])
        if not tag_ids:
            return fail("not_found", f"No tags matched: {tags}")
        return await self._request(
            "GET",
            ep.TREND_RANGE,
            params={"tag_ids": tag_ids, "start": start, "end": end},
        )

    async def resolve_tag(self, query: str) -> Result:
        resolved = await self.resolve_ids([query])
        if not resolved.ok:
            return resolved
        tag_ids = set(resolved.data.get("tag_ids", []))
        listing = await self.list_tags()
        if not listing.ok:
            return listing
        matches = [t for t in listing.data if t.get("id") in tag_ids]
        return ok({"query": query, "matches": matches, "count": len(matches)})

    async def system_health(self) -> Result:
        health = await self.health()
        plcs = await self.list_plcs()
        tags = await self.list_tags()
        return ok(
            {
                "health": health.data if health.ok else None,
                "plc_count": len(plcs.data) if plcs.ok and isinstance(plcs.data, list) else 0,
                "tag_count": len(tags.data) if tags.ok and isinstance(tags.data, list) else 0,
            }
        )

    # -- Auth extras ---------------------------------------------------------
    async def register(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str = "",
        role: str = "operator",
    ) -> Result:
        return await self._request(
            "POST",
            ep.AUTH_REGISTER,
            json={
                "username": username,
                "email": email,
                "password": password,
                "full_name": full_name,
                "role": role,
            },
        )

    async def me(self) -> Result:
        return await self._request("GET", ep.AUTH_ME)

    # -- Tag writes / readings ----------------------------------------------
    async def create_tag(
        self,
        node_id: str,
        name: str,
        description: str = "",
        unit: str = "",
        channel: str = "",
        device: str = "",
    ) -> Result:
        return await self._request(
            "POST",
            ep.TAGS,
            json={
                "node_id": node_id,
                "name": name,
                "description": description,
                "unit": unit,
                "channel": channel,
                "device": device,
            },
        )

    async def delete_tag(self, tag_id: int) -> Result:
        res = await self._request("DELETE", ep.TAG_ITEM.format(tag_id=tag_id))
        if not res.ok:
            return res
        return ok({"deleted": True, "tag_id": tag_id})

    async def update_tag(
        self,
        tag_id: int,
        unit: str | None = None,
        device: str | None = None,
        channel: str | None = None,
        description: str | None = None,
        min_alarm: float | None = None,
        max_alarm: float | None = None,
    ) -> Result:
        payload: dict[str, Any] = {}
        if unit is not None:
            payload["unit"] = unit
        if device is not None:
            payload["device"] = device
        if channel is not None:
            payload["channel"] = channel
        if description is not None:
            payload["description"] = description
        if min_alarm is not None:
            payload["min_alarm"] = min_alarm
        if max_alarm is not None:
            payload["max_alarm"] = max_alarm
        if not payload:
            raise ValueError("update_tag: at least one field must be provided")
        return await self._request("PATCH", ep.TAG_ITEM.format(tag_id=tag_id), json=payload)

    async def get_readings(
        self,
        tag_id: int,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> Result:
        params: dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return await self._request("GET", ep.TAG_READINGS.format(tag_id=tag_id), params=params)

    # -- Dashboard / trend (by id) ------------------------------------------
    async def overview(self) -> Result:
        return await self._request("GET", ep.DASHBOARD_OVERVIEW)

    async def trend(self, tag_ids: list[int], hours: int = 24) -> Result:
        return await self._request("GET", ep.TREND, params={"tag_ids": tag_ids, "hours": hours})

    # -- Reports (by id) -----------------------------------------------------
    async def reports_generate_by_ids(
        self,
        tag_ids: list[int],
        start: str,
        end: str,
        interval: str = "hourly",
        output_format: str = "json",
    ) -> Result:
        return await self._request(
            "POST",
            ep.REPORTS_GENERATE,
            json={
                "tag_ids": tag_ids,
                "start": start,
                "end": end,
                "interval": interval,
                "format": output_format,
            },
        )

    async def list_report_history(self) -> Result:
        return await self._request("GET", ep.REPORTS_HISTORY)

    async def download_report_history(self, history_id: int) -> Result:
        path = f"{ep.REPORTS_HISTORY}/{history_id}/download"
        try:
            resp = await self._client.request("GET", "/" + path.lstrip("/"))
        except httpx.HTTPError as exc:
            return fail("connection", str(exc))
        if resp.status_code >= 400:
            return from_http_error(resp)
        cd = resp.headers.get("content-disposition", "")
        filename = f"scada_rapor_{history_id}.bin"
        for token in (t.strip() for t in cd.split(";")):
            if token.lower().startswith("filename="):
                filename = token[len("filename=") :].strip('"').strip("'")
                break
        return ok({"content": resp.content, "filename": filename})

    # -- Explore -------------------------------------------------------------
    async def explore_schema(self) -> Result:
        return await self._request("GET", ep.EXPLORE_SCHEMA)

    async def explore_summary(self) -> Result:
        return await self._request("GET", ep.EXPLORE_SUMMARY)

    # -- AI passthrough ------------------------------------------------------
    async def ai_health(self) -> Result:
        return await self._request("GET", ep.AI_HEALTH)

    async def ai_query(self, question: str) -> Result:
        return await self._request("POST", ep.AI_QUERY, json={"question": question})

    # -- Spec 2: tag / watchlist / annotation writes --------------------------
    async def import_csv_tags(self, payload: dict) -> Result:
        return await self._request("POST", ep.TAG_IMPORT_CSV, json=payload)

    async def watchlist_add(self, tag_id: int) -> Result:
        return await self._request("POST", ep.WATCHLIST_ITEM.format(tag_id=tag_id))

    async def watchlist_remove(self, tag_id: int) -> Result:
        return await self._request("DELETE", ep.WATCHLIST_ITEM.format(tag_id=tag_id))

    async def annotation_add(self, ts: str, text: str, tag_id: int | None = None) -> Result:
        return await self._request(
            "POST", ep.ANNOTATIONS, json={"ts": ts, "text": text, "tag_id": tag_id}
        )

    async def annotation_delete(self, annotation_id: int) -> Result:
        return await self._request("DELETE", ep.ANNOTATION_ITEM.format(annotation_id=annotation_id))

    # -- Spec 2: report templates / scheduled ------------------------------
    async def template_create(self, payload: dict) -> Result:
        return await self._request("POST", ep.ADV_TEMPLATES, json=payload)

    async def template_update(self, template_id: int, payload: dict) -> Result:
        return await self._request(
            "PUT", ep.ADV_TEMPLATE_ITEM.format(template_id=template_id), json=payload
        )

    async def template_run(
        self, template_id: int, start: str | None = None, end: str | None = None
    ) -> Result:
        return await self._request(
            "POST",
            ep.ADV_TEMPLATE_RUN.format(template_id=template_id),
            json={"start": start, "end": end},
        )

    async def template_delete(self, template_id: int) -> Result:
        return await self._request("DELETE", ep.ADV_TEMPLATE_ITEM.format(template_id=template_id))

    async def scheduled_create(self, payload: dict) -> Result:
        return await self._request("POST", ep.ADV_SCHEDULED, json=payload)

    async def scheduled_update(self, scheduled_id: int, payload: dict) -> Result:
        return await self._request(
            "PUT", ep.ADV_SCHEDULED_ITEM.format(scheduled_id=scheduled_id), json=payload
        )

    async def scheduled_toggle(self, scheduled_id: int) -> Result:
        return await self._request(
            "PATCH", ep.ADV_SCHEDULED_TOGGLE.format(scheduled_id=scheduled_id)
        )

    async def scheduled_delete(self, scheduled_id: int) -> Result:
        return await self._request(
            "DELETE", ep.ADV_SCHEDULED_ITEM.format(scheduled_id=scheduled_id)
        )

    async def archive_delete(self, archive_id: int) -> Result:
        return await self._request("DELETE", ep.ADV_ARCHIVE_ITEM.format(archive_id=archive_id))

    # -- Spec 2: group / plc / user writes ---------------------------------
    async def group_create(
        self, name: str, parent_id: int | None = None, sort_order: int = 0
    ) -> Result:
        return await self._request(
            "POST",
            ep.GROUPS,
            json={"name": name, "parent_id": parent_id, "sort_order": sort_order},
        )

    async def group_update(
        self,
        group_id: int,
        name: str | None = None,
        parent_id: int | None = None,
        sort_order: int | None = None,
    ) -> Result:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if sort_order is not None:
            payload["sort_order"] = sort_order
        if not payload:
            raise ValueError("group_update: at least one field required")
        return await self._request("PATCH", ep.GROUP_ITEM.format(group_id=group_id), json=payload)

    async def group_assign(self, group_id: int, tag_ids: list[int]) -> Result:
        return await self._request(
            "POST", ep.GROUP_ASSIGN.format(group_id=group_id), json={"tag_ids": tag_ids}
        )

    async def group_unassign(self, tag_ids: list[int]) -> Result:
        return await self._request("POST", ep.GROUP_UNASSIGN, json={"tag_ids": tag_ids})

    async def group_delete(self, group_id: int) -> Result:
        return await self._request("DELETE", ep.GROUP_ITEM.format(group_id=group_id))

    async def plc_create(self, name: str, ip: str = "", rack: int = 0, slot: int = 1) -> Result:
        return await self._request(
            "POST", ep.PLC, json={"name": name, "ip": ip, "rack": rack, "slot": slot}
        )

    async def plc_update(self, name: str, ip: str, rack: int = 0, slot: int = 1) -> Result:
        return await self._request(
            "PATCH",
            ep.PLC_ITEM.format(name=name),
            json={"ip": ip, "rack": rack, "slot": slot},
        )

    async def plc_delete(self, name: str) -> Result:
        return await self._request("DELETE", ep.PLC_ITEM.format(name=name))

    async def user_create(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str = "",
        role: str = "operator",
        permission_overrides: dict | None = None,
    ) -> Result:
        return await self._request(
            "POST",
            ep.USERS,
            json={
                "username": username,
                "email": email,
                "password": password,
                "full_name": full_name,
                "role": role,
                "permission_overrides": permission_overrides or {},
            },
        )

    async def user_update(
        self,
        user_id: int,
        email: str | None = None,
        full_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        permission_overrides: dict | None = None,
    ) -> Result:
        payload: dict[str, Any] = {}
        if email is not None:
            payload["email"] = email
        if full_name is not None:
            payload["full_name"] = full_name
        if role is not None:
            payload["role"] = role
        if is_active is not None:
            payload["is_active"] = is_active
        if permission_overrides is not None:
            payload["permission_overrides"] = permission_overrides
        if not payload:
            raise ValueError("user_update: at least one field required")
        return await self._request("PATCH", ep.USER_ITEM.format(user_id=user_id), json=payload)

    async def user_set_password(self, user_id: int, password: str) -> Result:
        return await self._request(
            "POST", ep.USER_PASSWORD.format(user_id=user_id), json={"password": password}
        )

    async def user_delete(self, user_id: int) -> Result:
        return await self._request("DELETE", ep.USER_ITEM.format(user_id=user_id))

    async def aclose(self) -> None:
        await self._client.aclose()


class SyncScadaClient:
    """AsyncScadaClient üzerine senkron facade — CLI bunu kullanır."""

    def __init__(self, *args, **kwargs) -> None:
        self._async = AsyncScadaClient(*args, **kwargs)

    def _run(self, coro):
        return asyncio.run(coro)

    def set_token(self, token: str) -> None:
        self._async.set_token(token)

    def __getattr__(self, name: str):
        attr = getattr(self._async, name)
        if inspect.iscoroutinefunction(attr):

            def wrapper(*a, **kw):
                return self._run(attr(*a, **kw))

            return wrapper
        return attr

    def close(self) -> None:
        self._run(self._async.aclose())
