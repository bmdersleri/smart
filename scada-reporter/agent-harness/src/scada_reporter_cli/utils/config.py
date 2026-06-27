from __future__ import annotations

import os
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "scada-reporter"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def token_with_source() -> tuple[str | None, str]:
    env_token = os.environ.get("SCADA_TOKEN")
    if env_token:
        return env_token, "env"
    cfg = load_config()
    token = cfg.get("token")
    return token, "config" if token else "missing"


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def get_token() -> str | None:
    token, _ = token_with_source()
    return token


def set_token(token: str) -> None:
    cfg = load_config()
    cfg["token"] = token
    save_config(cfg)


def get_api_url() -> str:
    return os.environ.get("SCADA_API_URL", "http://localhost:8001")
