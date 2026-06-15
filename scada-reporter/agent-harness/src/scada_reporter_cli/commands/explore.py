from __future__ import annotations

import click
from scada_reporter_cli.client import ScadaClient
from scada_reporter_cli.utils.config import get_api_url, get_token
from scada_reporter_cli.utils.repl_skin import success, error, info, fmt_json, fmt_table


@click.group(name="explore")
def explore_cmd():
    """Veritabani kesfi: sema, metadata, istatistikler."""


def _get_client() -> tuple[ScadaClient, bool]:
    token = get_token()
    if not token:
        click.echo(error("Once `scada auth login` ile giris yapin"))
        return None, False  # type: ignore[return-value]
    client = ScadaClient(get_api_url())
    client.set_token(token)
    return client, True


@explore_cmd.command(name="schema")
@click.option("--json-output", is_flag=True, help="JSON cikti")
def schema(json_output: bool):
    """Veritabani semasini kesfet: tablolar, kolonlar, FK'lar."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.explore_schema()
    if "error" in result and result["error"]:
        click.echo(error(f"Hata: {result['error']}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        tables = result.get("tables", {})
        click.echo(success("Veritabani Semasi"))
        click.echo(f"  Surucu: {result.get('db_type', '?')}")
        for tname, info_ in tables.items():
            click.echo()
            click.echo(info(f"Table: {tname} ({info_.get('row_count', '?')} satir)"))
            for col in info_.get("columns", []):
                pk = "PK" if col.get("pk") else "  "
                null_flag = "NULL" if col.get("nullable") else "NOT NULL"
                click.echo(f"  {pk} {col['name']:20s} {col['type']:15s} {null_flag}")
            for fk in info_.get("foreign_keys", []):
                click.echo(f"  FK  {fk['from']} -> {fk['to_table']}({fk['to_column']})")
    client.close()


@explore_cmd.command(name="summary")
@click.option("--json-output", is_flag=True, help="JSON cikti")
def summary(json_output: bool):
    """Veritabani ozet istatistikleri."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.explore_summary()
    if "error" in result and result["error"]:
        click.echo(error(f"Hata: {result['error']}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success("Sistem Ozeti"))
        tags = result.get("tags", {})
        click.echo(
            f"  Tag: {tags.get('active', 0)} aktif / {tags.get('total', 0)} toplam"
        )
        readings = result.get("readings", {})
        click.echo(f"  Okuma: {readings.get('total', 0)} adet")
        click.echo(f"  Son okuma: {readings.get('last_overall', '-')}")
        click.echo(f"  Kullanici: {result.get('users', 0)}")

        devices = result.get("devices", {})
        if devices:
            click.echo()
            click.echo(info("Cihaz bazinda tag dagilimi"))
            dev_rows = [{"device": d, "tag_count": c} for d, c in devices.items()]
            click.echo(fmt_table(dev_rows, ["device", "tag_count"]))

        quality = result.get("quality_distribution", {})
        if quality:
            click.echo()
            click.echo(info("Kalite dagilimi"))
            q_rows = [{"quality": k, "count": v} for k, v in quality.items()]
            click.echo(fmt_table(q_rows, ["quality", "count"]))
    client.close()
