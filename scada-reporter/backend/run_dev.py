"""Dev server launcher.

Bypasses uvicorn's Click CLI on purpose. On Windows, Click's
``_expand_args`` runs ``glob.glob()`` over argv, so ``--reload-exclude "*.db"``
gets expanded to the literal db filenames whenever db files exist in the CWD
(scada_reporter.db, stray *.db artifacts), which then crashes argument parsing
with "Got unexpected extra argument". Calling ``uvicorn.run`` directly passes
``reload_excludes`` as a real list — no shell/Click globbing involved.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=["app"],
        reload_excludes=["*.db", "*.db-wal", "*.db-shm"],
    )
