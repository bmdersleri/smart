from __future__ import annotations

import click
from scada_core.client import SyncScadaClient
from scada_reporter_cli.utils.config import get_api_url, get_token
from scada_reporter_cli.utils.repl_skin import error


def get_client() -> tuple[SyncScadaClient | None, bool]:
    token = get_token()
    if not token:
        click.echo(error("Once `scada auth login` ile giris yapin"))
        return None, False
    client = SyncScadaClient(get_api_url())
    client.set_token(token)
    return client, True


def unwrap(value):
    """scada_core.Result -> legacy CLI shape; pass through plain values (test mocks)."""
    legacy = getattr(value, "legacy", None)
    return legacy() if callable(legacy) else value
