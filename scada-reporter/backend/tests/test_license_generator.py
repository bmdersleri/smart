"""Vendor-side license signing: build_license_token round-trips through verify.

build_license_token is the inverse of verify_license_token — the vendor signs a
token with the PRIVATE key; the deployed backend verifies it with the matching
PUBLIC key. These tests prove the two halves agree.
"""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from app.core.license import (
    LicenseError,
    build_license_token,
    verify_license_token,
)

PRODUCT = "ekont-smart-report"


def _rsa_pem() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return priv, pub


def _ec_pem() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return priv, pub


def test_rs256_token_roundtrips_through_verify():
    priv, pub = _rsa_pem()
    exp = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    token = build_license_token(
        private_key=priv,
        algorithm="RS256",
        customer="ACME Water",
        license_id="lic_42",
        features=["export", "grafana"],
        max_tags=500,
        expires_at=exp,
    )

    info = verify_license_token(
        token=token,
        public_key=pub,
        algorithms=["RS256"],
        expected_product=PRODUCT,
    )

    assert info.customer == "ACME Water"
    assert info.license_id == "lic_42"
    assert info.features == ("export", "grafana")
    assert info.max_tags == 500
    assert info.expires_at == exp


def test_es256_token_roundtrips_through_verify():
    priv, pub = _ec_pem()
    token = build_license_token(
        private_key=priv,
        algorithm="ES256",
        customer="Plant B",
    )
    info = verify_license_token(
        token=token, public_key=pub, algorithms=["ES256"], expected_product=PRODUCT
    )
    assert info.customer == "Plant B"


def test_token_without_max_tags_is_unlimited():
    priv, pub = _rsa_pem()
    token = build_license_token(private_key=priv, algorithm="RS256", customer="X")
    info = verify_license_token(
        token=token, public_key=pub, algorithms=["RS256"], expected_product=PRODUCT
    )
    assert info.max_tags is None
    assert info.features == ()


def test_expired_token_is_rejected_by_verify():
    priv, pub = _rsa_pem()
    past = int((datetime.now(UTC) - timedelta(days=1)).timestamp())
    token = build_license_token(private_key=priv, algorithm="RS256", customer="X", expires_at=past)
    with pytest.raises(LicenseError):
        verify_license_token(
            token=token, public_key=pub, algorithms=["RS256"], expected_product=PRODUCT
        )


def test_wrong_public_key_is_rejected():
    priv, _ = _rsa_pem()
    _, other_pub = _rsa_pem()
    token = build_license_token(private_key=priv, algorithm="RS256", customer="X")
    with pytest.raises(LicenseError):
        verify_license_token(
            token=token, public_key=other_pub, algorithms=["RS256"], expected_product=PRODUCT
        )


def test_build_rejects_none_algorithm():
    with pytest.raises(LicenseError, match="[Uu]nsigned|none"):
        build_license_token(private_key="x", algorithm="none", customer="X")


def test_build_requires_customer():
    priv, _ = _rsa_pem()
    with pytest.raises(LicenseError, match="[Cc]ustomer"):
        build_license_token(private_key=priv, algorithm="RS256", customer="")
