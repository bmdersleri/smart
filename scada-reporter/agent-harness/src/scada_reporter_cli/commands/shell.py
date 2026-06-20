from __future__ import annotations

import sys
import code

import click
from scada_core.client import SyncScadaClient
from scada_reporter_cli.utils.client_helper import unwrap
from scada_reporter_cli.utils.config import get_api_url, get_token
from scada_reporter_cli.utils.repl_skin import banner, info, success


def _setup_context() -> dict:
    """Shell icin on-yuklu context olustur."""
    ctx: dict = {}

    ctx["API_URL"] = get_api_url()
    ctx["client"] = SyncScadaClient(ctx["API_URL"])
    token = get_token()
    if token:
        ctx["client"].set_token(token)
        ctx["TOKEN"] = token
        print(success("Token yuklendi"))
    else:
        print(info("Token yok — once scada auth login"))

    try:
        import pandas as pd  # type: ignore[import-untyped]

        ctx["pd"] = pd
        ctx["DataFrame"] = pd.DataFrame

        def load_tags() -> pd.DataFrame:
            """Tag listesini DataFrame olarak yukle."""
            data = unwrap(ctx["client"].list_tags())
            if isinstance(data, list) and data and "error" in data[0]:
                print("Hata:", data[0].get("detail"))
                return pd.DataFrame()
            return pd.DataFrame(data)

        def load_readings(tag_id: int, limit: int = 1000) -> pd.DataFrame:
            """Tag okumalarini DataFrame olarak yukle."""
            data = unwrap(ctx["client"].get_readings(tag_id, limit=limit))
            if isinstance(data, list) and data and "error" in data[0]:
                print("Hata:", data[0].get("detail"))
                return pd.DataFrame()
            return pd.DataFrame(data)

        def load_current() -> pd.DataFrame:
            """Canli degerleri DataFrame olarak yukle."""
            data = unwrap(ctx["client"].current_values())
            if isinstance(data, list) and data and "error" in data[0]:
                print("Hata:", data[0].get("detail"))
                return pd.DataFrame()
            return pd.DataFrame(data)

        def query(sql: str, limit: int = 5000) -> pd.DataFrame:
            """SQL sorgusu calistir, sonucu DataFrame olarak getir."""
            result = unwrap(ctx["client"].run_sql(sql, limit=limit))
            if "error" in result and result["error"]:
                print("Hata:", result.get("detail"))
                return pd.DataFrame()
            return pd.DataFrame(result.get("rows", []))

        ctx["load_tags"] = load_tags
        ctx["load_readings"] = load_readings
        ctx["load_current"] = load_current
        ctx["query"] = query

        print(
            success(
                "Pandas yuklendi — load_tags(), load_readings(id), load_current(), query(sql)"
            )
        )
    except ImportError:
        print(info("Pandas yuklu degil — pip install pandas ile kurabilirsiniz"))

    import json as _json
    import datetime as _dt

    ctx["json"] = _json
    ctx["datetime"] = _dt

    print(info(f"API: {ctx['API_URL']} | Cikmak icin: exit()"))
    return ctx


@click.command(name="shell")
@click.option("--no-banner", is_flag=True, help="Banner gosterme")
def shell(no_banner: bool):
    """Python REPL ac — on-yuklu SyncScadaClient + Pandas.

    Hazir degiskenler:
      client      — SyncScadaClient (tokenli)
      load_tags() — Tag listesi DataFrame
      load_readings(id, limit) — Tag okumalari DataFrame
      load_current() — Canli degerler DataFrame
      query(sql)  — SQL sorgusu DataFrame
      pd          — Pandas
      json        — json modulu
      datetime    — datetime modulu
    """
    if not no_banner:
        print(banner())
        print(info("EKONT SMART REPORT Python Shell"))
        print()

    ctx = _setup_context()
    print()

    shell_banner = (
        "Python {} | EKONT SMART REPORT Shell\n"
        "Hazir: client, load_tags(), load_readings(), load_current(), query(), pd, json"
    ).format(sys.version.split()[0])

    try:
        import IPython  # type: ignore[import-untyped]

        IPython.embed(header=shell_banner, user_ns=ctx)
    except ImportError:
        code.interact(banner=shell_banner, local=ctx)
    finally:
        ctx["client"].close()
