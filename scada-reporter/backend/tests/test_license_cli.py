"""End-to-end smoke for scripts/generate_license.py.

Drives the real CLI (keygen + issue) via subprocess in a tmp dir, then proves
the issued token verifies with the generated public key through the same path
the backend uses at startup.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from app.core.license import verify_license_token

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "generate_license.py"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.mark.parametrize(
    ("keytype", "algorithm"),
    [("rsa", "RS256"), ("ec", "ES256")],
)
def test_keygen_then_issue_verifies(tmp_path: Path, keytype: str, algorithm: str):
    _run("keygen", "--type", keytype, "--out-dir", str(tmp_path), "--name", "lic", cwd=tmp_path)
    priv = tmp_path / "lic_private.pem"
    pub = tmp_path / "lic_public.pem"
    assert priv.exists() and pub.exists()

    out = tmp_path / "license.jwt"
    _run(
        "issue",
        "--private-key",
        str(priv),
        "--algorithm",
        algorithm,
        "--customer",
        "ACME Water",
        "--license-id",
        "lic_001",
        "--features",
        "advanced_reports,grafana,realtime,export",
        "--max-tags",
        "500",
        "--days",
        "365",
        "--out",
        str(out),
        "--public-key",
        str(pub),
        cwd=tmp_path,
    )
    token = out.read_text(encoding="utf-8").strip()

    info = verify_license_token(
        token=token,
        public_key=pub.read_text(encoding="utf-8"),
        algorithms=[algorithm],
        expected_product="ekont-smart-report",
    )
    assert info.customer == "ACME Water"
    assert info.license_id == "lic_001"
    assert info.max_tags == 500
    assert set(info.features) == {"advanced_reports", "grafana", "realtime", "export"}


def test_issue_requires_customer(tmp_path: Path):
    _run("keygen", "--type", "rsa", "--out-dir", str(tmp_path), "--name", "k", cwd=tmp_path)
    priv = tmp_path / "k_private.pem"
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "issue",
            "--private-key",
            str(priv),
            "--algorithm",
            "RS256",
            "--customer",
            "",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "customer" in (proc.stderr + proc.stdout).lower()
