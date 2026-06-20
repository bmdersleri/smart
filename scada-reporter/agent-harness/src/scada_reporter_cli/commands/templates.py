import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="templates")
def templates_cmd():
    """Rapor şablonu yönetimi."""


@templates_cmd.command()
@click.option("--payload", required=True, help="JSON şablon gövdesi")
def create(payload):
    client, ok = get_client()
    if not ok:
        return
    body = json.loads(payload)
    click.echo(
        json.dumps(
            unwrap(client.template_create(body)), default=str, ensure_ascii=False
        )
    )


@templates_cmd.command()
@click.argument("template_id", type=int)
@click.option("--payload", required=True, help="JSON güncelleme gövdesi")
def update(template_id, payload):
    client, ok = get_client()
    if not ok:
        return
    body = json.loads(payload)
    click.echo(
        json.dumps(
            unwrap(client.template_update(template_id, body)),
            default=str,
            ensure_ascii=False,
        )
    )


@templates_cmd.command()
@click.argument("template_id", type=int)
@click.option("--start", default=None)
@click.option("--end", default=None)
def run(template_id, start, end):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.template_run(template_id, start, end)),
            default=str,
            ensure_ascii=False,
        )
    )


@templates_cmd.command()
@click.argument("template_id", type=int)
@click.option("--confirm", is_flag=True, default=False)
def delete(template_id, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "template_delete", template_id)
    click.echo(
        json.dumps(
            unwrap(client.template_delete(template_id)), default=str, ensure_ascii=False
        )
    )
