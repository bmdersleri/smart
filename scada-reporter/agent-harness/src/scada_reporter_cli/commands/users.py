import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap, require_confirm


@click.group(name="users")
def users_cmd():
    """Kullanıcı yönetimi (admin)."""


@users_cmd.command()
@click.argument("username")
@click.option("--email", required=True)
@click.option("--password", required=True)
@click.option("--full-name", default="")
@click.option("--role", default="operator")
def create(username, email, password, full_name, role):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.user_create(username, email, password, full_name, role)),
            default=str,
            ensure_ascii=False,
        )
    )


@users_cmd.command()
@click.argument("user_id", type=int)
@click.option("--email", default=None)
@click.option("--full-name", default=None)
@click.option("--role", default=None)
@click.option("--is-active", type=bool, default=None)
def update(user_id, email, full_name, role, is_active):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.user_update(user_id, email, full_name, role, is_active)),
            default=str,
            ensure_ascii=False,
        )
    )


@users_cmd.command(name="set-password")
@click.argument("user_id", type=int)
@click.option("--password", required=True)
def set_password(user_id, password):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.user_set_password(user_id, password)),
            default=str,
            ensure_ascii=False,
        )
    )


@users_cmd.command()
@click.argument("user_id", type=int)
@click.option("--confirm", is_flag=True, default=False)
def delete(user_id, confirm):
    client, ok = get_client()
    if not ok:
        return
    require_confirm(confirm, "user_delete", user_id)
    click.echo(
        json.dumps(unwrap(client.user_delete(user_id)), default=str, ensure_ascii=False)
    )
