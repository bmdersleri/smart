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
    assert "ask" in result.output
    assert "note" in result.output
    assert "status" in result.output
    assert "report-pack" in result.output


def test_compliance_ask_json_output():
    mc = MagicMock()
    mc.compliance_assistant.return_value = {
        "intent": "breaches",
        "answer": "Found 1 limit-exceeded event(s).",
        "links": [{"type": "event", "id": 1}],
    }
    with patch(
        "scada_reporter_cli.commands.compliance.get_client",
        return_value=(mc, True),
    ):
        result = runner.invoke(
            cli,
            [
                "compliance",
                "ask",
                "Which limits were exceeded?",
                "--permit-id",
                "3",
                "--start",
                "2026-05-01T00:00:00",
                "--end",
                "2026-06-01T00:00:00",
                "--json-output",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["intent"] == "breaches"
    mc.compliance_assistant.assert_called_once_with(
        "Which limits were exceeded?",
        permit_id=3,
        start="2026-05-01T00:00:00",
        end="2026-06-01T00:00:00",
    )


def test_compliance_note_add_calls_client():
    mc = MagicMock()
    mc.compliance_add_note.return_value = {"id": 1, "event_id": 5, "note": "x"}
    with patch(
        "scada_reporter_cli.commands.compliance.get_client",
        return_value=(mc, True),
    ):
        result = runner.invoke(
            cli,
            ["compliance", "note", "add", "5", "Operator note.", "--json-output"],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["event_id"] == 5
    mc.compliance_add_note.assert_called_once_with(5, "Operator note.")


def test_compliance_status_set_calls_client():
    mc = MagicMock()
    mc.compliance_set_status.return_value = {"id": 5, "status": "waived"}
    with patch(
        "scada_reporter_cli.commands.compliance.get_client",
        return_value=(mc, True),
    ):
        result = runner.invoke(
            cli,
            [
                "compliance",
                "status",
                "set",
                "5",
                "waived",
                "--reason",
                "Documented exception.",
                "--json-output",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "waived"
    mc.compliance_set_status.assert_called_once_with(
        5, "waived", reason="Documented exception."
    )


def test_compliance_report_pack_create_calls_client():
    mc = MagicMock()
    mc.compliance_create_report_pack.return_value = {"id": 9, "status": "draft"}
    with patch(
        "scada_reporter_cli.commands.compliance.get_client",
        return_value=(mc, True),
    ):
        result = runner.invoke(
            cli,
            [
                "compliance",
                "report-pack",
                "create",
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
    assert data["id"] == 9
    mc.compliance_create_report_pack.assert_called_once_with(
        7, "2026-05-01T00:00:00", "2026-06-01T00:00:00"
    )


def test_compliance_report_pack_approve_calls_client():
    mc = MagicMock()
    mc.compliance_approve_report_pack.return_value = {"id": 9, "status": "approved"}
    with patch(
        "scada_reporter_cli.commands.compliance.get_client",
        return_value=(mc, True),
    ):
        result = runner.invoke(
            cli,
            ["compliance", "report-pack", "approve", "9", "--json-output"],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "approved"
    mc.compliance_approve_report_pack.assert_called_once_with(9)


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
