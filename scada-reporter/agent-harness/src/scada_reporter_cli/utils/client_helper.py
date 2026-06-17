from __future__ import annotations

import click
from scada_reporter_cli.client import ScadaClient
from scada_reporter_cli.utils.config import get_api_url, get_token
from scada_reporter_cli.utils.repl_skin import error


def get_client() -> tuple[ScadaClient, bool]:
    token = get_token()
    if not token:
        click.echo(error("Once `scada auth login` ile giris yapin"))
        return None, False
    client = ScadaClient(get_api_url())
    client.set_token(token)
    return client, True
