"""EKONT SMART REPORT — commercial license generator (VENDOR side).

Signs license JWTs that the deployed backend verifies at startup with the
matching PUBLIC key (see app.core.license.verify_required_license). Keep the
PRIVATE key off customer machines — it is the only thing that can mint licenses.

Run with the backend venv (it has jose + cryptography):

    cd scada-reporter/backend
    .venv/Scripts/python ../../scripts/generate_license.py keygen --type rsa
    .venv/Scripts/python ../../scripts/generate_license.py issue \
        --private-key license_private.pem --algorithm RS256 \
        --customer "ACME Water" --license-id lic_001 \
        --features advanced_reports,grafana,realtime,export \
        --max-tags 500 --days 365 --out license.jwt --public-key license_public.pem

Feature keys understood by the backend gates:
    advanced_reports | grafana | realtime | export
An empty features list (omit --features) means "full version" (all gates open).
max_tags omitted means unlimited tags.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

# Import the shared signing helper so the tool and the backend never drift.
_BACKEND = Path(__file__).resolve().parent.parent / "scada-reporter" / "backend"
sys.path.insert(0, str(_BACKEND))

from app.core.license import build_license_token, verify_license_token  # noqa: E402


def _write_pem(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    # Private keys must not be world-readable; best-effort on POSIX, no-op on Win.
    with contextlib.suppress(OSError, NotImplementedError):
        os.chmod(path, 0o600)


def cmd_keygen(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.name

    if args.type == "rsa":
        key = rsa.generate_private_key(public_exponent=65537, key_size=args.rsa_bits)
        algo_hint = "RS256"
    else:
        key = ec.generate_private_key(ec.SECP256R1())
        algo_hint = "ES256"

    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    priv_path = out_dir / f"{name}_private.pem"
    pub_path = out_dir / f"{name}_public.pem"
    _write_pem(priv_path, priv_pem)
    pub_path.write_bytes(pub_pem)

    print(f"Private key: {priv_path}  (KEEP SECRET — never ship to customers)")
    print(f"Public key:  {pub_path}")
    print(f"Use --algorithm {algo_hint} when issuing with this key.")
    return 0


def _expiry_timestamp(args: argparse.Namespace) -> int | None:
    if args.expires is not None:
        return int(args.expires)
    if args.days is not None:
        return int((datetime.now(UTC) + timedelta(days=args.days)).timestamp())
    return None


def cmd_issue(args: argparse.Namespace) -> int:
    private_key = Path(args.private_key).read_text(encoding="utf-8")
    features = [f.strip() for f in (args.features or "").split(",") if f.strip()]
    expires_at = _expiry_timestamp(args)

    token = build_license_token(
        private_key=private_key,
        algorithm=args.algorithm,
        customer=args.customer,
        product=args.product,
        license_id=args.license_id,
        features=features,
        max_tags=args.max_tags,
        expires_at=expires_at,
    )

    # Fail loudly if the freshly minted token would not verify with its own
    # public key — catches algorithm/key mismatches before the customer does.
    if args.public_key:
        public_key = Path(args.public_key).read_text(encoding="utf-8")
        info = verify_license_token(
            token=token,
            public_key=public_key,
            algorithms=[args.algorithm],
            expected_product=args.product,
        )
        print(f"Self-check OK — verifies as customer={info.customer!r}")

    if args.out:
        Path(args.out).write_text(token + "\n", encoding="utf-8")
        print(f"License written: {args.out}")
    else:
        print(token)

    exp_str = (
        datetime.fromtimestamp(expires_at, UTC).isoformat()
        if expires_at
        else "never (perpetual)"
    )
    print("── license summary ─────────────────────────────")
    print(f"  customer   : {args.customer}")
    print(f"  license_id : {args.license_id or '-'}")
    print(f"  product    : {args.product}")
    print(f"  features   : {features or '(empty → full version)'}")
    print(
        f"  max_tags   : {args.max_tags if args.max_tags is not None else 'unlimited'}"
    )
    print(f"  expires    : {exp_str}")
    print("── deploy on customer backend ──────────────────")
    print("  SCADA_LICENSE_REQUIRED=true")
    print("  SCADA_LICENSE_FILE=/etc/ekont-smart-report/license.jwt")
    print(f"  SCADA_LICENSE_ALGORITHMS={args.algorithm}")
    print("  SCADA_LICENSE_PUBLIC_KEY=<paste public.pem, newlines as \\n>")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_license.py",
        description="Generate signing keys and issue EKONT SMART REPORT licenses.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    kg = sub.add_parser("keygen", help="Generate an RSA or EC signing keypair.")
    kg.add_argument(
        "--type", choices=["rsa", "ec"], default="rsa", help="Key type (default rsa)."
    )
    kg.add_argument(
        "--rsa-bits", type=int, default=2048, help="RSA key size (default 2048)."
    )
    kg.add_argument(
        "--out-dir", default=".", help="Output directory (default current dir)."
    )
    kg.add_argument(
        "--name", default="license", help="Filename stem (default 'license')."
    )
    kg.set_defaults(func=cmd_keygen)

    iss = sub.add_parser("issue", help="Sign a license token from claims.")
    iss.add_argument(
        "--private-key", required=True, help="Path to the PEM private key."
    )
    iss.add_argument("--algorithm", choices=["RS256", "ES256"], required=True)
    iss.add_argument("--customer", required=True, help="Customer name (required).")
    iss.add_argument("--license-id", default="", help="License id / serial.")
    iss.add_argument(
        "--product", default="ekont-smart-report", help="Product id claim."
    )
    iss.add_argument("--features", default="", help="Comma-separated feature keys.")
    iss.add_argument(
        "--max-tags", type=int, default=None, help="Max tag count (default unlimited)."
    )
    grp = iss.add_mutually_exclusive_group()
    grp.add_argument(
        "--days", type=int, default=None, help="Valid for N days from now."
    )
    grp.add_argument(
        "--expires", type=int, default=None, help="Absolute expiry (unix seconds)."
    )
    iss.add_argument(
        "--out", default=None, help="Write token to file (default stdout)."
    )
    iss.add_argument(
        "--public-key", default=None, help="Public PEM to self-verify the token."
    )
    iss.set_defaults(func=cmd_issue)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
