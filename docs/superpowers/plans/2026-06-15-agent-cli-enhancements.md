# Agent CLI Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync the `scada` agent CLI with the new backend endpoints added in the UI/UX sprint (alarm thresholds, report history), add alarm-aware display + live watch mode to `current-values`, and add the missing `explore tags` command documented in TOOL.md.

**Architecture:** All new commands follow the existing pattern — each command module has its own `_get_client()` helper, `ScadaClient` handles HTTP, `--json-output` flag enables machine-readable output. Tests mock at the `ScadaClient` level using `unittest.mock.patch` so no running backend is needed.

**Tech Stack:** Python 3.14 · Click 8 · httpx · pytest · `scada-reporter/agent-harness/`

**Spec:** `docs/superpowers/specs/2026-06-15-ui-ux-improvements-design.md` (backend endpoints)

---

## File Map

### Modified
- `scada-reporter/agent-harness/src/scada_reporter_cli/client.py` — 3 new methods: `update_tag`, `list_report_history`, `download_report_history`
- `scada-reporter/agent-harness/src/scada_reporter_cli/commands/tags.py` — add `update` subcommand
- `scada-reporter/agent-harness/src/scada_reporter_cli/commands/dashboard.py` — `current-values` gains `alarm_state` column + `--alarm-only` + `--watch`
- `scada-reporter/agent-harness/src/scada_reporter_cli/commands/reports.py` — add `list-history` + `download-history`
- `scada-reporter/agent-harness/src/scada_reporter_cli/commands/explore.py` — add `tags` subcommand
- `scada-reporter/agent-harness/tests/test_cli.py` — proper mocked tests for all new commands
- `scada-reporter/agent-harness/skills/SKILL.md` — add new commands to capability list
- `scada-reporter/commands/scada-tags.md` — add `update` usage
- `scada-reporter/commands/scada-reports.md` — add history usage
- `scada-reporter/commands/scada-dashboard.md` — add `--alarm-only` / `--watch` usage
- `TOOL.md` — update Project CLI table

---

## Task 1: ScadaClient — 3 new API methods

**Files:**
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/client.py`

- [ ] **Step 1: Write failing tests for the 3 new client methods**

Add to `scada-reporter/agent-harness/tests/test_cli.py` (below existing imports):

```python
import httpx
from unittest.mock import patch, MagicMock
from scada_reporter_cli.client import ScadaClient


def test_client_update_tag_success(respx_mock):
    """update_tag sends PATCH and returns updated tag."""
    pass  # will use mock approach below
```

Actually, `respx` is not installed. Use `unittest.mock` instead — mock the internal `_client` attribute:

```python
def test_client_update_tag():
    """update_tag sends PATCH /api/tags/{id} with the right payload."""
    sc = ScadaClient("http://testserver")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 7, "node_id": "DB1,REAL0", "name": "Test",
        "unit": "bar", "device": "PLC", "channel": "Ch1",
        "is_active": True, "min_alarm": 0.0, "max_alarm": 5000.0,
    }
    sc._client.patch = MagicMock(return_value=mock_resp)

    result = sc.update_tag(7, unit="bar", min_alarm=0.0, max_alarm=5000.0)

    sc._client.patch.assert_called_once()
    call_kwargs = sc._client.patch.call_args
    assert "api/tags/7" in call_kwargs[0][0]
    assert call_kwargs[1]["json"]["unit"] == "bar"
    assert call_kwargs[1]["json"]["min_alarm"] == 0.0
    assert result["id"] == 7
    assert result["min_alarm"] == 0.0


def test_client_update_tag_error():
    """update_tag returns error dict on non-200."""
    sc = ScadaClient("http://testserver")
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Tag bulunamadi"
    sc._client.patch = MagicMock(return_value=mock_resp)

    result = sc.update_tag(999)

    assert result["error"] is True
    assert result["status"] == 404


def test_client_list_report_history():
    """list_report_history returns list of history records."""
    sc = ScadaClient("http://testserver")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"id": 1, "format": "json", "interval": "hourly",
         "tag_ids": [1, 2], "created_at": "2026-06-15T22:00:00",
         "start": "2026-06-15T00:00:00", "end": "2026-06-15T22:00:00"}
    ]
    sc._client.get = MagicMock(return_value=mock_resp)

    result = sc.list_report_history()

    assert len(result) == 1
    assert result[0]["format"] == "json"
    assert "api/reports/history" in sc._client.get.call_args[0][0]


def test_client_download_report_history():
    """download_report_history returns content bytes + filename from header."""
    sc = ScadaClient("http://testserver")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"fake-excel-bytes"
    mock_resp.headers = {"content-disposition": 'attachment; filename="report.xlsx"'}
    sc._client.get = MagicMock(return_value=mock_resp)

    result = sc.download_report_history(3)

    assert result["content"] == b"fake-excel-bytes"
    assert result["filename"] == "report.xlsx"
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_client_update_tag tests/test_cli.py::test_client_update_tag_error tests/test_cli.py::test_client_list_report_history tests/test_cli.py::test_client_download_report_history -v
```

Expected: `FAILED` — `ScadaClient` has no `update_tag` / `list_report_history` / `download_report_history`.

- [ ] **Step 3: Add the 3 methods to ScadaClient**

In `src/scada_reporter_cli/client.py`, add after the existing `delete_tag` method (inside the `# -- Tags` section):

```python
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
    resp = self._client.patch(
        urljoin(self.base_url + "/", f"api/tags/{tag_id}"),
        json=payload,
    )
    if resp.status_code != 200:
        return {"error": True, "status": resp.status_code, "detail": resp.text}
    return resp.json()
```

Add after `generate_report` (inside the `# -- Reports` section):

```python
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
    filename = f"scada_rapor_{history_id}.bin"
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip('"').strip("'")
    return {"content": resp.content, "filename": filename}
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_client_update_tag tests/test_cli.py::test_client_update_tag_error tests/test_cli.py::test_client_list_report_history tests/test_cli.py::test_client_download_report_history -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
cd C:/project/smart
git add scada-reporter/agent-harness/src/scada_reporter_cli/client.py scada-reporter/agent-harness/tests/test_cli.py
git commit -m "feat: add update_tag, list_report_history, download_report_history to ScadaClient"
```

---

## Task 2: `tags update` command

**Files:**
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/tags.py`
- Modify: `scada-reporter/agent-harness/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_tags_update_success():
    """tags update calls update_tag and prints confirmation."""
    mock_client = MagicMock()
    mock_client.update_tag.return_value = {
        "id": 1, "node_id": "DB1,REAL0", "name": "Test",
        "unit": "bar", "device": "PLC", "channel": "Ch1",
        "is_active": True, "min_alarm": 0.0, "max_alarm": 5000.0,
    }
    with patch("scada_reporter_cli.commands.tags.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.tags.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, [
            "tags", "update", "1",
            "--unit", "bar", "--min-alarm", "0", "--max-alarm", "5000",
        ])
    assert result.exit_code == 0
    assert "güncellendi" in result.output or "1" in result.output
    mock_client.update_tag.assert_called_once_with(
        1, unit="bar", device=None, channel=None,
        description=None, min_alarm=0.0, max_alarm=5000.0,
    )


def test_tags_update_validation_error():
    """tags update blocks min >= max without hitting the API."""
    mock_client = MagicMock()
    with patch("scada_reporter_cli.commands.tags.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.tags.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, [
            "tags", "update", "1",
            "--min-alarm", "5000", "--max-alarm", "0",
        ])
    assert result.exit_code == 0
    assert "min" in result.output.lower() or "küçük" in result.output.lower()
    mock_client.update_tag.assert_not_called()


def test_tags_update_json_output():
    """tags update --json-output prints the full tag JSON."""
    mock_client = MagicMock()
    mock_client.update_tag.return_value = {
        "id": 2, "node_id": "DB2,REAL0", "name": "Hat2",
        "unit": "m3/h", "device": "Hat2", "channel": "Ch1",
        "is_active": True, "min_alarm": None, "max_alarm": None,
    }
    with patch("scada_reporter_cli.commands.tags.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.tags.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, [
            "tags", "update", "2", "--unit", "m3/h", "--json-output",
        ])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert data["id"] == 2
    assert data["unit"] == "m3/h"
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_tags_update_success tests/test_cli.py::test_tags_update_validation_error tests/test_cli.py::test_tags_update_json_output -v
```

Expected: `FAILED` — `tags update` subcommand doesn't exist.

- [ ] **Step 3: Add `update` command to tags.py**

In `src/scada_reporter_cli/commands/tags.py`, add after the `delete` command:

```python
@tags_cmd.command(name="update")
@click.argument("tag-id", type=int)
@click.option("--unit", default=None, help="Birim (örn. m³/h, bar)")
@click.option("--device", default=None, help="Cihaz/PLC adı")
@click.option("--channel", default=None, help="Kanal/group")
@click.option("--description", default=None, help="Açıklama")
@click.option("--min-alarm", type=float, default=None, help="Min alarm eşiği")
@click.option("--max-alarm", type=float, default=None, help="Max alarm eşiği")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def update(
    tag_id: int,
    unit: str | None,
    device: str | None,
    channel: str | None,
    description: str | None,
    min_alarm: float | None,
    max_alarm: float | None,
    json_output: bool,
):
    """Tag güncelle (birim, cihaz, kanal, alarm eşikleri)."""
    if min_alarm is not None and max_alarm is not None and min_alarm >= max_alarm:
        click.echo(error("Min alarm değeri Max alarm'dan küçük olmalı"))
        return
    client, ok = _get_client()
    if not ok:
        return
    result = client.update_tag(
        tag_id,
        unit=unit,
        device=device,
        channel=channel,
        description=description,
        min_alarm=min_alarm,
        max_alarm=max_alarm,
    )
    if "error" in result and result["error"]:
        click.echo(error(f"Güncelleme başarısız: {result.get('detail', 'bilinmeyen hata')}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        parts: list[str] = []
        if unit:
            parts.append(f"birim={unit}")
        if device:
            parts.append(f"cihaz={device}")
        if min_alarm is not None:
            parts.append(f"min_alarm={min_alarm}")
        if max_alarm is not None:
            parts.append(f"max_alarm={max_alarm}")
        click.echo(success(f"Tag {tag_id} güncellendi: {', '.join(parts) or 'değişiklik yok'}"))
    client.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_tags_update_success tests/test_cli.py::test_tags_update_validation_error tests/test_cli.py::test_tags_update_json_output -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
cd C:/project/smart
git add scada-reporter/agent-harness/src/scada_reporter_cli/commands/tags.py scada-reporter/agent-harness/tests/test_cli.py
git commit -m "feat: add 'scada tags update' command with alarm threshold support"
```

---

## Task 3: `dashboard current-values` alarm enhancements

**Files:**
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/dashboard.py`
- Modify: `scada-reporter/agent-harness/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
_SAMPLE_VALUES = [
    {"tag_id": 1, "name": "Hat1_Debi", "device": "Hat1", "unit": "m3/h",
     "value": 3500.0, "timestamp": "2026-06-15T22:00:00", "quality_ok": True, "alarm_state": "max"},
    {"tag_id": 2, "name": "Havuz_Seviye", "device": "Havuz", "unit": "mm",
     "value": 1027604480.0, "timestamp": "2026-06-15T22:00:00", "quality_ok": False, "alarm_state": "overflow"},
    {"tag_id": 3, "name": "Hat2_Debi", "device": "Hat2", "unit": "m3/h",
     "value": 1200.0, "timestamp": "2026-06-15T22:00:00", "quality_ok": True, "alarm_state": None},
]


def test_current_values_shows_alarm_column():
    """current-values table includes alarm_state column."""
    mock_client = MagicMock()
    mock_client.current_values.return_value = _SAMPLE_VALUES
    with patch("scada_reporter_cli.commands.dashboard.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.dashboard.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, ["dashboard", "current-values"])
    assert result.exit_code == 0
    assert "alarm" in result.output.lower()
    assert "MAX" in result.output or "OVERFLOW" in result.output


def test_current_values_alarm_only_filter():
    """--alarm-only shows only rows with alarm_state != None."""
    mock_client = MagicMock()
    mock_client.current_values.return_value = _SAMPLE_VALUES
    with patch("scada_reporter_cli.commands.dashboard.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.dashboard.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, ["dashboard", "current-values", "--alarm-only"])
    assert result.exit_code == 0
    assert "Hat2_Debi" not in result.output  # no alarm, should be filtered out
    assert "Hat1_Debi" in result.output or "Havuz_Seviye" in result.output


def test_current_values_json_includes_alarm_state():
    """--json-output includes alarm_state field."""
    import json
    mock_client = MagicMock()
    mock_client.current_values.return_value = _SAMPLE_VALUES
    with patch("scada_reporter_cli.commands.dashboard.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.dashboard.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, ["dashboard", "current-values", "--json-output"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert any("alarm_state" in item for item in data)
    overflow_items = [i for i in data if i["alarm_state"] == "overflow"]
    assert len(overflow_items) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_current_values_shows_alarm_column tests/test_cli.py::test_current_values_alarm_only_filter tests/test_cli.py::test_current_values_json_includes_alarm_state -v
```

Expected: `FAILED` — current-values has no alarm column and no `--alarm-only`.

- [ ] **Step 3: Replace `current_values` command in dashboard.py**

Replace the entire `current_values` function (lines 44-73) with:

```python
_ALARM_LABELS = {"overflow": "OVERFLOW", "max": "MAX AŞIMI", "min": "MIN ALTI"}


@dashboard_cmd.command(name="current-values")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
@click.option("--alarm-only", is_flag=True, help="Sadece alarm durumundaki tag'leri göster")
@click.option(
    "--watch",
    "watch_interval",
    type=int,
    default=0,
    metavar="SANIYE",
    help="Her N saniyede bir yenile (0=devre dışı). Ctrl+C ile çık.",
)
def current_values(json_output: bool, alarm_only: bool, watch_interval: int):
    """Tüm tag'lerin son değerlerini göster."""
    import time
    from datetime import datetime

    def _render() -> bool:
        client, ok = _get_client()
        if not ok:
            return False
        result = client.current_values()
        client.close()
        if isinstance(result, list) and result and "error" in result[0]:
            click.echo(error(f"Hata: {result[0].get('detail', 'bilinmeyen hata')}"))
            return False
        if alarm_only:
            result = [r for r in result if r.get("alarm_state") is not None]
        if json_output:
            click.echo(fmt_json(result))
            return True
        if not result:
            click.echo("(alarm yok)" if alarm_only else "(veri yok)")
            return True
        rows = [
            {
                "cihaz": r["device"],
                "tag": r["name"],
                "değer": r["value"],
                "birim": r["unit"],
                "kalite": "✓" if r["quality_ok"] else "✗",
                "alarm": _ALARM_LABELS.get(r.get("alarm_state", ""), "—") if r.get("alarm_state") else "—",
            }
            for r in result
        ]
        click.echo(fmt_table(rows, ["cihaz", "tag", "değer", "birim", "kalite", "alarm"]))
        alarm_count = sum(1 for r in result if r.get("alarm_state"))
        if alarm_count:
            click.echo(f"\n⚠  {alarm_count} alarm aktif")
        return True

    if watch_interval > 0:
        try:
            while True:
                click.clear()
                click.echo(f"[{datetime.now().strftime('%H:%M:%S')}] Yenileniyor (Ctrl+C ile çık)\n")
                if not _render():
                    break
                time.sleep(watch_interval)
        except KeyboardInterrupt:
            click.echo(info("\nDurduruldu."))
    else:
        _render()
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_current_values_shows_alarm_column tests/test_cli.py::test_current_values_alarm_only_filter tests/test_cli.py::test_current_values_json_includes_alarm_state -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
cd C:/project/smart
git add scada-reporter/agent-harness/src/scada_reporter_cli/commands/dashboard.py scada-reporter/agent-harness/tests/test_cli.py
git commit -m "feat: current-values alarm column, --alarm-only filter, --watch live mode"
```

---

## Task 4: `reports list-history` + `reports download-history`

**Files:**
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/reports.py`
- Modify: `scada-reporter/agent-harness/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
_SAMPLE_HISTORY = [
    {
        "id": 3, "format": "excel", "interval": "daily",
        "tag_ids": [1, 2, 3],
        "created_at": "2026-06-15T22:07:00",
        "start": "2026-06-08T00:00:00",
        "end": "2026-06-15T22:00:00",
    },
    {
        "id": 2, "format": "json", "interval": "hourly",
        "tag_ids": [4, 5],
        "created_at": "2026-06-14T18:30:00",
        "start": "2026-06-14T00:00:00",
        "end": "2026-06-14T18:00:00",
    },
]


def test_reports_list_history_table():
    """list-history prints a table with id, date, tag count, interval, format."""
    mock_client = MagicMock()
    mock_client.list_report_history.return_value = _SAMPLE_HISTORY
    with patch("scada_reporter_cli.commands.reports.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.reports.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, ["reports", "list-history"])
    assert result.exit_code == 0
    assert "excel" in result.output
    assert "json" in result.output
    assert "3" in result.output  # id


def test_reports_list_history_empty():
    """list-history shows empty message when no history."""
    mock_client = MagicMock()
    mock_client.list_report_history.return_value = []
    with patch("scada_reporter_cli.commands.reports.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.reports.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, ["reports", "list-history"])
    assert result.exit_code == 0
    assert "rapor yok" in result.output.lower() or "yok" in result.output


def test_reports_list_history_json():
    """list-history --json-output returns raw JSON array."""
    import json
    mock_client = MagicMock()
    mock_client.list_report_history.return_value = _SAMPLE_HISTORY
    with patch("scada_reporter_cli.commands.reports.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.reports.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, ["reports", "list-history", "--json-output"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["id"] == 3


def test_reports_download_history_saves_file(tmp_path):
    """download-history writes bytes to file."""
    mock_client = MagicMock()
    mock_client.download_report_history.return_value = {
        "content": b"PK\x03\x04fake-xlsx",
        "filename": "report.xlsx",
    }
    out_file = str(tmp_path / "out.xlsx")
    with patch("scada_reporter_cli.commands.reports.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.reports.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, [
            "reports", "download-history", "3", "--output", out_file,
        ])
    assert result.exit_code == 0
    assert "indirildi" in result.output.lower() or out_file in result.output
    assert open(out_file, "rb").read() == b"PK\x03\x04fake-xlsx"
    mock_client.download_report_history.assert_called_once_with(3)
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_reports_list_history_table tests/test_cli.py::test_reports_list_history_empty tests/test_cli.py::test_reports_list_history_json tests/test_cli.py::test_reports_download_history_saves_file -v
```

Expected: `FAILED` — subcommands don't exist yet.

- [ ] **Step 3: Add `list-history` and `download-history` to reports.py**

Add to `src/scada_reporter_cli/commands/reports.py` after the `generate` command:

```python
@reports_cmd.command(name="list-history")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def list_history(json_output: bool):
    """Son 10 raporu listele."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.list_report_history()
    if isinstance(result, list) and result and isinstance(result[0], dict) and result[0].get("error"):
        click.echo(error(f"Hata: {result[0].get('detail', 'bilinmeyen hata')}"))
        client.close()
        return
    if json_output:
        click.echo(fmt_json(result))
    else:
        if not result:
            click.echo("(henüz rapor yok)")
        else:
            rows = [
                {
                    "id": r["id"],
                    "tarih": r["created_at"][:16].replace("T", " "),
                    "tag sayısı": len(r.get("tag_ids", [])),
                    "aralık": r["interval"],
                    "format": r["format"],
                }
                for r in result
            ]
            click.echo(fmt_table(rows, ["id", "tarih", "tag sayısı", "aralık", "format"]))
    client.close()


@reports_cmd.command(name="download-history")
@click.argument("history-id", type=int)
@click.option("--output", default=None, help="Çıktı dosyası (varsayılan: rapor adı sunucudan alınır)")
@click.option("--json-output", is_flag=True, help="JSON çıktı (meta bilgi)")
def download_history(history_id: int, output: str | None, json_output: bool):
    """Geçmiş raporu tekrar indir."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.download_report_history(history_id)
    if isinstance(result, dict) and result.get("error"):
        click.echo(error(f"İndirme hatası: {result.get('detail', 'bilinmeyen hata')}"))
        client.close()
        return
    content: bytes = result["content"]
    filename: str = output or result.get("filename", f"scada_rapor_{history_id}.bin")
    with open(filename, "wb") as f:
        f.write(content)
    if json_output:
        click.echo(fmt_json({"file": filename, "size": len(content), "history_id": history_id}))
    else:
        click.echo(success(f"Rapor indirildi: {filename} ({len(content):,} byte)"))
    client.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_reports_list_history_table tests/test_cli.py::test_reports_list_history_empty tests/test_cli.py::test_reports_list_history_json tests/test_cli.py::test_reports_download_history_saves_file -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
cd C:/project/smart
git add scada-reporter/agent-harness/src/scada_reporter_cli/commands/reports.py scada-reporter/agent-harness/tests/test_cli.py
git commit -m "feat: reports list-history and download-history commands"
```

---

## Task 5: `explore tags` command

**Files:**
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/explore.py`
- Modify: `scada-reporter/agent-harness/tests/test_cli.py`

This adds the `scada explore tags` command listed in TOOL.md but missing from implementation. It aggregates data from `list_tags()` — no new backend endpoint needed.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
_SAMPLE_TAGS = [
    {"id": 1, "name": "Hat1_Debi", "node_id": "DB171,REAL0", "unit": "m3/h",
     "device": "Hat1", "channel": "Ch1", "is_active": True, "min_alarm": None, "max_alarm": 3000.0},
    {"id": 2, "name": "Hat1_Basinc", "node_id": "DB172,REAL0", "unit": "bar",
     "device": "Hat1", "channel": "Ch1", "is_active": True, "min_alarm": 0.5, "max_alarm": 6.0},
    {"id": 3, "name": "Havuz_Seviye", "node_id": "DB180,REAL0", "unit": "mm",
     "device": "Havuz", "channel": "Ch2", "is_active": True, "min_alarm": None, "max_alarm": None},
]


def test_explore_tags_groups_by_device():
    """explore tags groups output by device."""
    mock_client = MagicMock()
    mock_client.list_tags.return_value = _SAMPLE_TAGS
    with patch("scada_reporter_cli.commands.explore.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.explore.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, ["explore", "tags"])
    assert result.exit_code == 0
    assert "Hat1" in result.output
    assert "Havuz" in result.output
    assert "Hat1_Debi" in result.output
    assert "Hat1_Basinc" in result.output
    assert "Havuz_Seviye" in result.output


def test_explore_tags_shows_alarm_info():
    """explore tags shows alarm threshold when set."""
    mock_client = MagicMock()
    mock_client.list_tags.return_value = _SAMPLE_TAGS
    with patch("scada_reporter_cli.commands.explore.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.explore.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, ["explore", "tags"])
    assert result.exit_code == 0
    # Hat1_Debi has max_alarm=3000 → should show alarm info
    assert "3000" in result.output


def test_explore_tags_json():
    """explore tags --json-output returns grouped structure."""
    import json
    mock_client = MagicMock()
    mock_client.list_tags.return_value = _SAMPLE_TAGS
    with patch("scada_reporter_cli.commands.explore.get_token", return_value="tok"), \
         patch("scada_reporter_cli.commands.explore.ScadaClient", return_value=mock_client):
        result = runner.invoke(cli, ["explore", "tags", "--json-output"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total"] == 3
    assert "by_device" in data
    assert "Hat1" in data["by_device"]
    assert len(data["by_device"]["Hat1"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_explore_tags_groups_by_device tests/test_cli.py::test_explore_tags_shows_alarm_info tests/test_cli.py::test_explore_tags_json -v
```

Expected: `FAILED` — `explore tags` subcommand doesn't exist.

- [ ] **Step 3: Read existing explore.py first**

```
cat scada-reporter/agent-harness/src/scada_reporter_cli/commands/explore.py
```

Understand the existing `schema` and `summary` command structure, then add `tags` after `summary`.

- [ ] **Step 4: Add `tags` command to explore.py**

Add after the `summary` command in `src/scada_reporter_cli/commands/explore.py`:

```python
@explore_cmd.command(name="tags")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def explore_tags(json_output: bool):
    """Tag kataloğu: cihaz grupları, birimler, alarm eşikleri."""
    from collections import defaultdict

    client, ok = _get_client()
    if not ok:
        return
    tags = client.list_tags()
    client.close()

    if isinstance(tags, list) and tags and "error" in tags[0]:
        click.echo(error(f"Hata: {tags[0].get('detail', 'bilinmeyen hata')}"))
        return

    if json_output:
        by_device: dict[str, list] = {}
        for t in tags:
            d = t.get("device") or "—"
            by_device.setdefault(d, []).append({
                "id": t["id"],
                "name": t["name"],
                "unit": t.get("unit", ""),
                "min_alarm": t.get("min_alarm"),
                "max_alarm": t.get("max_alarm"),
                "is_active": t.get("is_active", True),
            })
        click.echo(fmt_json({"total": len(tags), "by_device": by_device}))
        return

    grouped: dict[str, list] = defaultdict(list)
    for t in tags:
        grouped[t.get("device") or "—"].append(t)

    click.echo(f"Toplam {len(tags)} tag · {len(grouped)} cihaz\n")
    for device, dtags in sorted(grouped.items()):
        click.echo(info(f"▸ {device}  ({len(dtags)} tag)"))
        for t in dtags:
            alarm_parts: list[str] = []
            if t.get("min_alarm") is not None:
                alarm_parts.append(f"min={t['min_alarm']}")
            if t.get("max_alarm") is not None:
                alarm_parts.append(f"max={t['max_alarm']}")
            alarm_str = f"  ⚠ {', '.join(alarm_parts)}" if alarm_parts else ""
            status = "●" if t.get("is_active") else "○"
            unit_str = f" [{t['unit']}]" if t.get("unit") else ""
            click.echo(f"  {status} {t['name']}{unit_str}  (id:{t['id']}){alarm_str}")
    click.echo()
```

Also add the necessary imports at the top of explore.py if `info` is not already imported:

```python
from scada_reporter_cli.utils.repl_skin import error, info, fmt_json
```

(Check existing imports; the file may already import `info`. Only add what's missing.)

- [ ] **Step 5: Run tests to verify they pass**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/test_cli.py::test_explore_tags_groups_by_device tests/test_cli.py::test_explore_tags_shows_alarm_info tests/test_cli.py::test_explore_tags_json -v
```

Expected: `3 passed`

- [ ] **Step 6: Run full test suite**

```
cd scada-reporter/agent-harness
..\..\backend\.venv\Scripts\python -m pytest tests/ -v
```

Expected: all tests pass (original 9 + 13 new = 22 total).

- [ ] **Step 7: Commit**

```bash
cd C:/project/smart
git add scada-reporter/agent-harness/src/scada_reporter_cli/commands/explore.py scada-reporter/agent-harness/tests/test_cli.py
git commit -m "feat: explore tags command — grouped tag catalog with alarm thresholds"
```

---

## Task 6: SKILL.md + command docs + TOOL.md update

**Files:**
- Modify: `scada-reporter/agent-harness/skills/SKILL.md`
- Modify: `scada-reporter/commands/scada-tags.md`
- Modify: `scada-reporter/commands/scada-reports.md`
- Modify: `scada-reporter/commands/scada-dashboard.md`
- Modify: `TOOL.md`

No tests needed — documentation only.

- [ ] **Step 1: Update SKILL.md**

In `scada-reporter/agent-harness/skills/SKILL.md`, extend the `commands:` list:

```yaml
commands:
  # Auth
  - scada auth login <username>
  - scada auth me
  - scada auth register <username> <email>

  # Tags
  - scada tags list [--json]
  - scada tags create --node-id <id> --name <name> [--unit] [--device] [--channel]
  - scada tags update <id> [--unit] [--device] [--min-alarm N] [--max-alarm N] [--json]
  - scada tags delete <id>
  - scada tags readings <id> [--start ISO] [--end ISO] [--limit N] [--json]

  # Dashboard
  - scada dashboard overview [--json]
  - scada dashboard current-values [--alarm-only] [--watch N] [--json]
  - scada dashboard trend <tag_id> [...] [--hours N] [--json]

  # Reports
  - scada reports generate --tag-ids 1,2,3 --start ISO --end ISO [--interval hourly|daily] [--format json|excel]
  - scada reports list-history [--json]
  - scada reports download-history <id> [--output FILE] [--json]

  # Explore
  - scada explore schema [--json]
  - scada explore summary [--json]
  - scada explore tags [--json]

  # Query / Shell
  - scada query run "SELECT ..." [--limit N] [--json]
  - scada shell

  # Health
  - scada health [--json]
```

Also add notes section explaining alarm_state values:

```yaml
alarm_state_values:
  overflow: "Değer > 1_000_000 veya kalite kötü (PLC bağlantı sorunu)"
  max: "Değer tag'in max_alarm eşiğini aştı"
  min: "Değer tag'in min_alarm eşiğinin altına düştü"
  null: "Normal — alarm yok"
```

- [ ] **Step 2: Update scada-tags.md**

In `scada-reporter/commands/scada-tags.md`, add after the `delete` section:

```markdown
## `scada tags update`

Tag'in birini, cihazını veya alarm eşiklerini güncelle.

```bash
# Birimi değiştir
scada tags update 7 --unit "bar"

# Alarm eşiklerini ayarla (min < max zorunlu)
scada tags update 7 --min-alarm 0.5 --max-alarm 6.0

# Birden fazla alan birden
scada tags update 7 --unit "m3/h" --device "Hat2" --max-alarm 3000

# JSON çıktı (tam güncel tag nesnesi)
scada tags update 7 --min-alarm 0 --max-alarm 5000 --json
```

Doğrulama: `--min-alarm >= --max-alarm` ise istek gönderilmez, hata mesajı gösterilir.
```

- [ ] **Step 3: Update scada-reports.md**

In `scada-reporter/commands/scada-reports.md`, add after the `generate` section:

```markdown
## `scada reports list-history`

Son 10 raporu listele (en yenisi üstte).

```bash
scada reports list-history
# id  tarih             tag sayısı  aralık  format
#  3  2026-06-15 22:07           6  hourly  excel
#  2  2026-06-14 18:30           5  hourly  json

scada reports list-history --json
```

## `scada reports download-history`

Önceki raporu tekrar indir (yeniden oluşturmaz, diske kayıtlı dosyayı getirir).

```bash
scada reports download-history 3
# ✓ Rapor indirildi: report.xlsx (45,312 byte)

scada reports download-history 3 --output /tmp/myreport.xlsx
```
```

- [ ] **Step 4: Update scada-dashboard.md**

In `scada-reporter/commands/scada-dashboard.md`, update the `current-values` section:

```markdown
## `scada dashboard current-values`

Tüm tag'lerin son değerlerini göster. Alarm durumu `alarm` sütununda:
- `OVERFLOW` — değer > 1_000_000 veya kalite kötü
- `MAX AŞIMI` — değer max_alarm eşiğini geçti
- `MIN ALTI` — değer min_alarm eşiğinin altına düştü

```bash
# Tümünü göster (alarm sütunlu)
scada dashboard current-values

# Sadece alarm durumundaki tag'ler
scada dashboard current-values --alarm-only

# Canlı izleme — her 5 saniyede yenile, Ctrl+C ile durdur
scada dashboard current-values --watch 5

# Alarm izleme döngüsü
scada dashboard current-values --alarm-only --watch 10

# Agent kullanımı: overflow olan tag'ler
scada dashboard current-values --json | jq '[.[] | select(.alarm_state == "overflow")]'
```
```

- [ ] **Step 5: Update TOOL.md Project CLI table**

In `TOOL.md`, replace the Project CLI table with:

```markdown
## Project CLI (`scada`)
| Command | Description |
|---------|-------------|
| `scada auth login` | JWT login |
| `scada tags list` | List tags |
| `scada tags update <id>` | Update tag (unit, device, alarm thresholds) |
| `scada tags readings` | Tag readings |
| `scada dashboard overview` | System overview |
| `scada dashboard current-values` | Live values with alarm_state (`--alarm-only`, `--watch N`) |
| `scada dashboard trend <tag_ids>` | Trend series |
| `scada reports generate` | Generate report (Excel/JSON) |
| `scada reports list-history` | List last 10 saved reports |
| `scada reports download-history <id>` | Re-download saved report |
| `scada query run <sql>` | Read-only SQL execution |
| `scada explore schema` | DB schema discovery |
| `scada explore summary` | System stats |
| `scada explore tags` | Tag catalog (grouped by device, alarm thresholds) |
| `scada shell` | Python REPL with data context |
| `scada health` | Backend health check |
```

- [ ] **Step 6: Commit**

```bash
cd C:/project/smart
git add scada-reporter/agent-harness/skills/SKILL.md scada-reporter/commands/ TOOL.md
git commit -m "docs: update SKILL.md, command refs, TOOL.md with new CLI commands"
```

---

## Self-Review

**Spec coverage:**
- ✅ `PATCH /api/tags/{id}` → `tags update` (Task 2)
- ✅ `alarm_state` in current-values response → `alarm` column + `--alarm-only` (Task 3)
- ✅ `--watch N` live mode (Task 3)
- ✅ `GET /api/reports/history` → `reports list-history` (Task 4)
- ✅ `GET /api/reports/history/{id}/download` → `reports download-history` (Task 4)
- ✅ `scada explore tags` missing from TOOL.md → implemented (Task 5)
- ✅ SKILL.md stale → updated (Task 6)
- ✅ TOOL.md stale → updated (Task 6)

**Placeholder scan:** None found.

**Type consistency:**
- `client.download_report_history()` returns `dict[str, Any]` with keys `content: bytes` and `filename: str` — consistent across Task 1 client method and Task 4 command usage. ✅
- `client.update_tag()` signature in Task 1 matches keyword args used in Task 2 command. ✅
- `_SAMPLE_VALUES[*]["alarm_state"]` in Task 3 tests matches the field name used in Task 3 command code. ✅
