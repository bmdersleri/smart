from __future__ import annotations

import click
from scada_reporter_cli.client import ScadaClient
from scada_reporter_cli.utils.config import get_api_url, set_token
from scada_reporter_cli.utils.repl_skin import success, error, fmt_json


@click.group(name="auth")
def auth_cmd():
    """Kimlik doğrulama işlemleri."""


@auth_cmd.command()
@click.argument("username")
@click.option(
    "--password", "-p", default=None, help="Sifre (verilmezse prompt ile sorulur)"
)
@click.option("--json-output", is_flag=True, help="JSON cikti")
def login(username: str, password: str | None, json_output: bool):
    """API'ye giris yap ve JWT token al."""
    if password is None:
        password = click.prompt("Sifre", hide_input=True)
    client = ScadaClient(get_api_url())
    result = client.login(username, password)
    if "error" in result and result["error"]:
        click.echo(error(f"Giris basarisiz: {result.get('detail', 'bilinmeyen hata')}"))
        return
    set_token(result["access_token"])
    if json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success("Giris basarili"))
        click.echo(f"  Token: {result['access_token'][:20]}...")
    client.close()


@auth_cmd.command()
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def me(json_output: bool):
    """Mevcut kullanıcı bilgilerini göster."""
    from scada_reporter_cli.utils.config import get_token

    token = get_token()
    if not token:
        click.echo(error("Önce `scada auth login` ile giriş yapın"))
        return
    client = ScadaClient(get_api_url())
    client.set_token(token)
    result = client.me()
    if "error" in result and result["error"]:
        click.echo(error(f"Hata: {result.get('detail', 'bilinmeyen hata')}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(success(f"Kullanıcı: {result['username']}"))
        click.echo(f"  Rol: {result['role']}")
        click.echo(f"  Ad: {result.get('full_name', '-')}")
    client.close()


@auth_cmd.command()
@click.argument("username")
@click.argument("email")
@click.password_option()
@click.option("--full-name", default="", help="Tam ad")
@click.option("--role", default="operator", help="Rol (admin/operator/viewer)")
@click.option("--json-output", is_flag=True, help="JSON çıktı")
def register(
    username: str,
    email: str,
    password: str,
    full_name: str,
    role: str,
    json_output: bool,
):
    """Yeni kullanıcı kaydet."""
    client = ScadaClient(get_api_url())
    result = client.register(username, email, password, full_name, role)
    if "error" in result and result["error"]:
        click.echo(error(f"Kayıt başarısız: {result.get('detail', 'bilinmeyen hata')}"))
    elif json_output:
        click.echo(fmt_json(result))
    else:
        click.echo(
            success(f"Kullanıcı oluşturuldu: {result['username']} (id: {result['id']})")
        )
    client.close()
