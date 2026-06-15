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


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def get_token() -> str | None:
    token = os.environ.get("SCADA_TOKEN")
    if token:
        return token
    cfg = load_config()
    return cfg.get("token")


def set_token(token: str) -> None:
    cfg = load_config()
    cfg["token"] = token
    save_config(cfg)


def get_api_url() -> str:
    return os.environ.get("SCADA_API_URL", "http://localhost:8001")
