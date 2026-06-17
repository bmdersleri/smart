from __future__ import annotations

import click
from scada_reporter_cli.utils.client_helper import get_client
from scada_reporter_cli.utils.repl_skin import success, error, info, fmt_table, fmt_json


@click.group(name="dashboard")
def dashboard_cmd():
    """Dashboard verileri ve canlı değerler."""


@dashboard_cmd.command()
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def overview(json_output: bool):
    """Sistem genel durumunu göster."""
    client, ok = get_client()
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


_ALARM_LABELS = {"overflow": "OVERFLOW", "max": "MAX AŞIMI", "min": "MIN ALTI"}


@dashboard_cmd.command(name="current-values")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
@click.option(
    "--alarm-only", is_flag=True, help="Sadece alarm durumundaki tag'leri göster"
)
@click.option(
    "--watch",
    "watch_interval",
    type=click.IntRange(min=0),
    default=0,
    metavar="SANIYE",
    help="Her N saniyede bir yenile (0=devre dışı). Ctrl+C ile çık.",
)
def current_values(json_output: bool, alarm_only: bool, watch_interval: int):
    """Tüm tag'lerin son değerlerini göster."""
    import time
    from datetime import datetime

    def _render() -> bool:
        client, ok = get_client()
        if not ok:
            return False
        result = client.current_values()
        client.close()
        if isinstance(result, list) and result and "error" in result[0]:
            click.echo(error(f"Hata: {result[0].get('detail', 'bilinmeyen hata')}"))
            return False
        if alarm_only:
            result = [r for r in result if r.get("alarm_state") is not None]
        if json_output:
            click.echo(fmt_json(result))
            return True
        if not result:
            click.echo("(alarm yok)" if alarm_only else "(veri yok)")
            return True
        rows = [
            {
                "cihaz": r["device"],
                "tag": r["name"],
                "değer": r["value"],
                "birim": r["unit"],
                "kalite": "✓" if r["quality_ok"] else "✗",
                "alarm": _ALARM_LABELS.get(r.get("alarm_state", ""), "—")
                if r.get("alarm_state")
                else "—",
            }
            for r in result
        ]
        click.echo(
            fmt_table(rows, ["cihaz", "tag", "değer", "birim", "kalite", "alarm"])
        )
        alarm_count = sum(1 for r in result if r.get("alarm_state"))
        if alarm_count:
            click.echo(f"\n⚠  {alarm_count} alarm aktif")
        return True

    if watch_interval > 0:
        try:
            while True:
                click.clear()
                click.echo(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Yenileniyor (Ctrl+C ile çık)\n"
                )
                if not _render():
                    break
                time.sleep(watch_interval)
        except KeyboardInterrupt:
            click.echo(info("\nDurduruldu."))
    else:
        _render()


@dashboard_cmd.command()
@click.argument("tag-ids", nargs=-1, type=int, required=True)
@click.option("--hours", default=24, help="Saat aralığı")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def trend(tag_ids: tuple[int, ...], hours: int, json_output: bool):
    """Tag'lerin trend verisini getir."""
    client, ok = get_client()
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
