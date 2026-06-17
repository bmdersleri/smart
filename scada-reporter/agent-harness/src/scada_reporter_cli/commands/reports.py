from __future__ import annotations

import click
from scada_reporter_cli.utils.client_helper import get_client
from scada_reporter_cli.utils.repl_skin import success, error, info, fmt_json, fmt_table


@click.group(name="reports")
def reports_cmd():
    """Rapor oluşturma."""


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
    client, ok = get_client()
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


@reports_cmd.command(name="list-history")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def list_history(json_output: bool):
    """Son 10 raporu listele."""
    client, ok = get_client()
    if not ok:
        return
    result = client.list_report_history()
    if (
        isinstance(result, list)
        and result
        and isinstance(result[0], dict)
        and result[0].get("error")
    ):
        click.echo(error(f"Hata: {result[0].get('detail', 'bilinmeyen hata')}"))
        client.close()
        return
    if json_output:
        click.echo(fmt_json(result))
    else:
        if not result:
            click.echo("(henüz rapor yok)")
        else:
            rows = [
                {
                    "id": r["id"],
                    "tarih": r["created_at"][:16].replace("T", " "),
                    "tag sayısı": len(r.get("tag_ids", [])),
                    "aralık": r["interval"],
                    "format": r["format"],
                }
                for r in result
            ]
            click.echo(
                fmt_table(rows, ["id", "tarih", "tag sayısı", "aralık", "format"])
            )
    client.close()


@reports_cmd.command(name="download-history")
@click.argument("history-id", type=int)
@click.option(
    "--output", default=None, help="Çıktı dosyası (varsayılan: sunucudan alınan ad)"
)
@click.option("--json-output", is_flag=True, help="JSON meta çıktı")
def download_history(history_id: int, output: str | None, json_output: bool):
    """Geçmiş raporu tekrar indir."""
    client, ok = get_client()
    if not ok:
        return
    result = client.download_report_history(history_id)
    if isinstance(result, dict) and result.get("error"):
        click.echo(error(f"İndirme hatası: {result.get('detail', 'bilinmeyen hata')}"))
        client.close()
        return
    content: bytes = result["content"]
    filename: str = output or result.get("filename", f"scada_rapor_{history_id}.bin")
    with open(filename, "wb") as f:
        f.write(content)
    if json_output:
        click.echo(
            fmt_json({"file": filename, "size": len(content), "history_id": history_id})
        )
    else:
        click.echo(success(f"Rapor indirildi: {filename} ({len(content):,} byte)"))
    client.close()
