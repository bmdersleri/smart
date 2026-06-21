import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="scheduled")
def scheduled_cmd():
    """Zamanlanmış rapor yönetimi."""


@scheduled_cmd.command()
@click.option("--payload", required=True, help="JSON zamanlanmış gövdesi")
def create(payload):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.scheduled_create(json.loads(payload))),
            default=str,
            ensure_ascii=False,
        )
    )


@scheduled_cmd.command()
@click.argument("scheduled_id", type=int)
@click.option("--payload", required=True)
def update(scheduled_id, payload):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.scheduled_update(scheduled_id, json.loads(payload))),
            default=str,
            ensure_ascii=False,
        )
    )


@scheduled_cmd.command()
@click.argument("scheduled_id", type=int)
def toggle(scheduled_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.scheduled_toggle(scheduled_id)),
            default=str,
            ensure_ascii=False,
        )
    )


@scheduled_cmd.command()
@click.argument("scheduled_id", type=int)
@click.option("--confirm", is_flag=True, default=False)
def delete(scheduled_id, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "scheduled_delete", scheduled_id)
    click.echo(
        json.dumps(
            unwrap(client.scheduled_delete(scheduled_id)),
            default=str,
            ensure_ascii=False,
        )
    )
