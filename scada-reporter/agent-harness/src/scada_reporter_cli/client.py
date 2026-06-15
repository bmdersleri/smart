from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import httpx


API_BASE = os.environ.get("SCADA_API_URL", "http://localhost:8001")


class ScadaClient:
    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)

    # -- Auth -----------------------------------------------------------------

    def login(self, username: str, password: str) -> dict[str, Any]:
        resp = self._client.post(
            urljoin(self.base_url + "/", "api/auth/token"),
            data={"username": username, "password": password},
        )
        if resp.status_code != 200:
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        data = resp.json()
        self._token = data["access_token"]
        self._client.headers.update({"Authorization": f"Bearer {self._token}"})
        return data

    def register(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str = "",
        role: str = "operator",
    ) -> dict[str, Any]:
        resp = self._client.post(
            urljoin(self.base_url + "/", "api/auth/register"),
            json={
                "username": username,
                "email": email,
                "password": password,
                "full_name": full_name,
                "role": role,
            },
        )
        if resp.status_code not in (200, 201):
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        return resp.json()

    def me(self) -> dict[str, Any]:
        resp = self._client.get(urljoin(self.base_url + "/", "api/auth/me"))
        if resp.status_code != 200:
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        return resp.json()

    def set_token(self, token: str) -> None:
        self._token = token
        self._client.headers.update({"Authorization": f"Bearer {self._token}"})

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    # -- Tags -----------------------------------------------------------------

    def list_tags(self) -> list[dict[str, Any]]:
        resp = self._client.get(urljoin(self.base_url + "/", "api/tags/"))
        if resp.status_code != 200:
            return [{"error": True, "status": resp.status_code, "detail": resp.text}]
        return resp.json()  # type: ignore[return-value]

    def create_tag(
        self,
        node_id: str,
        name: str,
        description: str = "",
        unit: str = "",
        channel: str = "",
        device: str = "",
    ) -> dict[str, Any]:
        resp = self._client.post(
            urljoin(self.base_url + "/", "api/tags/"),
            json={
                "node_id": node_id,
                "name": name,
                "description": description,
                "unit": unit,
                "channel": channel,
                "device": device,
            },
        )
        if resp.status_code not in (200, 201):
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        return resp.json()

    def delete_tag(self, tag_id: int) -> dict[str, Any]:
        resp = self._client.delete(urljoin(self.base_url + "/", f"api/tags/{tag_id}"))
        if resp.status_code not in (200, 204):
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        return {"deleted": True, "tag_id": tag_id}

    def update_tag(
        self,
        tag_id: int,
        unit: str | None = None,
        device: str | None = None,
        channel: str | None = None,
        description: str | None = None,
        min_alarm: float | None = None,
        max_alarm: float | None = None,
    ) -> dict[str, Any]:
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
        resp = self._client.patch(
            urljoin(self.base_url + "/", f"api/tags/{tag_id}"),
            json=payload,
        )
        if resp.status_code != 200:
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        return resp.json()

    def get_readings(
        self,
        tag_id: int,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        resp = self._client.get(
            urljoin(self.base_url + "/", f"api/tags/{tag_id}/readings"), params=params
        )
        if resp.status_code != 200:
            return [{"error": True, "status": resp.status_code, "detail": resp.text}]
        return resp.json()  # type: ignore[return-value]

    # -- Dashboard ------------------------------------------------------------

    def overview(self) -> dict[str, Any]:
        resp = self._client.get(urljoin(self.base_url + "/", "api/dashboard/overview"))
        if resp.status_code != 200:
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        return resp.json()

    def current_values(self) -> list[dict[str, Any]]:
        resp = self._client.get(
            urljoin(self.base_url + "/", "api/dashboard/current-values")
        )
        if resp.status_code != 200:
            return [{"error": True, "status": resp.status_code, "detail": resp.text}]
        return resp.json()  # type: ignore[return-value]

    def trend(self, tag_ids: list[int], hours: int = 24) -> list[dict[str, Any]]:
        resp = self._client.get(
            urljoin(self.base_url + "/", "api/dashboard/trend"),
            params={"tag_ids": tag_ids, "hours": hours},
        )
        if resp.status_code != 200:
            return [{"error": True, "status": resp.status_code, "detail": resp.text}]
        return resp.json()  # type: ignore[return-value]

    # -- Reports --------------------------------------------------------------

    def generate_report(
        self,
        tag_ids: list[int],
        start: str,
        end: str,
        interval: str = "hourly",
        output_format: str = "json",
    ) -> Any:
        resp = self._client.post(
            urljoin(self.base_url + "/", "api/reports/generate"),
            json={
                "tag_ids": tag_ids,
                "start": start,
                "end": end,
                "interval": interval,
                "format": output_format,
            },
        )
        if resp.status_code != 200:
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        if output_format == "json":
            return resp.json()
        return resp.content

    def list_report_history(self) -> list[dict[str, Any]]:
        resp = self._client.get(urljoin(self.base_url + "/", "api/reports/history"))
        if resp.status_code != 200:
            return [{"error": True, "status": resp.status_code, "detail": resp.text}]
        return resp.json()  # type: ignore[return-value]

    def download_report_history(self, history_id: int) -> dict[str, Any]:
        resp = self._client.get(
            urljoin(self.base_url + "/", f"api/reports/history/{history_id}/download")
        )
        if resp.status_code != 200:
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        cd = resp.headers.get("content-disposition", "")
        tokens = [t.strip() for t in cd.split(";")]
        filename = f"scada_rapor_{history_id}.bin"
        for token in tokens:
            if token.lower().startswith("filename="):
                filename = token[len("filename=") :].strip('"').strip("'")
                break
        return {"content": resp.content, "filename": filename}

    def health(self) -> dict[str, Any]:
        try:
            resp = self._client.get(urljoin(self.base_url + "/", "health"))
            if resp.status_code != 200:
                return {"error": True, "detail": resp.text}
            return resp.json()
        except Exception as e:
            return {"error": True, "detail": str(e)}

    # -- Query ---------------------------------------------------------------

    def run_query(
        self, sql: str, params: dict | None = None, limit: int = 5000
    ) -> dict:
        resp = self._client.post(
            urljoin(self.base_url + "/", "api/query/run"),
            json={"sql": sql, "params": params, "limit": limit},
        )
        if resp.status_code != 200:
            return {"error": True, "status": resp.status_code, "detail": resp.text}
        return resp.json()

    # -- Explore -------------------------------------------------------------

    def explore_schema(self) -> dict:
        resp = self._client.get(urljoin(self.base_url + "/", "api/explore/schema"))
        if resp.status_code != 200:
            return {"error": True, "detail": resp.text}
        return resp.json()

    def explore_summary(self) -> dict:
        resp = self._client.get(urljoin(self.base_url + "/", "api/explore/summary"))
        if resp.status_code != 200:
            return {"error": True, "detail": resp.text}
        return resp.json()

    def close(self) -> None:
        self._client.close()
