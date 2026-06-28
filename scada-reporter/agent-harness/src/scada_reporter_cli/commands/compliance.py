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


def _emit(client, result):
    if isinstance(result, dict) and result.get("error"):
        click.echo(error(f"Hata: {result.get('detail', 'bilinmeyen hata')}"))
    else:
        click.echo(fmt_json(result))
    client.close()


@compliance_cmd.command()
@click.argument("question")
@click.option("--permit-id", type=int, default=None, help="İzne göre bağla")
@click.option("--start", default=None, help="ISO 8601 başlangıç")
@click.option("--end", default=None, help="ISO 8601 bitiş")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def ask(
    question: str,
    permit_id: int | None,
    start: str | None,
    end: str | None,
    json_output: bool,
):
    """Uyumluluk asistanına doğal dilde soru sor (READ + taslak, yazma yapmaz)."""
    client, ok = get_client()
    if not ok:
        return
    result = unwrap(
        client.compliance_assistant(question, permit_id=permit_id, start=start, end=end)
    )
    _emit(client, result)


@compliance_cmd.group(name="note")
def note_cmd():
    """Uyumluluk olayı notları (yazma)."""


@note_cmd.command(name="add")
@click.argument("event_id", type=int)
@click.argument("text")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def note_add(event_id: int, text: str, json_output: bool):
    """Bir uyumluluk olayına operatör açıklama notu ekle."""
    client, ok = get_client()
    if not ok:
        return
    result = unwrap(client.compliance_add_note(event_id, text))
    _emit(client, result)


@compliance_cmd.group(name="status")
def status_cmd():
    """Uyumluluk olayı durum geçişleri (yazma)."""


@status_cmd.command(name="set")
@click.argument("event_id", type=int)
@click.argument("status")
@click.option("--reason", default=None, help="waive_reason ('waived' için zorunlu)")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def status_set(event_id: int, status: str, reason: str | None, json_output: bool):
    """Bir uyumluluk olayının durumunu değiştir."""
    client, ok = get_client()
    if not ok:
        return
    result = unwrap(client.compliance_set_status(event_id, status, reason=reason))
    _emit(client, result)


@compliance_cmd.group(name="report-pack")
def report_pack_cmd():
    """Resmî rapor paketleri (yazma)."""


@report_pack_cmd.command(name="create")
@click.option("--permit-id", type=int, required=True, help="İzin")
@click.option("--start", required=True, help="ISO 8601 başlangıç")
@click.option("--end", required=True, help="ISO 8601 bitiş")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def report_pack_create(permit_id: int, start: str, end: str, json_output: bool):
    """Bir izin ve dönem için taslak rapor paketi oluştur."""
    client, ok = get_client()
    if not ok:
        return
    result = unwrap(client.compliance_create_report_pack(permit_id, start, end))
    _emit(client, result)


@report_pack_cmd.command(name="approve")
@click.argument("pack_id", type=int)
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def report_pack_approve(pack_id: int, json_output: bool):
    """Bir rapor paketini onayla."""
    client, ok = get_client()
    if not ok:
        return
    result = unwrap(client.compliance_approve_report_pack(pack_id))
    _emit(client, result)
