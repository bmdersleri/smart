from __future__ import annotations

from typing import Any

import click

from scada_core.client import SyncScadaClient
from scada_reporter_cli.utils.client_helper import unwrap
from scada_reporter_cli.utils.config import get_api_url, token_with_source
from scada_reporter_cli.utils.repl_skin import error, fmt_json, info, success, warn


@click.command(name="doctor")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def doctor(json_output: bool) -> None:
    """Agent-native triage: API, auth, readiness, and catalog sanity."""

    api_url = get_api_url()
    token, token_source = token_with_source()

    client = SyncScadaClient(api_url)
    try:
        if token:
            client.set_token(token)

        health = unwrap(client.health())
        ready = unwrap(client.ready())
        system = unwrap(client.system_health())

        auth: dict[str, Any] | None = None
        if token:
            auth = unwrap(client.me())

        issues: list[dict[str, Any]] = []

        if not token:
            issues.append(
                {
                    "kind": "auth",
                    "severity": "warning",
                    "message": "SCADA_TOKEN yok; yazma komutlari ve user context sinirli olacak.",
                }
            )
        elif isinstance(auth, dict) and auth.get("error"):
            issues.append(
                {
                    "kind": "auth",
                    "severity": "error",
                    "message": auth.get("detail", "Kimlik dogrulama basarisiz"),
                }
            )

        if isinstance(health, dict) and health.get("error"):
            issues.append(
                {
                    "kind": "health",
                    "severity": "error",
                    "message": health.get("detail", "API saglik yaniti alinmadi"),
                }
            )

        if isinstance(ready, dict) and ready.get("status") != "ready":
            issues.append(
                {
                    "kind": "ready",
                    "severity": "error",
                    "message": "Readiness kontrolleri tamam degil",
                }
            )

        if isinstance(system, dict):
            if isinstance(system.get("health"), dict) and system["health"].get("error"):
                issues.append(
                    {
                        "kind": "system",
                        "severity": "warning",
                        "message": system["health"].get(
                            "detail", "Sistem saglik yaniti eksik"
                        ),
                    }
                )

        status = (
            "ok"
            if not issues
            else (
                "error" if any(i["severity"] == "error" for i in issues) else "warning"
            )
        )

        report = {
            "status": status,
            "api_url": api_url,
            "token": {
                "present": bool(token),
                "source": token_source,
            },
            "health": health,
            "ready": ready,
            "system": system,
            "auth": auth,
            "issues": issues,
        }

        if json_output:
            click.echo(fmt_json(report))
            return

        click.echo(success(f"Doctor: {status}"))
        click.echo(info(f"API: {api_url}"))
        click.echo(f"  Token: {'var' if token else 'yok'} ({token_source})")

        if isinstance(health, dict) and not health.get("error"):
            click.echo(f"  Health: {health.get('status', 'unknown')}")
            click.echo(
                f"  Collector: {'on' if health.get('collector_running') else 'off'} | "
                f"Scheduler: {'on' if health.get('scheduler_running') else 'off'}"
            )
        else:
            click.echo(
                error(
                    f"  Health: {health.get('detail', 'bilinmiyor') if isinstance(health, dict) else 'bilinmiyor'}"
                )
            )

        if isinstance(ready, dict):
            click.echo(f"  Ready: {ready.get('status', 'unknown')}")
            checks = ready.get("checks", {})
            click.echo(
                f"  Checks: db={checks.get('db')} alembic={checks.get('alembic_head')} "
                f"scheduler={checks.get('scheduler')}"
            )

        if isinstance(system, dict):
            click.echo(
                f"  Catalog: plc={system.get('plc_count', 0)} tag={system.get('tag_count', 0)}"
            )

        if isinstance(auth, dict) and not auth.get("error"):
            click.echo(f"  User: {auth.get('username', '-')} ({auth.get('role', '-')})")

        if issues:
            click.echo()
            click.echo(warn("Issues"))
            for issue in issues:
                prefix = "✗" if issue["severity"] == "error" else "⚠"
                click.echo(f"  {prefix} {issue['kind']}: {issue['message']}")
    finally:
        client.close()
