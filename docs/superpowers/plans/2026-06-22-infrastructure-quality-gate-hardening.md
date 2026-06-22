# Infrastructure Quality Gate Hardening — Implementation Plan

**Goal:** Implement `2026-06-22-infrastructure-quality-gate-hardening-design.md` by making local checks include backend security and OpenAPI contract freshness.

**Tech Stack:** FastAPI backend, pytest, Bandit, React/Vite frontend, OpenAPI TypeScript generator, root `justfile`, GitHub Actions parity.

## Tasks

- [x] **Task 1: Harden Grafana dashboard query generation**
  - Read `app/services/grafana_sync.py` and `tests/test_grafana_sync.py`.
  - Coerce `group_id` to `int` inside `_query()`.
  - Keep the generated SQL text stable for integer values.
  - Add a narrow `# nosec B608` only to the validated interpolation line.
  - Add a regression test that non-integer `group_id` input raises `ValueError` or `TypeError`.

- [x] **Task 2: Verify Bandit is green**
  - Run from `scada-reporter/backend`: `.venv/Scripts/bandit.exe -r app/ -ll`.
  - Confirm exit code 0.

- [x] **Task 3: Promote backend security into the local backend gate**
  - Update `justfile` so `backend-check` includes `backend-security`.
  - Remove the stale note saying Bandit is intentionally excluded because of the pre-existing finding.

- [x] **Task 4: Add local contract freshness check**
  - Add a `contract-check` recipe after `gen-client`.
  - The recipe should regenerate OpenAPI/client artifacts and run:
    `git diff --exit-code -- scada-reporter/frontend/openapi.json scada-reporter/frontend/src/api/generated`.

- [x] **Task 5: Promote contract freshness into the unified local gate**
  - Update `check` so it depends on `backend-check frontend-check cli-check mcp-check contract-check`.

- [x] **Task 6: Verify**
  - Run `pytest tests/test_grafana_sync.py -q`.
  - Run Bandit.
  - Run a lightweight `just` parse/list command if available.
  - Do not run the full frontend/backend suite unless needed; this change is narrowly scoped.

## Definition of Done

- Spec and plan exist in English.
- The Bandit false positive is closed through runtime integer validation plus a scoped suppression.
- Local backend checks now include security scanning.
- Local unified checks now include OpenAPI contract freshness.
- Targeted Grafana sync tests and Bandit pass.
