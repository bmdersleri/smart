from __future__ import annotations

import time
from datetime import datetime, timezone

import click
from scada_reporter_cli.utils.client_helper import get_client
from scada_reporter_cli.utils.repl_skin import (
    success,
    error,
    info,
    warn,
    fmt_table,
    fmt_json,
)


@click.group(name="agent")
def agent_cmd():
    """AI agent workflow komutlari (monitor, analyze)."""


def _fmt_dt(dt_str: str | None) -> str:
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str


@agent_cmd.command()
@click.option("--interval", default=60, help="Kontrol araligi (saniye)")
@click.option("--tags", default="", help="Virgulle ayrilmis tag listesi (bos = tumu)")
@click.option("--threshold", default=3.0, help="Anomali Z-score esigi")
@click.option("--once", is_flag=True, help="Tek sefer calistir, bekleme")
@click.option("--json-output", is_flag=True, help="JSON cikti")
def monitor(interval: int, tags: str, threshold: float, once: bool, json_output: bool):
    """Otomatik SCADA izleme ve anomali denetimi."""
    client, ok = get_client()
    if not ok:
        return

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    while True:
        cycle_start = time.time()
        timestamp = datetime.now(timezone.utc).isoformat()
        findings = []
        stale_count = 0

        # 1. System health check
        health = client.health()
        if "error" in health:
            findings.append(
                ("system", "error", health.get("detail", "API ulasilamiyor"))
            )

        # 2. Query current values
        current = client.current_values()
        readings = current if isinstance(current, list) else []
        if tag_list:
            readings = [r for r in readings if r.get("name") in tag_list]
            for r in readings:
                ts = r.get("timestamp")
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts)
                        age = (datetime.now(timezone.utc) - dt).total_seconds()
                        if age > 300:
                            stale_count += 1
                    except Exception:
                        pass
            if stale_count:
                findings.append(
                    ("stale_tags", "warning", f"{stale_count} tag > 5dk okunmadi")
                )

        # 3. Anomaly scan
        anomaly_total = 0
        anomaly_details = []
        scan_tags = [r.get("name") for r in readings[:10]]
        for tn in scan_tags:
            if tn:
                anom = client.ai_anomalies(tag_name=tn, threshold=threshold)
                if anom and "error" not in anom:
                    count = anom.get("anomaly_rate_pct", 0)
                    if count > 0:
                        anomaly_total += 1
                        anomaly_details.append(
                            {
                                "tag": tn,
                                "rate": count,
                                "count": len(anom.get("anomalies", [])),
                            }
                        )

        if anomaly_total:
            findings.append(
                (
                    "anomalies",
                    "warning",
                    f"{anomaly_total} tag'de anomali tespit edildi",
                )
            )

        # 4. Output
        result = {
            "timestamp": timestamp,
            "status": "ok"
            if not any(f[1] == "error" for f in findings)
            else "degraded",
            "findings": [
                {"type": f[0], "severity": f[1], "message": f[2]} for f in findings
            ],
            "tags_scanned": len(scan_tags),
            "anomaly_tags": anomaly_total,
            "stale_tags": stale_count,
        }

        if json_output:
            click.echo(fmt_json(result))
        else:
            status_icon = success if result["status"] == "ok" else warn
            click.echo(status_icon(f"[{_fmt_dt(timestamp)}] Durum: {result['status']}"))
            click.echo(
                f"  Tarama: {result['tags_scanned']} tag, {result['anomaly_tags']} anomali, {result['stale_tags']} gecikme"
            )
            for f in result["findings"]:
                sev_icon = warn if f["severity"] == "warning" else error
                click.echo(sev_icon(f"  [{f['type']}] {f['message']}"))
            if anomaly_details:
                click.echo(info("  Anomaliler:"))
                for d in anomaly_details:
                    click.echo(f"    {d['tag']}: %{d['rate']:.1f} ({d['count']} olay)")

        if once:
            break

        elapsed = time.time() - cycle_start
        sleep_time = max(1, interval - elapsed)
        time.sleep(sleep_time)


@agent_cmd.command()
@click.argument("question")
@click.option("--json-output", is_flag=True, help="JSON cikti")
def ask(question: str, json_output: bool):
    """Dogal dil ile SCADA verisine soru sor."""
    client, ok = get_client()
    if not ok:
        return
    result = client.ai_query(question)
    if "error" in result:
        click.echo(error(f"Hata: {result.get('detail', 'bilinmeyen hata')}"))
        return
    if json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success("AI Yanit:"))
        click.echo(f"  {result.get('answer', '-')}")
        data = result.get("data")
        if data:
            click.echo(info("Veri:"))
            if isinstance(data, list) and data:
                headers = list(data[0].keys()) if isinstance(data[0], dict) else []
                if headers:
                    click.echo(fmt_table(data, headers=headers))
        chart = result.get("chart_config")
        if chart:
            click.echo(
                info(
                    f"Chart: {chart.get('type', 'unknown')} - {', '.join(chart.get('tags', []))}"
                )
            )


@agent_cmd.command()
@click.argument("tag_name")
@click.option("--window", default="7d", help="Gecmis pencere (ornek: 24h, 7d, 30d)")
@click.option("--threshold", default=3.0, help="Z-score esik degeri")
@click.option("--json-output", is_flag=True, help="JSON cikti")
def anomalies(tag_name: str, window: str, threshold: float, json_output: bool):
    """Bir tag'de anomali tespiti yap."""
    client, ok = get_client()
    if not ok:
        return
    result = client.ai_anomalies(tag_name, window, threshold)
    if "error" in result:
        click.echo(error(f"Hata: {result.get('detail', 'bilinmeyen hata')}"))
        return
    if json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success(f"Anomali Analizi: {tag_name}"))
        click.echo(f"  Toplam okuma: {result.get('total_readings', 0)}")
        click.echo(f"  Anomali orani: %{result.get('anomaly_rate_pct', 0):.2f}")
        anomalies_list = result.get("anomalies", [])
        if anomalies_list:
            click.echo(info(f"  {len(anomalies_list)} anomali olayi:"))
            for a in anomalies_list[:10]:
                sev = warn if a.get("severity") == "warning" else error
                click.echo(
                    sev(
                        f"    [{_fmt_dt(a.get('timestamp', ''))}] {a.get('type', '?')} "
                        + f"deger={a.get('value', '?')} {a.get('details', '')}"
                    )
                )


@agent_cmd.command()
@click.argument("tag_name")
@click.option("--horizon", default="24h", help="Tahmin ufku (ornek: 24h, 7d)")
@click.option("--json-output", is_flag=True, help="JSON cikti")
def forecast(tag_name: str, horizon: str, json_output: bool):
    """Tag degeri icin trend tahmini yap."""
    client, ok = get_client()
    if not ok:
        return
    result = client.ai_predict(tag_name, horizon)
    if "error" in result:
        click.echo(error(f"Hata: {result.get('detail', 'bilinmeyen hata')}"))
        return
    if json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success(f"Tahmin: {tag_name}"))
        click.echo(
            f"  Trend: {result.get('trend_direction', '?')} (egim={result.get('slope', 0):.6f})"
        )
        forecast_data = result.get("forecast", [])
        click.echo(f"  Tahmin noktasi: {len(forecast_data)}")
        if forecast_data:
            click.echo(info("  Ilk 5 tahmin:"))
            for p in forecast_data[:5]:
                click.echo(
                    f"    {_fmt_dt(p.get('timestamp', ''))}: {p.get('value', '?')}"
                )


@agent_cmd.command()
@click.option("--json-output", is_flag=True, help="JSON cikti")
def status(json_output: bool):
    """AI servislerinin durumunu goster."""
    client, ok = get_client()
    if not ok:
        return
    result = client.ai_health()
    if "error" in result:
        click.echo(error(f"AI servislerine ulasilamiyor: {result.get('detail', '?')}"))
        return
    if json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success("AI Servis Durumu"))
        services = result.get("ai_services", [])
        for svc in services:
            click.echo(f"  [OK] {svc}")
