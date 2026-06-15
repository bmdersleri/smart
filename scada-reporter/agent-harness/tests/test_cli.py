from __future__ import annotations

import os
import pytest
from click.testing import CliRunner
from scada_reporter_cli.cli import cli


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
