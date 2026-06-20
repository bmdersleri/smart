import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_mcp_json_has_no_scada_db():
    cfg = json.loads((ROOT / "mcp.json").read_text(encoding="utf-8"))
    servers = cfg["mcpServers"]
    assert "scada-db" not in servers
    assert "scada" in servers


def test_mcp_db_dir_removed():
    assert not (ROOT / "mcp-servers" / "mcp-db").exists()
