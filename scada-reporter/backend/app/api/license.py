"""License status + runtime upload (hot-reload) + revert to demo.

The public key stays vendor-provisioned in the environment; only the signed
``license.jwt`` is uploaded here. A valid upload is verified against that key,
optionally persisted to ``SCADA_LICENSE_FILE``, and activated without a restart.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.api.auth import get_current_user, require_role
from app.core.config import settings
from app.core.license import (
    LicenseError,
    extract_license_token,
    license_status_summary,
    set_active_license,
    set_demo_mode,
    verify_license_token,
)

router = APIRouter(prefix="/license", tags=["license"])


@router.get("")
async def license_status(_=Depends(get_current_user)) -> dict:
    """Current license mode + claims — for the dashboard badge and Settings."""
    return license_status_summary()


@router.post("")
async def upload_license(file: UploadFile, _=Depends(require_role("admin"))) -> dict:
    """Verify an uploaded license against the configured public key and activate it."""
    if not settings.SCADA_LICENSE_PUBLIC_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No license public key is configured on the server.",
        )

    raw = (await file.read()).decode("utf-8", errors="replace")
    try:
        token = extract_license_token(raw)
        info = verify_license_token(
            token=token,
            public_key=settings.SCADA_LICENSE_PUBLIC_KEY,
            algorithms=settings.scada_license_algorithms,
            expected_product=settings.SCADA_LICENSE_PRODUCT,
        )
    except LicenseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    persisted = False
    target = settings.SCADA_LICENSE_FILE.strip()
    if target:
        try:
            Path(target).write_text(token + "\n", encoding="utf-8")
            persisted = True
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"License verified but could not be saved to {target}: {exc}",
            ) from exc

    set_active_license(info)
    return {**license_status_summary(), "persisted": persisted}


@router.delete("")
async def revert_license(_=Depends(require_role("admin"))) -> dict:
    """Remove the active license and fall back to DEMO mode."""
    target = settings.SCADA_LICENSE_FILE.strip()
    if target:
        Path(target).unlink(missing_ok=True)
    set_demo_mode(int(settings.SCADA_LICENSE_DEMO_MAX_TAGS))
    return license_status_summary()
