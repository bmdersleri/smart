import json
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from scada_reporter_cli.cli import cli

runner = CliRunner()


def test_template_create_passes_payload():
    mc = MagicMock()
    mc.template_create.return_value = {"id": 1}
    with patch(
        "scada_reporter_cli.commands.templates.get_client", return_value=(mc, True)
    ):
        result = runner.invoke(
            cli,
            [
                "templates",
                "create",
                "--payload",
                json.dumps({"name": "T", "tag_ids": [1]}),
            ],
        )
    assert result.exit_code == 0
    mc.template_create.assert_called_once()


def test_template_delete_blocked_without_confirm():
    mc = MagicMock()
    with patch(
        "scada_reporter_cli.commands.templates.get_client", return_value=(mc, True)
    ):
        result = runner.invoke(cli, ["templates", "delete", "9"])
    assert result.exit_code == 2
    mc.template_delete.assert_not_called()
    assert "re-run with --confirm" in result.output


def test_template_delete_runs_with_confirm():
    mc = MagicMock()
    mc.template_delete.return_value = {"ok": True}
    with patch(
        "scada_reporter_cli.commands.templates.get_client", return_value=(mc, True)
    ):
        result = runner.invoke(cli, ["templates", "delete", "9", "--confirm"])
    assert result.exit_code == 0
    mc.template_delete.assert_called_once_with(9)


def test_group_delete_blocked_without_confirm():
    mc = MagicMock()
    with patch(
        "scada_reporter_cli.commands.groups.get_client", return_value=(mc, True)
    ):
        result = runner.invoke(cli, ["groups", "delete", "3"])
    assert result.exit_code == 2
    mc.group_delete.assert_not_called()
