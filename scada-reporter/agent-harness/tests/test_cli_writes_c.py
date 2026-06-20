from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from scada_reporter_cli.cli import cli

runner = CliRunner()


def test_plc_create_calls_client():
    mc = MagicMock()
    mc.plc_create.return_value = {"name": "PLC1"}
    with patch("scada_reporter_cli.commands.plc.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["plc", "create", "PLC1", "--ip", "10.0.0.1"])
    assert result.exit_code == 0
    mc.plc_create.assert_called_once()


def test_plc_delete_requires_confirm():
    mc = MagicMock()
    with patch("scada_reporter_cli.commands.plc.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["plc", "delete", "PLC1"])
    assert result.exit_code == 2
    mc.plc_delete.assert_not_called()


def test_user_delete_runs_with_confirm():
    mc = MagicMock()
    mc.user_delete.return_value = {"ok": True}
    with patch("scada_reporter_cli.commands.users.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["users", "delete", "2", "--confirm"])
    assert result.exit_code == 0
    mc.user_delete.assert_called_once_with(2)


def test_user_create_requires_confirm():
    mc = MagicMock()
    with patch("scada_reporter_cli.commands.users.get_client", return_value=(mc, True)):
        result = runner.invoke(
            cli,
            ["users", "create", "u1", "--email", "u1@x.com", "--password", "secret6"],
        )
    assert result.exit_code == 2
    mc.user_create.assert_not_called()


def test_user_update_requires_confirm():
    mc = MagicMock()
    with patch("scada_reporter_cli.commands.users.get_client", return_value=(mc, True)):
        result = runner.invoke(cli, ["users", "update", "2", "--role", "admin"])
    assert result.exit_code == 2
    mc.user_update.assert_not_called()


def test_user_set_password_requires_confirm():
    mc = MagicMock()
    with patch("scada_reporter_cli.commands.users.get_client", return_value=(mc, True)):
        result = runner.invoke(
            cli, ["users", "set-password", "2", "--password", "newpass"]
        )
    assert result.exit_code == 2
    mc.user_set_password.assert_not_called()
