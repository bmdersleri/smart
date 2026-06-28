from __future__ import annotations

import click

from scada_reporter_cli.utils.client_helper import get_client, unwrap
from scada_reporter_cli.utils.repl_skin import error, fmt_json


@click.group(name="compliance")
def compliance_cmd():
    """Uyumluluk merkezi: genel durum, olaylar ve değerlendirme."""


@compliance_cmd.command()
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def overview(json_output: bool):
    """Uyumluluk merkezi genel durumunu göster."""
    client, ok = get_client()
    if not ok:
        return
    result = unwrap(client.compliance_overview())
    if isinstance(result, dict) and result.get("error"):
        click.echo(error(f"Hata: {result.get('detail', 'bilinmeyen hata')}"))
    else:
        click.echo(fmt_json(result))
    client.close()


@compliance_cmd.command()
@click.option("--permit-id", type=int, default=None, help="İzne göre filtrele")
@click.option("--start", default=None, help="ISO 8601 başlangıç")
@click.option("--end", default=None, help="ISO 8601 bitiş")
@click.option(
    "--status", default=None, help="Olay durumu (open/acknowledged/resolved/waived)"
)
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def events(
    permit_id: int | None,
    start: str | None,
    end: str | None,
    status: str | None,
    json_output: bool,
):
    """Uyumluluk olaylarını listele."""
    client, ok = get_client()
    if not ok:
        return
    result = unwrap(
        client.compliance_events(
            permit_id=permit_id, start=start, end=end, status=status
        )
    )
    if isinstance(result, dict) and result.get("error"):
        click.echo(error(f"Hata: {result.get('detail', 'bilinmeyen hata')}"))
    else:
        click.echo(fmt_json(result))
    client.close()


@compliance_cmd.command()
@click.option("--permit-id", type=int, required=True, help="Değerlendirilecek izin")
@click.option("--start", required=True, help="ISO 8601 başlangıç")
@click.option("--end", required=True, help="ISO 8601 bitiş")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def evaluate(permit_id: int, start: str, end: str, json_output: bool):
    """Bir izin için dönem uyumluluk değerlendirmesini çalıştır."""
    client, ok = get_client()
    if not ok:
        return
    result = unwrap(client.compliance_evaluate(permit_id, start, end))
    if isinstance(result, dict) and result.get("error"):
        click.echo(error(f"Hata: {result.get('detail', 'bilinmeyen hata')}"))
    else:
        click.echo(fmt_json(result))
    client.close()
