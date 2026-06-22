"""Production/service server launcher.

Like run_dev.py but with reload DISABLED. The dev reloader spawns a child
watcher process; under a Windows service (NSSM) that orphans the child on
stop. A single uvicorn process is what the service manager should own.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
    )
