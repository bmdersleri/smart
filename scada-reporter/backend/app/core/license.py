from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jose import JWTError, jwt

DEMO_MAX_TAGS_DEFAULT = 25


class LicenseError(RuntimeError):
    """Raised when commercial license verification fails."""


class LicenseLimitError(LicenseError):
    """Raised when an operation exceeds the active license limits (features/quota)."""


@dataclass(frozen=True)
class LicenseInfo:
    license_id: str
    customer: str
    product: str
    features: tuple[str, ...]
    max_tags: int | None
    expires_at: int | None


def _normalize_key(key: str) -> str:
    return key.replace("\\n", "\n").strip()


def extract_license_token(raw: str) -> str:
    """Pull the JWT out of raw license content — a bare token or a JSON wrapper."""
    raw = raw.strip()
    if not raw:
        raise LicenseError("License content is empty.")
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LicenseError("License JSON is invalid.") from exc
        token = data.get("license") or data.get("token")
        if not isinstance(token, str) or not token.strip():
            raise LicenseError("License JSON must contain a 'license' or 'token' string.")
        return token.strip()
    return raw


def _read_license_token(path: str) -> str:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise LicenseError(f"License file cannot be read: {path}") from exc
    return extract_license_token(raw)


def build_license_token(
    *,
    private_key: str,
    algorithm: str,
    customer: str,
    product: str = "ekont-smart-report",
    license_id: str = "",
    features: Any = (),
    max_tags: int | None = None,
    expires_at: int | None = None,
) -> str:
    """Sign a commercial license JWT (vendor side; inverse of verify_license_token).

    ``private_key`` is the PEM private key matching the public key shipped to the
    customer. ``expires_at`` is a Unix timestamp (seconds); omit for a perpetual
    license. The resulting token is verified by :func:`verify_license_token`.
    """
    if algorithm.lower() == "none":
        raise LicenseError("Unsigned license tokens are not allowed.")
    if not private_key.strip():
        raise LicenseError("License private key is missing.")
    if not customer.strip():
        raise LicenseError("License customer is required.")

    feature_list = [str(f) for f in features]
    if max_tags is not None and (not isinstance(max_tags, int) or max_tags < 0):
        raise LicenseError("max_tags must be a non-negative integer.")

    payload: dict[str, Any] = {
        "product": product,
        "customer": customer,
        "license_id": license_id,
        "features": feature_list,
    }
    if max_tags is not None:
        payload["max_tags"] = max_tags
    if expires_at is not None:
        payload["exp"] = expires_at

    return jwt.encode(payload, _normalize_key(private_key), algorithm=algorithm)


def _payload_to_info(payload: dict[str, Any], expected_product: str) -> LicenseInfo:
    product = str(payload.get("product") or "")
    if product != expected_product:
        raise LicenseError(
            f"License product mismatch: expected {expected_product!r}, got {product!r}."
        )

    features = payload.get("features") or []
    if not isinstance(features, list) or not all(isinstance(item, str) for item in features):
        raise LicenseError("License 'features' claim must be a list of strings.")

    max_tags = payload.get("max_tags")
    if max_tags is not None and (not isinstance(max_tags, int) or max_tags < 0):
        raise LicenseError("License 'max_tags' claim must be a non-negative integer.")

    return LicenseInfo(
        license_id=str(payload.get("license_id") or payload.get("jti") or ""),
        customer=str(payload.get("customer") or payload.get("sub") or ""),
        product=product,
        features=tuple(features),
        max_tags=max_tags,
        expires_at=payload.get("exp") if isinstance(payload.get("exp"), int) else None,
    )


def verify_license_token(
    token: str,
    public_key: str,
    algorithms: list[str],
    expected_product: str,
) -> LicenseInfo:
    if not token.strip():
        raise LicenseError("License token is missing.")
    if not public_key.strip():
        raise LicenseError("License public key is missing.")
    if not algorithms:
        raise LicenseError("At least one license signing algorithm is required.")
    if any(algorithm.lower() == "none" for algorithm in algorithms):
        raise LicenseError("Unsigned license tokens are not allowed.")

    try:
        payload = jwt.decode(
            token.strip(),
            _normalize_key(public_key),
            algorithms=algorithms,
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise LicenseError("License token signature or claims are invalid.") from exc

    return _payload_to_info(payload, expected_product)


# ── Runtime enforcement ──────────────────────────────────────────────────────
#
# The active license state is resolved once at startup (and again on upload) and
# cached here so request handlers can enforce feature gating, tag quota, and the
# demo read-only rule without re-reading the token.


class LicenseMode(enum.StrEnum):
    """Runtime licensing mode."""

    UNLICENSED = "unlicensed"  # dev/full — no public key configured, all allowed
    LICENSED = "licensed"  # valid token — features/quota per claims
    DEMO = "demo"  # deployment without a valid license — read-only, gated off


@dataclass(frozen=True)
class LicenseState:
    mode: LicenseMode
    info: LicenseInfo | None = None
    demo_max_tags: int = DEMO_MAX_TAGS_DEFAULT


_state: LicenseState = LicenseState(LicenseMode.UNLICENSED)


def set_active_license(info: LicenseInfo | None) -> None:
    """Activate a verified license, or clear it.

    A non-``None`` ``info`` sets LICENSED mode; ``None`` resets to UNLICENSED
    (dev/full). Backward-compatible with the original single-license API.
    """
    global _state
    _state = (
        LicenseState(LicenseMode.LICENSED, info) if info else LicenseState(LicenseMode.UNLICENSED)
    )


def set_demo_mode(demo_max_tags: int = DEMO_MAX_TAGS_DEFAULT) -> None:
    """Enter DEMO mode: read-only, gated features off, tag visibility capped."""
    global _state
    _state = LicenseState(LicenseMode.DEMO, None, demo_max_tags)


def get_license_state() -> LicenseState:
    """Return the current license state (mode + info)."""
    return _state


def get_active_license() -> LicenseInfo | None:
    """Return the active license info, or ``None`` when none is active."""
    return _state.info


def feature_allowed(feature: str) -> bool:
    """Whether ``feature`` is permitted in the current mode.

    UNLICENSED → all allowed; LICENSED → per the license; DEMO → all gated
    features are denied.
    """
    if _state.mode is LicenseMode.DEMO:
        return False
    return license_allows_feature(_state.info, feature)


def active_tag_quota() -> int | None:
    """Current tag cap, or ``None`` for unlimited.

    DEMO → demo cap; LICENSED → ``max_tags`` claim; UNLICENSED → unlimited.
    """
    if _state.mode is LicenseMode.DEMO:
        return _state.demo_max_tags
    return _state.info.max_tags if _state.info else None


def is_writable() -> bool:
    """Whether mutating operations are allowed (DEMO is read-only)."""
    return _state.mode is not LicenseMode.DEMO


def demo_visible_tag_limit() -> int | None:
    """Tag-list visibility cap in DEMO mode, else ``None``."""
    return _state.demo_max_tags if _state.mode is LicenseMode.DEMO else None


def license_status_summary() -> dict[str, Any]:
    """Serializable status for the dashboard badge and Settings page."""
    info = _state.info
    return {
        "mode": _state.mode.value,
        "licensed": _state.mode is LicenseMode.LICENSED,
        "customer": info.customer if info else None,
        "license_id": info.license_id if info else None,
        "product": info.product if info else None,
        "features": list(info.features) if info else [],
        "max_tags": active_tag_quota(),
        "expires_at": info.expires_at if info else None,
        "demo_max_tags": _state.demo_max_tags if _state.mode is LicenseMode.DEMO else None,
    }


def license_allows_feature(info: LicenseInfo | None, feature: str) -> bool:
    """Whether ``feature`` is permitted under ``info``.

    Unrestricted (``info is None``) and an empty ``features`` claim both mean
    "full version" — every feature is allowed. A non-empty ``features`` claim is
    an allow-list: only listed features pass.
    """
    if info is None:
        return True
    if not info.features:
        return True
    return feature in info.features


def enforce_feature(info: LicenseInfo | None, feature: str) -> None:
    """Raise :class:`LicenseLimitError` if ``feature`` is not licensed."""
    if not license_allows_feature(info, feature):
        raise LicenseLimitError(f"License does not include the '{feature}' feature.")


def enforce_tag_quota(info: LicenseInfo | None, current_count: int, adding: int) -> None:
    """Raise :class:`LicenseLimitError` if adding tags would exceed ``max_tags``.

    No license or no ``max_tags`` claim means unlimited.
    """
    if info is None or info.max_tags is None:
        return
    if current_count + adding > info.max_tags:
        raise LicenseLimitError(
            f"License tag limit reached: max_tags={info.max_tags}, "
            f"current={current_count}, requested=+{adding}."
        )


def verify_required_license(settings: Any) -> LicenseInfo | None:
    if not settings.SCADA_LICENSE_REQUIRED:
        return None

    token = settings.SCADA_LICENSE_TOKEN.strip()
    if not token and settings.SCADA_LICENSE_FILE.strip():
        token = _read_license_token(settings.SCADA_LICENSE_FILE.strip())

    algorithms = settings.scada_license_algorithms
    return verify_license_token(
        token=token,
        public_key=settings.SCADA_LICENSE_PUBLIC_KEY,
        algorithms=algorithms,
        expected_product=settings.SCADA_LICENSE_PRODUCT,
    )


def initialize_license_state(settings: Any) -> LicenseState:
    """Resolve and activate the startup license mode from settings.

    - ``SCADA_LICENSE_REQUIRED`` → strict: LICENSED, or raise (fail-closed).
    - public key configured + valid license → LICENSED.
    - public key configured + missing/invalid license → DEMO.
    - no public key configured → UNLICENSED (dev/full).
    """
    if settings.SCADA_LICENSE_REQUIRED:
        set_active_license(verify_required_license(settings))
        return get_license_state()

    if not settings.SCADA_LICENSE_PUBLIC_KEY.strip():
        set_active_license(None)
        return get_license_state()

    demo_max = int(settings.SCADA_LICENSE_DEMO_MAX_TAGS)
    try:
        token = settings.SCADA_LICENSE_TOKEN.strip()
        if not token and settings.SCADA_LICENSE_FILE.strip():
            token = _read_license_token(settings.SCADA_LICENSE_FILE.strip())
        if not token:
            set_demo_mode(demo_max)
            return get_license_state()
        info = verify_license_token(
            token=token,
            public_key=settings.SCADA_LICENSE_PUBLIC_KEY,
            algorithms=settings.scada_license_algorithms,
            expected_product=settings.SCADA_LICENSE_PRODUCT,
        )
        set_active_license(info)
    except LicenseError:
        set_demo_mode(demo_max)
    return get_license_state()
