from __future__ import annotations

import sys
import shlex

import click

from scada_core.client import SyncScadaClient
from scada_reporter_cli.utils.client_helper import unwrap
from scada_reporter_cli.utils.config import get_api_url, get_token
from scada_reporter_cli.utils.repl_skin import banner, success, error, info, fmt_json
from scada_reporter_cli.commands.auth import auth_cmd
from scada_reporter_cli.commands.tags import tags_cmd
from scada_reporter_cli.commands.dashboard import dashboard_cmd
from scada_reporter_cli.commands.reports import reports_cmd
from scada_reporter_cli.commands.query import query_cmd
from scada_reporter_cli.commands.explore import explore_cmd
from scada_reporter_cli.commands.doctor import doctor
from scada_reporter_cli.commands.shell import shell
from scada_reporter_cli.commands.agent import agent_cmd
from scada_reporter_cli.commands.watchlist import watchlist_cmd
from scada_reporter_cli.commands.annotations import annotations_cmd
from scada_reporter_cli.commands.templates import templates_cmd
from scada_reporter_cli.commands.scheduled import scheduled_cmd
from scada_reporter_cli.commands.groups import groups_cmd
from scada_reporter_cli.commands.plc import plc_cmd
from scada_reporter_cli.commands.users import users_cmd


@click.group(invoke_without_command=True)
@click.option(
    "--api-url",
    envvar="SCADA_API_URL",
    default="http://localhost:8001",
    help="API base URL",
)
@click.option(
    "--json", "json_output", is_flag=True, help="Tum ciktiyi JSON formatinda ver"
)
@click.pass_context
def cli(ctx: click.Context, api_url: str, json_output: bool):
    """EKONT SMART REPORT — Su/Atiksu tesisi SCADA veri toplama ve raporlama ara yuzu."""
    ctx.ensure_object(dict)
    ctx.obj["API_URL"] = api_url
    ctx.obj["JSON_OUTPUT"] = json_output

    if ctx.invoked_subcommand is None:
        repl(ctx)


cli.add_command(auth_cmd)
cli.add_command(tags_cmd)
cli.add_command(dashboard_cmd)
cli.add_command(reports_cmd)
cli.add_command(query_cmd)
cli.add_command(explore_cmd)
cli.add_command(doctor)
cli.add_command(shell)
cli.add_command(agent_cmd)
cli.add_command(watchlist_cmd)
cli.add_command(annotations_cmd)
cli.add_command(templates_cmd)
cli.add_command(scheduled_cmd)
cli.add_command(groups_cmd)
cli.add_command(plc_cmd)
cli.add_command(users_cmd)


def repl(ctx: click.Context) -> None:
    """Interaktif REPL modu."""
    api_url = ctx.obj["API_URL"]
    print(banner())
    print(info("API: {} | Cikmak icin: exit, quit".format(api_url)))
    print()

    client = SyncScadaClient(api_url)
    token = get_token()
    if token:
        client.set_token(token)
        print(success("Token yuklendi"))
    else:
        print(info("Giris yapmak icin: auth login <kullanici>"))
    print()

    while True:
        try:
            line = input("scada> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line in ("exit", "quit", "q"):
            break
        if line in ("help", "h", "?"):
            _repl_help()
            continue

        try:
            args = shlex.split(line)
        except ValueError as e:
            print(error("Hatali giris: {}".format(e)))
            continue

        try:
            from click.testing import CliRunner

            runner = CliRunner()
            result = runner.invoke(cli, args, obj=ctx.obj, standalone_mode=False)
            if result.exception:
                print(error("Hata: {}".format(result.exception)))
            elif result.output:
                print(result.output.rstrip())
        except Exception as e:
            print(error("Beklenmeyen hata: {}".format(e)))

    client.close()
    print(info("Gorusmek uzere."))


def _repl_help() -> None:
    print("""
Komutlar:
  auth login <username>         Giris yap
  auth me                       Kullanici bilgisi
  tags list                     Tag'leri listele
  tags readings <id>            Tag okumalari
  tags create --name X ...      Yeni tag
  dashboard overview            Sistem durumu
  dashboard current-values      Canli degerler
  dashboard trend <id>...       Trend verisi
  reports generate ...          Rapor olustur
  query run <sql>               SQL sorgusu calistir
  explore schema                Veritabani semasi
  explore summary               Sistem ozet istatistikleri
  doctor                        Agent triage: health, auth, readiness
  shell                         Python REPL (Pandas ile)
  health                        Sistem sagligi

Secenekler:
  --json        JSON cikti
  --help        Komut yardim

Yerel degiskenler:
  SCADA_API_URL=http://localhost:8001
  SCADA_TOKEN=<jwt>
""")


@cli.command()
@click.pass_context
@click.option("--json-output", is_flag=True)
def health(ctx: click.Context, json_output: bool):
    """Sistem saglik kontrolu."""
    api_url = ctx.obj.get("API_URL", get_api_url())
    client = SyncScadaClient(api_url)
    token = get_token()
    if token:
        client.set_token(token)
    result = unwrap(client.health())
    if "error" in result and result["error"]:
        click.echo(error("API yanit vermiyor: {}".format(result.get("detail"))))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        opc_status = "✓" if result.get("opc_connected") else "✗"
        click.echo(success("API saglikli — OPC baglantisi: {}".format(opc_status)))
    client.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    cli(obj={})


if __name__ == "__main__":
    main()
