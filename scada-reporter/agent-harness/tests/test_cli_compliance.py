import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from scada_reporter_cli.cli import cli

runner = CliRunner()


def test_compliance_group_help():
    result = runner.invoke(cli, ["compliance", "--help"])
    assert result.exit_code == 0
    assert "overview" in result.output
    assert "events" in result.output
    assert "evaluate" in result.output


def test_compliance_overview_json_output():
    mc = MagicMock()
    mc.compliance_overview.return_value = {"permits": 2, "open_events": 5}
    with patch(
        "scada_reporter_cli.commands.compliance.get_client",
        return_value=(mc, True),
    ):
        result = runner.invoke(cli, ["compliance", "overview", "--json-output"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["permits"] == 2
    assert data["open_events"] == 5
    mc.compliance_overview.assert_called_once_with()


def test_compliance_events_passes_filters():
    mc = MagicMock()
    mc.compliance_events.return_value = {"total": 0, "items": []}
    with patch(
        "scada_reporter_cli.commands.compliance.get_client",
        return_value=(mc, True),
    ):
        result = runner.invoke(
            cli,
            [
                "compliance",
                "events",
                "--permit-id",
                "3",
                "--start",
                "2026-05-01T00:00:00",
                "--end",
                "2026-06-01T00:00:00",
                "--status",
                "open",
                "--json-output",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total"] == 0
    mc.compliance_events.assert_called_once_with(
        permit_id=3,
        start="2026-05-01T00:00:00",
        end="2026-06-01T00:00:00",
        status="open",
    )


def test_compliance_evaluate_calls_client():
    mc = MagicMock()
    mc.compliance_evaluate.return_value = {"created": 1, "updated": 0}
    with patch(
        "scada_reporter_cli.commands.compliance.get_client",
        return_value=(mc, True),
    ):
        result = runner.invoke(
            cli,
            [
                "compliance",
                "evaluate",
                "--permit-id",
                "7",
                "--start",
                "2026-05-01T00:00:00",
                "--end",
                "2026-06-01T00:00:00",
                "--json-output",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["created"] == 1
    mc.compliance_evaluate.assert_called_once_with(
        7, "2026-05-01T00:00:00", "2026-06-01T00:00:00"
    )
