"""
Dump the FastAPI OpenAPI schema to frontend/openapi.json WITHOUT starting the server.

Run from the backend directory with the backend venv:
    cd scada-reporter/backend
    .venv/Scripts/python ../../scripts/dump_openapi.py

The script imports the FastAPI app object and calls app.openapi() which builds the
schema in-memory — no DB connection, no scheduler, no lifespan hooks are triggered.
The resulting JSON is written to scada-reporter/frontend/openapi.json (relative to
the repo root, i.e. ../frontend/openapi.json from the backend dir).
"""

import json
import os
import sys

# Ensure we can import app.* from the current working directory (should be backend/)
sys.path.insert(0, os.getcwd())

# Set minimal env so config doesn't crash; real values not needed for schema gen.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./dummy.db")

from app.main import app  # noqa: E402

schema = app.openapi()

# Output path: relative to this script's location (repo_root/scripts/),
# go up one level then into scada-reporter/frontend/openapi.json.
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(script_dir)
out_path = os.path.join(repo_root, "scada-reporter", "frontend", "openapi.json")

# newline="\n" forces LF on all platforms (Windows text mode would emit CRLF
# and make the committed file drift vs the Linux-generated CI copy).
with open(out_path, "w", encoding="utf-8", newline="\n") as f:
    json.dump(schema, f, indent=2, ensure_ascii=False, sort_keys=True)
    f.write("\n")

print(f"OpenAPI schema written to {out_path}")
print(f"  paths: {len(schema.get('paths', {}))}")
print(f"  components/schemas: {len(schema.get('components', {}).get('schemas', {}))}")
