import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="groups")
def groups_cmd():
    """Tag grubu yönetimi."""


@groups_cmd.command()
@click.argument("name")
@click.option("--parent-id", type=int, default=None)
@click.option("--sort-order", type=int, default=0)
def create(name, parent_id, sort_order):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.group_create(name, parent_id, sort_order)),
            default=str,
            ensure_ascii=False,
        )
    )


@groups_cmd.command()
@click.argument("group_id", type=int)
@click.option("--name", default=None)
@click.option("--parent-id", type=int, default=None)
@click.option("--sort-order", type=int, default=None)
def update(group_id, name, parent_id, sort_order):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.group_update(group_id, name, parent_id, sort_order)),
            default=str,
            ensure_ascii=False,
        )
    )


@groups_cmd.command()
@click.argument("group_id", type=int)
@click.option("--tag-ids", required=True, help="Virgülle ayrılmış tag id'leri")
def assign(group_id, tag_ids):
    client, ok = get_client()
    if not ok:
        return
    ids = [int(x) for x in tag_ids.split(",") if x.strip()]
    click.echo(
        json.dumps(
            unwrap(client.group_assign(group_id, ids)), default=str, ensure_ascii=False
        )
    )


@groups_cmd.command()
@click.option("--tag-ids", required=True, help="Virgülle ayrılmış tag id'leri")
def unassign(tag_ids):
    client, ok = get_client()
    if not ok:
        return
    ids = [int(x) for x in tag_ids.split(",") if x.strip()]
    click.echo(
        json.dumps(unwrap(client.group_unassign(ids)), default=str, ensure_ascii=False)
    )


@groups_cmd.command()
@click.argument("group_id", type=int)
@click.option("--confirm", is_flag=True, default=False)
def delete(group_id, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "group_delete", group_id)
    click.echo(
        json.dumps(
            unwrap(client.group_delete(group_id)), default=str, ensure_ascii=False
        )
    )
