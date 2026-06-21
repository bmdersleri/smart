import json
import click
from scada_reporter_cli.utils.client_helper import get_client, unwrap


@click.group(name="annotations")
def annotations_cmd():
    """Annotation yönetimi."""


@annotations_cmd.command()
@click.option("--ts", required=True, help="ISO 8601 zaman damgası")
@click.option("--text", required=True)
@click.option("--tag-id", type=int, default=None)
def add(ts, text, tag_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.annotation_add(ts, text, tag_id)),
            default=str,
            ensure_ascii=False,
        )
    )


@annotations_cmd.command()
@click.argument("annotation_id", type=int)
def delete(annotation_id):
    client, ok = get_client()
    if not ok:
        return
    click.echo(
        json.dumps(
            unwrap(client.annotation_delete(annotation_id)),
            default=str,
            ensure_ascii=False,
        )
    )
