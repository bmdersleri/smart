"""DB health helpers for /ready endpoint.

Provides:
- db_ok()              : async SELECT 1 probe
- alembic_head_matches(): compare script head to DB's applied revision
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Alembic ini is at the backend root (one level above this package).
_BACKEND_DIR = Path(__file__).parent.parent.parent  # …/backend


async def db_ok() -> bool:
    """Return True if the DB responds to SELECT 1, False on any error."""
    from app.core.database import engine  # local import to avoid circular

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("db_ok probe failed")
        return False


def alembic_head_matches() -> bool:
    """Return True if the DB's current Alembic revision matches the script head.

    Tolerance rules:
    - If the alembic_version table does not exist (dev/test using create_all),
      treat as OK (return True) — not a migration failure.
    - Only return False when alembic_version exists AND differs from script head.
    - Any unexpected error → True (fail-open; don't block readiness on probe issues).
    """
    try:
        import alembic.config as alembic_config_mod
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        ini_file = _BACKEND_DIR / "alembic.ini"
        cfg = alembic_config_mod.Config(str(ini_file))
        # Override script_location to be absolute so it works regardless of cwd.
        cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))

        script = ScriptDirectory.from_config(cfg)
        head_rev = script.get_current_head()

        # Use a sync connection from the async engine's sync_engine.
        from app.core.database import engine  # local import

        sync_eng = engine.sync_engine
        with sync_eng.connect() as conn:
            # Check whether alembic_version table exists.
            from sqlalchemy import inspect as sa_inspect

            insp = sa_inspect(conn)
            if "alembic_version" not in insp.get_table_names():
                # Dev/test scenario: create_all was used, no migrations applied.
                return True

            mig_ctx = MigrationContext.configure(conn)
            current_rev = mig_ctx.get_current_revision()

        return current_rev == head_rev
    except Exception:
        logger.exception("alembic_head_matches probe failed — treating as OK")
        return True
