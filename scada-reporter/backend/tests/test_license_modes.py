"""License mode state machine + mode-aware enforcement helpers.

Three modes:
- UNLICENSED: dev/full — no public key configured, everything allowed.
- LICENSED:   valid token — features/quota per claims.
- DEMO:       deployment without a valid license — read-only, gated features off,
              tag visibility capped.
"""

import pytest

from app.core.license import (
    DEMO_MAX_TAGS_DEFAULT,
    LicenseInfo,
    LicenseMode,
    active_tag_quota,
    demo_visible_tag_limit,
    feature_allowed,
    get_active_license,
    get_license_state,
    is_writable,
    license_status_summary,
    set_active_license,
    set_demo_mode,
)


def _info(*, features=(), max_tags=None) -> LicenseInfo:
    return LicenseInfo(
        license_id="lic_1",
        customer="ACME",
        product="ekont-smart-report",
        features=tuple(features),
        max_tags=max_tags,
        expires_at=None,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    set_active_license(None)
    yield
    set_active_license(None)


# ── mode transitions ─────────────────────────────────────────────────────────


def test_default_mode_is_unlicensed():
    assert get_license_state().mode is LicenseMode.UNLICENSED
    assert get_active_license() is None


def test_set_active_license_sets_licensed_mode():
    info = _info(features=["export"])
    set_active_license(info)
    assert get_license_state().mode is LicenseMode.LICENSED
    assert get_active_license() is info


def test_set_active_license_none_is_unlicensed():
    set_active_license(_info())
    set_active_license(None)
    assert get_license_state().mode is LicenseMode.UNLICENSED


def test_set_demo_mode():
    set_demo_mode()
    assert get_license_state().mode is LicenseMode.DEMO
    assert get_active_license() is None


# ── feature gating by mode ───────────────────────────────────────────────────


def test_unlicensed_allows_every_feature():
    assert feature_allowed("advanced_reports") is True
    assert feature_allowed("grafana") is True


def test_licensed_honors_feature_list():
    set_active_license(_info(features=["export"]))
    assert feature_allowed("export") is True
    assert feature_allowed("grafana") is False


def test_licensed_empty_features_is_full():
    set_active_license(_info(features=[]))
    assert feature_allowed("grafana") is True


def test_demo_denies_all_gated_features():
    set_demo_mode()
    for f in ("advanced_reports", "grafana", "realtime", "export"):
        assert feature_allowed(f) is False


# ── tag quota by mode ────────────────────────────────────────────────────────


def test_unlicensed_quota_unlimited():
    assert active_tag_quota() is None


def test_licensed_quota_from_claim():
    set_active_license(_info(max_tags=500))
    assert active_tag_quota() == 500


def test_licensed_quota_none_when_claim_absent():
    set_active_license(_info(max_tags=None))
    assert active_tag_quota() is None


def test_demo_quota_is_demo_cap():
    set_demo_mode()
    assert active_tag_quota() == DEMO_MAX_TAGS_DEFAULT


def test_demo_quota_custom_cap():
    set_demo_mode(demo_max_tags=10)
    assert active_tag_quota() == 10


# ── read-only by mode ────────────────────────────────────────────────────────


def test_unlicensed_and_licensed_are_writable():
    assert is_writable() is True
    set_active_license(_info())
    assert is_writable() is True


def test_demo_is_read_only():
    set_demo_mode()
    assert is_writable() is False


# ── visible tag limit ────────────────────────────────────────────────────────


def test_demo_visible_tag_limit_set():
    set_demo_mode(demo_max_tags=25)
    assert demo_visible_tag_limit() == 25


def test_non_demo_has_no_visible_limit():
    assert demo_visible_tag_limit() is None
    set_active_license(_info(max_tags=5))
    assert demo_visible_tag_limit() is None


# ── status summary ───────────────────────────────────────────────────────────


def test_status_summary_unlicensed():
    s = license_status_summary()
    assert s["mode"] == "unlicensed"
    assert s["licensed"] is False
    assert s["customer"] is None
    assert s["features"] == []


def test_status_summary_licensed():
    set_active_license(_info(features=["export"], max_tags=500))
    s = license_status_summary()
    assert s["mode"] == "licensed"
    assert s["licensed"] is True
    assert s["customer"] == "ACME"
    assert s["features"] == ["export"]
    assert s["max_tags"] == 500


def test_status_summary_demo():
    set_demo_mode(demo_max_tags=25)
    s = license_status_summary()
    assert s["mode"] == "demo"
    assert s["licensed"] is False
    assert s["demo_max_tags"] == 25
