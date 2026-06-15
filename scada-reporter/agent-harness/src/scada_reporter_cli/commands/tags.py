from __future__ import annotations

import click
from scada_reporter_cli.client import ScadaClient
from scada_reporter_cli.utils.config import get_api_url, get_token
from scada_reporter_cli.utils.repl_skin import success, error, fmt_table, fmt_json


@click.group(name="tags")
def tags_cmd():
    """PLC tag'lerini yönet."""


def _get_client() -> tuple[ScadaClient, bool]:
    token = get_token()
    if not token:
        click.echo(error("Önce `scada auth login` ile giriş yapın"))
        return None, False  # type: ignore[return-value]
    client = ScadaClient(get_api_url())
    client.set_token(token)
    return client, True


@tags_cmd.command(name="list")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def list_tags(json_output: bool):
    """Tüm tag'leri listele."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.list_tags()
    if isinstance(result, list) and result and "error" in result[0]:
        click.echo(error(f"Hata: {result[0].get('detail', 'bilinmeyen hata')}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        if not result:
            click.echo("(tag bulunamadı)")
        else:
            click.echo(fmt_table(result, ["id", "name", "device", "unit", "is_active"]))
            click.echo(f"\nToplam: {len(result)} tag")
    client.close()


@tags_cmd.command()
@click.option("--node-id", required=True, help="PLC node ID (örn. DB171,REAL0)")
@click.option("--name", required=True, help="Tag adı")
@click.option("--description", default="", help="Açıklama")
@click.option("--unit", default="", help="Birim")
@click.option("--device", default="", help="Cihaz/PLC adı")
@click.option("--channel", default="", help="Kanal/group")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def create(
    node_id: str,
    name: str,
    description: str,
    unit: str,
    device: str,
    channel: str,
    json_output: bool,
):
    """Yeni tag oluştur."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.create_tag(node_id, name, description, unit, channel, device)
    if "error" in result and result["error"]:
        click.echo(
            error(f"Oluşturma başarısız: {result.get('detail', 'bilinmeyen hata')}")
        )
    elif json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success(f"Tag oluşturuldu: {result['name']} (id: {result['id']})"))
    client.close()


@tags_cmd.command()
@click.argument("tag-id", type=int)
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def delete(tag_id: int, json_output: bool):
    """Tag sil (admin)."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.delete_tag(tag_id)
    if "error" in result and result["error"]:
        click.echo(error(f"Silme başarısız: {result.get('detail', 'bilinmeyen hata')}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success(f"Tag {tag_id} silindi"))
    client.close()


@tags_cmd.command(name="update")
@click.argument("tag-id", type=int)
@click.option("--unit", default=None, help="Birim (örn. m³/h, bar)")
@click.option("--device", default=None, help="Cihaz/PLC adı")
@click.option("--channel", default=None, help="Kanal/group")
@click.option("--description", default=None, help="Açıklama")
@click.option("--min-alarm", type=float, default=None, help="Min alarm eşiği")
@click.option("--max-alarm", type=float, default=None, help="Max alarm eşiği")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def update(
    tag_id: int,
    unit: str | None,
    device: str | None,
    channel: str | None,
    description: str | None,
    min_alarm: float | None,
    max_alarm: float | None,
    json_output: bool,
):
    """Tag güncelle (birim, cihaz, kanal, alarm eşikleri)."""
    if all(
        v is None for v in [unit, device, channel, description, min_alarm, max_alarm]
    ):
        click.echo(error("Güncellenecek en az bir alan belirtin"))
        return
    if min_alarm is not None and max_alarm is not None and min_alarm >= max_alarm:
        click.echo(error("Min alarm değeri Max alarm'dan küçük olmalı"))
        return
    client, ok = _get_client()
    if not ok:
        return
    result = client.update_tag(
        tag_id,
        unit=unit,
        device=device,
        channel=channel,
        description=description,
        min_alarm=min_alarm,
        max_alarm=max_alarm,
    )
    if "error" in result and result["error"]:
        click.echo(
            error(f"Güncelleme başarısız: {result.get('detail', 'bilinmeyen hata')}")
        )
    elif json_output:
        click.echo(fmt_json(result))
    else:
        parts: list[str] = []
        if unit:
            parts.append(f"birim={unit}")
        if device:
            parts.append(f"cihaz={device}")
        if min_alarm is not None:
            parts.append(f"min_alarm={min_alarm}")
        if max_alarm is not None:
            parts.append(f"max_alarm={max_alarm}")
        click.echo(
            success(f"Tag {tag_id} güncellendi: {', '.join(parts) or 'değişiklik yok'}")
        )
    client.close()


@tags_cmd.command(name="readings")
@click.argument("tag-id", type=int)
@click.option("--start", help="Başlangıç (ISO format, örn: 2024-01-01T00:00:00)")
@click.option("--end", help="Bitiş (ISO format)")
@click.option("--limit", default=100, help="Maks okuma sayısı")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def get_readings(
    tag_id: int, start: str | None, end: str | None, limit: int, json_output: bool
):
    """Tag okuma değerlerini getir."""
    client, ok = _get_client()
    if not ok:
        return
    result = client.get_readings(tag_id, start, end, limit)
    if isinstance(result, list) and result and "error" in result[0]:
        click.echo(error(f"Hata: {result[0].get('detail', 'bilinmeyen hata')}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        if not result:
            click.echo("(okuma bulunamadı)")
        else:
            keys = ["timestamp", "value", "quality"]
            click.echo(fmt_table([{k: r.get(k) for k in keys} for r in result], keys))
            click.echo(f"\nToplam: {len(result)} okuma")
    client.close()
