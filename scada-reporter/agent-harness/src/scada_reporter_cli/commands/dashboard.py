from __future__ import annotations

import click
from scada_reporter_cli.client import ScadaClient
from scada_reporter_cli.utils.config import get_api_url, get_token
from scada_reporter_cli.utils.repl_skin import success, error, info, fmt_table, fmt_json


@click.group(name="dashboard")
def dashboard_cmd():
    """Dashboard verileri ve canlı değerler."""


def _get_client() -> tuple[ScadaClient, bool]:
    token = get_token()
    if not token:
        click.echo(error("Önce `scada auth login` ile giriş yapın"))
        return None, False  # type: ignore[return-value]
    client = ScadaClient(get_api_url())
    client.set_token(token)
    return client, True


@dashboard_cmd.command()
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def overview(json_output: bool):
    """Sistem genel durumunu göster."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.overview()
    if "error" in result and result["error"]:
        click.echo(error(f"Hata: {result.get('detail', 'bilinmeyen hata')}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success("Sistem Durumu"))
        click.echo(f"  Aktif tag: {result.get('active_tags', '?')}")
        click.echo(f"  Son okuma: {result.get('last_reading', '-')}")
        click.echo(f"  24s okuma: {result.get('readings_24h', '?')}")
    client.close()


@dashboard_cmd.command(name="current-values")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def current_values(json_output: bool):
    """Tüm tag'lerin son değerlerini göster."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.current_values()
    if isinstance(result, list) and result and "error" in result[0]:
        click.echo(error(f"Hata: {result[0].get('detail', 'bilinmeyen hata')}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        if not result:
            click.echo("(veri yok)")
        else:
            rows = [
                {
                    "device": r["device"],
                    "name": r["name"],
                    "value": r["value"],
                    "unit": r["unit"],
                    "quality_ok": "✓" if r["quality_ok"] else "✗",
                }
                for r in result
            ]
            click.echo(
                fmt_table(rows, ["device", "name", "value", "unit", "quality_ok"])
            )
    client.close()


@dashboard_cmd.command()
@click.argument("tag-ids", nargs=-1, type=int, required=True)
@click.option("--hours", default=24, help="Saat aralığı")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def trend(tag_ids: tuple[int, ...], hours: int, json_output: bool):
    """Tag'lerin trend verisini getir."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.trend(list(tag_ids), hours)
    if isinstance(result, list) and result and "error" in result[0]:
        click.echo(error(f"Hata: {result[0].get('detail', 'bilinmeyen hata')}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        if not result:
            click.echo("(veri yok)")
        else:
            for series in result:
                click.echo()
                click.echo(info(f"{series['name']} ({series['unit']})"))
                click.echo(f"  {len(series['data'])} okuma, {hours}s")
                if series["data"]:
                    first = series["data"][0]
                    last = series["data"][-1]
                    click.echo(f"  İlk: {first['t']} → {first['v']}")
                    click.echo(f"  Son: {last['t']} → {last['v']}")
    client.close()
