from __future__ import annotations

import click
from scada_reporter_cli.client import ScadaClient
from scada_reporter_cli.utils.config import get_api_url, get_token
from scada_reporter_cli.utils.repl_skin import success, error, info, fmt_json


@click.group(name="reports")
def reports_cmd():
    """Rapor oluşturma."""


def _get_client() -> tuple[ScadaClient, bool]:
    token = get_token()
    if not token:
        click.echo(error("Önce `scada auth login` ile giriş yapın"))
        return None, False  # type: ignore[return-value]
    client = ScadaClient(get_api_url())
    client.set_token(token)
    return client, True


@reports_cmd.command()
@click.option(
    "--tag-ids", required=True, help="Virgülle ayrılmış tag ID'leri (örn: 1,2,3)"
)
@click.option("--start", required=True, help="Başlangıç (ISO: 2024-01-01T00:00:00)")
@click.option("--end", required=True, help="Bitiş (ISO: 2024-01-01T23:59:59)")
@click.option(
    "--interval",
    default="hourly",
    type=click.Choice(["hourly", "daily"]),
    help="Gruplama aralığı",
)
@click.option(
    "--format",
    "output_format",
    default="json",
    type=click.Choice(["json", "excel"]),
    help="Çıktı formatı",
)
@click.option("--output", help="Çıktı dosyası (excel için .xlsx)")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def generate(
    tag_ids: str,
    start: str,
    end: str,
    interval: str,
    output_format: str,
    output: str | None,
    json_output: bool,
):
    """Rapor oluştur."""
    client, ok = _get_client()
    if not ok:
        return

    ids = [int(x.strip()) for x in tag_ids.split(",")]
    result = client.generate_report(ids, start, end, interval, output_format)

    if isinstance(result, dict) and "error" in result and result["error"]:
        click.echo(error(f"Rapor hatası: {result.get('detail', 'bilinmeyen hata')}"))
        return

    if output_format == "excel":
        fname = output or f"scada_rapor_{start[:10]}_{end[:10]}.xlsx"
        with open(fname, "wb") as f:
            f.write(result)
        click.echo(success(f"Excel raporu kaydedildi: {fname}"))
        if json_output:
            click.echo(
                fmt_json({"file": fname, "format": "excel", "size": len(result)})
            )
    else:
        if json_output:
            click.echo(fmt_json(result))
        else:
            data = result.get("data", {})
            click.echo(success(f"Rapor: {result.get('period', interval)}"))
            click.echo(f"  Aralık: {result.get('start')} → {result.get('end')}")
            click.echo(f"  Tag sayısı: {len(data)}")
            for tag_name, rows in data.items():
                click.echo(info(tag_name))
                click.echo(f"  {len(rows)} dilim")
    client.close()
