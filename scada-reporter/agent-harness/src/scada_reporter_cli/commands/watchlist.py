import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap


@click.group(name="watchlist")
def watchlist_cmd():
    """İzleme listesi yönetimi."""


@watchlist_cmd.command()
@click.argument("tag_id", type=int)
def add(tag_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.watchlist_add(tag_id)), default=str, ensure_ascii=False
        )
    )


@watchlist_cmd.command()
@click.argument("tag_id", type=int)
def remove(tag_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.watchlist_remove(tag_id)), default=str, ensure_ascii=False
        )
    )
