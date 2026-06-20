import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="plc")
def plc_cmd():
    """PLC bağlantı yapılandırması yönetimi."""


@plc_cmd.command()
@click.argument("name")
@click.option("--ip", default="")
@click.option("--rack", type=int, default=0)
@click.option("--slot", type=int, default=1)
def create(name, ip, rack, slot):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.plc_create(name, ip, rack, slot)),
            default=str,
            ensure_ascii=False,
        )
    )


@plc_cmd.command()
@click.argument("name")
@click.option("--ip", required=True)
@click.option("--rack", type=int, default=0)
@click.option("--slot", type=int, default=1)
def update(name, ip, rack, slot):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.plc_update(name, ip, rack, slot)),
            default=str,
            ensure_ascii=False,
        )
    )


@plc_cmd.command()
@click.argument("name")
@click.option("--confirm", is_flag=True, default=False)
def delete(name, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "plc_delete", name)
    click.echo(
        json.dumps(unwrap(client.plc_delete(name)), default=str, ensure_ascii=False)
    )
