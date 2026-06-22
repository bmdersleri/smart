from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jose import JWTError, jwt


class LicenseError(RuntimeError):
    """Raised when commercial license verification fails."""


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


def _read_license_token(path: str) -> str:
    try:
        raw = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise LicenseError(f"License file cannot be read: {path}") from exc
    if not raw:
        raise LicenseError("License file is empty.")
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LicenseError("License file JSON is invalid.") from exc
        token = data.get("license") or data.get("token")
        if not isinstance(token, str) or not token.strip():
            raise LicenseError("License file must contain a 'license' or 'token' string.")
        return token.strip()
    return raw


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
