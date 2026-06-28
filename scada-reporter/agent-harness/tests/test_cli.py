from __future__ import annotations

import os
import pytest
from click.testing import CliRunner
from scada_reporter_cli.cli import cli
from unittest.mock import MagicMock, patch

runner = CliRunner()


def _clear_token():
    os.environ.pop("SCADA_TOKEN", None)


def test_health_no_api():
    """Health API'ye ulasamazsa hata mesaji donmeli."""
    result = runner.invoke(cli, ["health"])
    assert result.exit_code in (0, 1)
    assert "API" in result.output or "saglik" in result.output.lower()


def test_doctor_json_output_with_token():
    """doctor JSON, health/readiness/auth özetini tek yerde toplamalı."""
    import json

    mock_client = MagicMock()
    mock_client.health.return_value = {
        "status": "ok",
        "collector_running": True,
        "scheduler_running": False,
    }
    mock_client.ready.return_value = {
        "status": "ready",
        "checks": {"db": True, "alembic_head": True, "scheduler": "disabled"},
    }
    mock_client.system_health.return_value = {
        "health": {"status": "ok"},
        "plc_count": 2,
        "tag_count": 7,
    }
    mock_client.me.return_value = {"username": "admin", "role": "admin"}

    with (
        patch.dict(os.environ, {"SCADA_TOKEN": "token-from-env"}, clear=False),
        patch(
            "scada_reporter_cli.commands.doctor.SyncScadaClient",
            return_value=mock_client,
        ),
    ):
        result = runner.invoke(cli, ["doctor", "--json-output"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert data["token"] == {"present": True, "source": "env"}
    assert data["health"]["status"] == "ok"
    assert data["ready"]["status"] == "ready"
    assert data["system"]["plc_count"] == 2
    assert data["auth"]["username"] == "admin"
    mock_client.me.assert_called_once()


def test_doctor_without_token_reports_warning():
    """doctor token yokken de faydalı bir triage vermeli."""
    import json

    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "ok"}
    mock_client.ready.return_value = {"status": "ready", "checks": {}}
    mock_client.system_health.return_value = {"plc_count": 0, "tag_count": 0}

    with (
        patch.dict(os.environ, {}, clear=True),
        patch(
            "scada_reporter_cli.commands.doctor.SyncScadaClient",
            return_value=mock_client,
        ),
        patch(
            "scada_reporter_cli.commands.doctor.token_with_source",
            return_value=(None, "missing"),
        ),
    ):
        result = runner.invoke(cli, ["doctor", "--json-output"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "warning"
    assert data["token"] == {"present": False, "source": "missing"}
    assert data["issues"][0]["kind"] == "auth"
    mock_client.me.assert_not_called()


def test_agent_capabilities_json_output():
    import json

    result = runner.invoke(cli, ["agent", "capabilities", "--json-output"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "1.0"
    assert data["counts"]["total"] == len(data["capabilities"])
    assert any(cap["name"] == "list_tags" for cap in data["capabilities"])


def test_agent_contract_json_output():
    import json

    result = runner.invoke(cli, ["agent", "contract", "--json-output"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["project"] == "ekont-smart-report"
    assert "scada://agent/contract" in data["mcp"]["resources"]
    assert "scada agent bootstrap --json-output" in data["cli"]["recommended_start"]


def test_agent_bootstrap_json_output_without_token():
    import json

    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "ok"}
    mock_client.ready.return_value = {"status": "ready", "checks": {}}
    mock_client.system_health.return_value = {"tag_count": 3, "plc_count": 1}

    with (
        patch.dict(os.environ, {}, clear=True),
        patch(
            "scada_reporter_cli.commands.agent.SyncScadaClient",
            return_value=mock_client,
        ),
        patch(
            "scada_reporter_cli.commands.agent.token_with_source",
            return_value=(None, "missing"),
        ),
    ):
        result = runner.invoke(cli, ["agent", "bootstrap", "--json-output"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "warning"
    assert data["token"] == {"present": False, "source": "missing"}
    assert data["health"]["status"] == "ok"
    assert data["ready"]["status"] == "ready"
    assert data["system"]["tag_count"] == 3


def test_list_tags_no_auth():
    """Token olmadan tags list auth hatasi vermeli."""
    _clear_token()
    with patch("scada_reporter_cli.utils.client_helper.get_token", return_value=None):
        result = runner.invoke(cli, ["tags", "list"])
    assert result.exit_code == 0
    assert "login" in result.output.lower()


def test_dashboard_overview_no_auth():
    """Token olmadan dashboard overview auth hatasi vermeli."""
    _clear_token()
    with patch("scada_reporter_cli.utils.client_helper.get_token", return_value=None):
        result = runner.invoke(cli, ["dashboard", "overview"])
    assert result.exit_code == 0
    assert "login" in result.output.lower()


def test_repl_help():
    """REPL modunda help komutu calismali."""
    result = runner.invoke(cli, [], input="help\nexit\n")
    assert result.exit_code == 0
    assert "Komutlar" in result.output or "auth login" in result.output


def test_cli_invocation():
    """CLI --help calismali."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "EKONT SMART REPORT" in result.output


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
    "cmd", ["auth", "tags", "dashboard", "reports", "query", "explore", "doctor"]
)
def test_group_help(cmd: str):
    """Her komut grubu --help calistirabilmeli."""
    result = runner.invoke(cli, [cmd, "--help"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_tags_update_success():
    """tags update calls update_tag and prints confirmation."""
    mock_client = MagicMock()
    mock_client.update_tag.return_value = {
        "id": 1,
        "node_id": "DB1,REAL0",
        "name": "Test",
        "unit": "bar",
        "device": "PLC",
        "channel": "Ch1",
        "is_active": True,
        "min_alarm": 0.0,
        "max_alarm": 5000.0,
    }
    with patch(
        "scada_reporter_cli.commands.tags.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(
            cli,
            [
                "tags",
                "update",
                "1",
                "--unit",
                "bar",
                "--min-alarm",
                "0",
                "--max-alarm",
                "5000",
            ],
        )
    assert result.exit_code == 0
    assert "Tag 1 güncellendi" in result.output
    mock_client.update_tag.assert_called_once_with(
        1,
        unit="bar",
        device=None,
        channel=None,
        description=None,
        min_alarm=0.0,
        max_alarm=5000.0,
    )


def test_tags_update_validation_error():
    """tags update blocks min >= max without hitting the API."""
    mock_client = MagicMock()
    with patch(
        "scada_reporter_cli.commands.tags.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(
            cli,
            [
                "tags",
                "update",
                "1",
                "--min-alarm",
                "5000",
                "--max-alarm",
                "0",
            ],
        )
    assert result.exit_code == 0
    assert "min" in result.output.lower() or "küçük" in result.output.lower()
    mock_client.update_tag.assert_not_called()


def test_tags_update_json_output():
    """tags update --json-output prints the full tag JSON."""
    import json

    mock_client = MagicMock()
    mock_client.update_tag.return_value = {
        "id": 2,
        "node_id": "DB2,REAL0",
        "name": "Hat2",
        "unit": "m3/h",
        "device": "Hat2",
        "channel": "Ch1",
        "is_active": True,
        "min_alarm": None,
        "max_alarm": None,
    }
    with patch(
        "scada_reporter_cli.commands.tags.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(
            cli,
            [
                "tags",
                "update",
                "2",
                "--unit",
                "m3/h",
                "--json-output",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == 2
    assert data["unit"] == "m3/h"


_SAMPLE_VALUES = [
    {
        "tag_id": 1,
        "name": "Hat1_Debi",
        "device": "Hat1",
        "unit": "m3/h",
        "value": 3500.0,
        "timestamp": "2026-06-15T22:00:00",
        "quality_ok": True,
        "alarm_state": "max",
    },
    {
        "tag_id": 2,
        "name": "Havuz_Seviye",
        "device": "Havuz",
        "unit": "mm",
        "value": 1027604480.0,
        "timestamp": "2026-06-15T22:00:00",
        "quality_ok": False,
        "alarm_state": "overflow",
    },
    {
        "tag_id": 3,
        "name": "Hat2_Debi",
        "device": "Hat2",
        "unit": "m3/h",
        "value": 1200.0,
        "timestamp": "2026-06-15T22:00:00",
        "quality_ok": True,
        "alarm_state": None,
    },
]


def test_current_values_shows_alarm_column():
    """current-values table includes alarm_state column."""
    mock_client = MagicMock()
    mock_client.current_values.return_value = _SAMPLE_VALUES
    with patch(
        "scada_reporter_cli.commands.dashboard.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(cli, ["dashboard", "current-values"])
    assert result.exit_code == 0
    assert "alarm" in result.output.lower()
    assert "MAX" in result.output or "OVERFLOW" in result.output


def test_current_values_alarm_only_filter():
    """--alarm-only shows only rows with alarm_state != None."""
    mock_client = MagicMock()
    mock_client.current_values.return_value = _SAMPLE_VALUES
    with patch(
        "scada_reporter_cli.commands.dashboard.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(cli, ["dashboard", "current-values", "--alarm-only"])
    assert result.exit_code == 0
    assert "Hat2_Debi" not in result.output  # no alarm, should be filtered out
    assert "Hat1_Debi" in result.output or "Havuz_Seviye" in result.output


def test_current_values_json_includes_alarm_state():
    """--json-output includes alarm_state field."""
    import json

    mock_client = MagicMock()
    mock_client.current_values.return_value = _SAMPLE_VALUES
    with patch(
        "scada_reporter_cli.commands.dashboard.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(cli, ["dashboard", "current-values", "--json-output"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert any("alarm_state" in item for item in data)
    overflow_items = [i for i in data if i["alarm_state"] == "overflow"]
    assert len(overflow_items) == 1


_SAMPLE_HISTORY = [
    {
        "id": 3,
        "format": "excel",
        "interval": "daily",
        "tag_ids": [1, 2, 3],
        "created_at": "2026-06-15T22:07:00",
        "start": "2026-06-08T00:00:00",
        "end": "2026-06-15T22:00:00",
    },
    {
        "id": 2,
        "format": "json",
        "interval": "hourly",
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
    with patch(
        "scada_reporter_cli.commands.reports.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(cli, ["reports", "list-history"])
    assert result.exit_code == 0
    assert "excel" in result.output
    assert "json" in result.output
    assert "3" in result.output  # id


def test_reports_list_history_empty():
    """list-history shows empty message when no history."""
    mock_client = MagicMock()
    mock_client.list_report_history.return_value = []
    with patch(
        "scada_reporter_cli.commands.reports.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(cli, ["reports", "list-history"])
    assert result.exit_code == 0
    assert "rapor yok" in result.output.lower() or "yok" in result.output


def test_reports_list_history_json():
    """list-history --json-output returns raw JSON array."""
    import json

    mock_client = MagicMock()
    mock_client.list_report_history.return_value = _SAMPLE_HISTORY
    with patch(
        "scada_reporter_cli.commands.reports.get_client",
        return_value=(mock_client, True),
    ):
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
    with patch(
        "scada_reporter_cli.commands.reports.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(
            cli,
            [
                "reports",
                "download-history",
                "3",
                "--output",
                out_file,
            ],
        )
    assert result.exit_code == 0
    assert "indirildi" in result.output.lower() or out_file in result.output
    with open(out_file, "rb") as f:
        assert f.read() == b"PK\x03\x04fake-xlsx"
    mock_client.download_report_history.assert_called_once_with(3)


_SAMPLE_TAGS_FOR_EXPLORE = [
    {
        "id": 1,
        "name": "Hat1_Debi",
        "node_id": "DB171,REAL0",
        "unit": "m3/h",
        "device": "Hat1",
        "channel": "Ch1",
        "is_active": True,
        "min_alarm": None,
        "max_alarm": 3000.0,
    },
    {
        "id": 2,
        "name": "Hat1_Basinc",
        "node_id": "DB172,REAL0",
        "unit": "bar",
        "device": "Hat1",
        "channel": "Ch1",
        "is_active": True,
        "min_alarm": 0.5,
        "max_alarm": 6.0,
    },
    {
        "id": 3,
        "name": "Havuz_Seviye",
        "node_id": "DB180,REAL0",
        "unit": "mm",
        "device": "Havuz",
        "channel": "Ch2",
        "is_active": True,
        "min_alarm": None,
        "max_alarm": None,
    },
]


def test_explore_tags_groups_by_device():
    """explore tags groups output by device."""
    mock_client = MagicMock()
    mock_client.list_tags.return_value = _SAMPLE_TAGS_FOR_EXPLORE
    with patch(
        "scada_reporter_cli.commands.explore.get_client",
        return_value=(mock_client, True),
    ):
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
    mock_client.list_tags.return_value = _SAMPLE_TAGS_FOR_EXPLORE
    with patch(
        "scada_reporter_cli.commands.explore.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(cli, ["explore", "tags"])
    assert result.exit_code == 0
    # Hat1_Debi has max_alarm=3000 → should show alarm info
    assert "3000" in result.output


def test_explore_tags_json():
    """explore tags --json-output returns grouped structure."""
    import json

    mock_client = MagicMock()
    mock_client.list_tags.return_value = _SAMPLE_TAGS_FOR_EXPLORE
    with patch(
        "scada_reporter_cli.commands.explore.get_client",
        return_value=(mock_client, True),
    ):
        result = runner.invoke(cli, ["explore", "tags", "--json-output"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total"] == 3
    assert "by_device" in data
    assert "Hat1" in data["by_device"]
    assert len(data["by_device"]["Hat1"]) == 2
