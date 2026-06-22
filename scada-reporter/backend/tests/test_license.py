from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.core.config import Settings
from app.core.license import LicenseError, verify_license_token, verify_required_license


def _token(**claims):
    payload = {
        "product": "ekont-smart-report",
        "customer": "Demo Customer",
        "license_id": "lic_test",
        "features": ["reports"],
        "max_tags": 100,
        "exp": datetime.now(UTC) + timedelta(days=30),
        **claims,
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def test_license_disabled_returns_none():
    settings = Settings(_env_file=None, SCADA_LICENSE_REQUIRED=False)
    assert verify_required_license(settings) is None


def test_valid_license_token_returns_info():
    info = verify_license_token(
        token=_token(),
        public_key="test-secret",
        algorithms=["HS256"],
        expected_product="ekont-smart-report",
    )

    assert info.license_id == "lic_test"
    assert info.customer == "Demo Customer"
    assert info.features == ("reports",)
    assert info.max_tags == 100


def test_required_license_rejects_missing_public_key():
    settings = Settings(
        _env_file=None,
        SCADA_LICENSE_REQUIRED=True,
        SCADA_LICENSE_TOKEN=_token(),
        SCADA_LICENSE_PUBLIC_KEY="",
        SCADA_LICENSE_ALGORITHMS="HS256",
    )

    with pytest.raises(LicenseError, match="public key"):
        verify_required_license(settings)


def test_license_rejects_wrong_product():
    with pytest.raises(LicenseError, match="product mismatch"):
        verify_license_token(
            token=_token(product="other-product"),
            public_key="test-secret",
            algorithms=["HS256"],
            expected_product="ekont-smart-report",
        )
