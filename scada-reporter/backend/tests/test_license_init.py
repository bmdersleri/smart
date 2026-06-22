"""Startup license mode resolution: initialize_license_state(settings)."""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.core.license import (
    LicenseError,
    LicenseMode,
    build_license_token,
    initialize_license_state,
    set_active_license,
)


@pytest.fixture(autouse=True)
def _reset_state():
    set_active_license(None)
    yield
    set_active_license(None)


def _keys() -> tuple[str, str]:
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = k.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = (
        k.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return priv, pub


def test_no_public_key_is_unlicensed_full():
    s = Settings(_env_file=None, SCADA_LICENSE_REQUIRED=False, SCADA_LICENSE_PUBLIC_KEY="")
    state = initialize_license_state(s)
    assert state.mode is LicenseMode.UNLICENSED


def test_public_key_no_token_is_demo():
    _, pub = _keys()
    s = Settings(
        _env_file=None,
        SCADA_LICENSE_REQUIRED=False,
        SCADA_LICENSE_PUBLIC_KEY=pub,
        SCADA_LICENSE_ALGORITHMS="RS256",
        SCADA_LICENSE_DEMO_MAX_TAGS=15,
    )
    state = initialize_license_state(s)
    assert state.mode is LicenseMode.DEMO
    assert state.demo_max_tags == 15


def test_public_key_valid_token_is_licensed():
    priv, pub = _keys()
    token = build_license_token(
        private_key=priv, algorithm="RS256", customer="ACME", features=["export"]
    )
    s = Settings(
        _env_file=None,
        SCADA_LICENSE_REQUIRED=False,
        SCADA_LICENSE_PUBLIC_KEY=pub,
        SCADA_LICENSE_ALGORITHMS="RS256",
        SCADA_LICENSE_TOKEN=token,
    )
    state = initialize_license_state(s)
    assert state.mode is LicenseMode.LICENSED
    assert state.info.customer == "ACME"


def test_public_key_invalid_token_falls_back_to_demo():
    _, pub = _keys()
    s = Settings(
        _env_file=None,
        SCADA_LICENSE_REQUIRED=False,
        SCADA_LICENSE_PUBLIC_KEY=pub,
        SCADA_LICENSE_ALGORITHMS="RS256",
        SCADA_LICENSE_TOKEN="not-a-real-jwt",
    )
    state = initialize_license_state(s)
    assert state.mode is LicenseMode.DEMO


def test_required_valid_token_is_licensed():
    priv, pub = _keys()
    token = build_license_token(private_key=priv, algorithm="RS256", customer="Strict")
    s = Settings(
        _env_file=None,
        SCADA_LICENSE_REQUIRED=True,
        SCADA_LICENSE_PUBLIC_KEY=pub,
        SCADA_LICENSE_ALGORITHMS="RS256",
        SCADA_LICENSE_TOKEN=token,
    )
    state = initialize_license_state(s)
    assert state.mode is LicenseMode.LICENSED
    assert state.info.customer == "Strict"


def test_required_invalid_token_fails_closed():
    _, pub = _keys()
    s = Settings(
        _env_file=None,
        SCADA_LICENSE_REQUIRED=True,
        SCADA_LICENSE_PUBLIC_KEY=pub,
        SCADA_LICENSE_ALGORITHMS="RS256",
        SCADA_LICENSE_TOKEN="garbage",
    )
    with pytest.raises(LicenseError):
        initialize_license_state(s)
