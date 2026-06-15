from __future__ import annotations

import os
import pytest
from click.testing import CliRunner
from scada_reporter_cli.cli import cli
from unittest.mock import MagicMock
from scada_reporter_cli.client import ScadaClient


runner = CliRunner()


def _clear_token():
    os.environ.pop("SCADA_TOKEN", None)


def test_health_no_api():
    """Health API'ye ulasamazsa hata mesaji donmeli."""
    result = runner.invoke(cli, ["health"])
    assert result.exit_code in (0, 1)
    assert "API" in result.output or "saglik" in result.output.lower()


def test_list_tags_no_auth():
    """Token olmadan tags list calismali (token varsa da calisir)."""
    result = runner.invoke(cli, ["tags", "list"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_dashboard_overview_no_auth():
    """Token olmadan dashboard overview calismali."""
    result = runner.invoke(cli, ["dashboard", "overview"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_repl_help():
    """REPL modunda help komutu calismali."""
    result = runner.invoke(cli, [], input="help\nexit\n")
    assert result.exit_code == 0
    assert "Komutlar" in result.output or "auth login" in result.output


def test_cli_invocation():
    """CLI --help calismali."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "SCADA Reporter" in result.output


def test_repl_exit():
    """REPL'den exit ile cikilabilmeli."""
    result = runner.invoke(cli, [], input="exit\n")
    assert result.exit_code == 0


def test_repl_quit():
    """REPL'den quit ile cikilabilmeli."""
    result = runner.invoke(cli, [], input="quit\n")
    assert result.exit_code == 0


def test_repl_invalid_command():
    """REPL'de gecersiz komut hata vermemeli."""
    result = runner.invoke(cli, [], input="nonexistent-cmd\nexit\n")
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "cmd", ["auth", "tags", "dashboard", "reports", "query", "explore"]
)
def test_group_help(cmd: str):
    """Her komut grubu --help calistirabilmeli."""
    result = runner.invoke(cli, [cmd, "--help"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_client_update_tag():
    """update_tag sends PATCH /api/tags/{id} with the right payload."""
    sc = ScadaClient("http://testserver")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 7,
        "node_id": "DB1,REAL0",
        "name": "Test",
        "unit": "bar",
        "device": "PLC",
        "channel": "Ch1",
        "is_active": True,
        "min_alarm": 0.0,
        "max_alarm": 5000.0,
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

    result = sc.update_tag(999, unit="m3/h")

    assert result["error"] is True
    assert result["status"] == 404


def test_client_update_tag_empty_payload():
    """update_tag raises ValueError when no fields are provided."""
    sc = ScadaClient("http://testserver")

    with pytest.raises(ValueError, match="at least one field"):
        sc.update_tag(1)


def test_client_list_report_history():
    """list_report_history returns list of history records."""
    sc = ScadaClient("http://testserver")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": 1,
            "format": "json",
            "interval": "hourly",
            "tag_ids": [1, 2],
            "created_at": "2026-06-15T22:00:00",
            "start": "2026-06-15T00:00:00",
            "end": "2026-06-15T22:00:00",
        }
    ]
    sc._client.get = MagicMock(return_value=mock_resp)

    result = sc.list_report_history()

    assert len(result) == 1
    assert result[0]["format"] == "json"
    assert "api/reports/history" in sc._client.get.call_args[0][0]


def test_client_list_report_history_error():
    """list_report_history returns error list on non-200."""
    sc = ScadaClient("http://testserver")
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    sc._client.get = MagicMock(return_value=mock_resp)

    result = sc.list_report_history()

    assert isinstance(result, list)
    assert result[0]["error"] is True
    assert result[0]["status"] == 401


def test_client_download_report_history_no_cd_header():
    """download_report_history uses fallback filename when no Content-Disposition."""
    sc = ScadaClient("http://testserver")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"data"
    mock_resp.headers = {}  # no content-disposition
    sc._client.get = MagicMock(return_value=mock_resp)

    result = sc.download_report_history(5)

    assert result["content"] == b"data"
    assert result["filename"] == "scada_rapor_5.bin"


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
