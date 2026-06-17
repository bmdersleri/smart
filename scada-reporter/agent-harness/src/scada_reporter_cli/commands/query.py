from __future__ import annotations

import click
from scada_reporter_cli.utils.client_helper import get_client
from scada_reporter_cli.utils.repl_skin import success, error, fmt_json, fmt_table


@click.group(name="query")
def query_cmd():
    """Read-only SQL sorgulari."""


@query_cmd.command(name="run")
@click.argument("sql")
@click.option("--limit", default=100, help="Maks sonuc sayisi")
@click.option("--json-output", is_flag=True, help="JSON cikti")
def run(sql: str, limit: int, json_output: bool):
    """Read-only SQL SELECT sorgusu calistir.

    Agent'larin veriyi kendi sorgulariyla kesfetmesini saglar.
    Sadece SELECT / WITH / EXPLAIN sorgularina izin verilir.

    Ornek: scada query run "SELECT device, COUNT(*) FROM tags GROUP BY device"
    """
    client, ok = get_client()
    if not ok:
        return
    result = client.run_query(sql, limit=limit)
    if "error" in result and result["error"]:
        detail = result.get("detail", "bilinmeyen hata")
        click.echo(error(f"Sorgu hatasi: {detail}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success("Sorgu sonucu"))
        click.echo(f"  Sutunlar: {', '.join(result.get('columns', []))}")
        click.echo(f"  Satir: {result.get('row_count', 0)}")
        rows = result.get("rows", [])
        if rows:
            click.echo()
            click.echo(fmt_table(rows, result.get("columns", list(rows[0].keys()))))
        if result.get("truncated"):
            click.echo(error(f"Sonuc kesildi (limit: {limit})"))
    client.close()
