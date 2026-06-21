from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from scada_reporter_cli.cli import cli

runner = CliRunner()


def _mock_client():
    mc = MagicMock()
    return mc


def test_watchlist_add_calls_client():
    mc = _mock_client()
    mc.watchlist_add.return_value = {"ok": True}
    with patch(
        "scada_reporter_cli.commands.watchlist.get_client", return_value=(mc, True)
    ):
        result = runner.invoke(cli, ["watchlist", "add", "5"])
    assert result.exit_code == 0
    mc.watchlist_add.assert_called_once_with(5)


def test_annotation_delete_requires_confirm():
    mc = _mock_client()
    with patch(
        "scada_reporter_cli.commands.annotations.get_client", return_value=(mc, True)
    ):
        result = runner.invoke(cli, ["annotations", "delete", "9"])
    # annotation_delete is write-tier (not destructive) -> no confirm needed
    assert result.exit_code == 0
    mc.annotation_delete.assert_called_once_with(9)
