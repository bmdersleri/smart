"""Pure license enforcement logic: feature gating + tag quota.

These are unit tests for the runtime enforcement helpers in app.core.license.
No FastAPI / DB involved.
"""

import pytest

from app.core.license import (
    LicenseInfo,
    LicenseLimitError,
    enforce_feature,
    enforce_tag_quota,
    get_active_license,
    license_allows_feature,
    set_active_license,
)


def _info(*, features=(), max_tags=None) -> LicenseInfo:
    return LicenseInfo(
        license_id="lic",
        customer="Cust",
        product="ekont-smart-report",
        features=tuple(features),
        max_tags=max_tags,
        expires_at=None,
    )


@pytest.fixture(autouse=True)
def _reset_active_license():
    """Keep the module-global active license from leaking across tests."""
    set_active_license(None)
    yield
    set_active_license(None)


# ── runtime holder ───────────────────────────────────────────────────────────


def test_active_license_defaults_to_none():
    assert get_active_license() is None


def test_set_and_get_active_license():
    info = _info(features=["reports"], max_tags=10)
    set_active_license(info)
    assert get_active_license() is info


# ── feature gating ───────────────────────────────────────────────────────────


def test_feature_allowed_when_no_license():
    assert license_allows_feature(None, "advanced_reports") is True


def test_feature_allowed_when_features_empty():
    # Empty features claim => full version (all features open).
    assert license_allows_feature(_info(features=[]), "grafana") is True


def test_feature_allowed_when_listed():
    assert license_allows_feature(_info(features=["export"]), "export") is True


def test_feature_denied_when_not_listed():
    assert license_allows_feature(_info(features=["reports"]), "export") is False


def test_enforce_feature_passes_when_allowed():
    enforce_feature(_info(features=["export"]), "export")  # no raise


def test_enforce_feature_raises_when_denied():
    with pytest.raises(LicenseLimitError, match="export"):
        enforce_feature(_info(features=["reports"]), "export")


# ── tag quota ────────────────────────────────────────────────────────────────


def test_quota_unlimited_when_no_license():
    enforce_tag_quota(None, current_count=10_000, adding=1)  # no raise


def test_quota_unlimited_when_max_tags_none():
    enforce_tag_quota(_info(max_tags=None), current_count=10_000, adding=1)  # no raise


def test_quota_allows_up_to_limit():
    enforce_tag_quota(_info(max_tags=100), current_count=99, adding=1)  # exactly 100


def test_quota_blocks_when_exceeded_by_one():
    with pytest.raises(LicenseLimitError, match="100"):
        enforce_tag_quota(_info(max_tags=100), current_count=100, adding=1)


def test_quota_blocks_bulk_partially_over_limit():
    with pytest.raises(LicenseLimitError):
        enforce_tag_quota(_info(max_tags=100), current_count=98, adding=5)


def test_quota_allows_zero_adding_at_limit():
    enforce_tag_quota(_info(max_tags=100), current_count=100, adding=0)  # no raise
