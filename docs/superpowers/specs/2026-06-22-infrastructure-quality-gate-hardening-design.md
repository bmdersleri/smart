# Infrastructure Quality Gate Hardening — Design Spec

**Date:** 2026-06-22
**Status:** Implemented
**Scope:** Local quality gate parity with CI, backend security scan inclusion, and local OpenAPI contract freshness checks. No product behavior changes.

## Goal

Make the repository's local infrastructure checks match the checks that already protect CI. A developer or agent should be able to run one local command before a PR and catch the same classes of infrastructure drift that GitHub Actions catches: backend lint/type/test/security, frontend type/lint/test, agent CLI tests, MCP tests, and generated OpenAPI client freshness.

## Current State

- GitHub Actions already runs backend Bandit security scanning.
- The root `justfile` has a `backend-security` recipe, but `backend-check` does not include it because Bandit still reports one `B608` finding in `app/services/grafana_sync.py`.
- GitHub Actions has a `contract-freshness` job that regenerates `frontend/openapi.json` and `frontend/src/api/generated`, then fails on drift.
- The root `justfile` has `dump-openapi` and `gen-client`, but no local recipe that asserts the generated contract is committed and fresh.
- `just check` covers backend, frontend, CLI, and MCP, but not contract freshness and not backend security.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Bandit finding strategy | Validate `group_id` as an integer and mark the generated Grafana SQL line with a narrow `# nosec B608` | Grafana dashboard SQL is static JSON text, not a live SQLAlchemy execution path. Runtime `int()` coercion rejects non-integer input, and the suppressing comment is scoped to the one false positive. |
| Local security gate | Add `backend-security` to `backend-check` | CI already requires Bandit, so local backend checks should fail on the same issue class. |
| Local contract gate | Add `contract-check` recipe | CI already checks generated OpenAPI freshness; local workflows need the same explicit gate. |
| Unified check | Add `contract-check` to `check` | The single pre-PR local command should cover CI-equivalent infrastructure checks. |

## Architecture

### 1. Grafana dashboard SQL hardening

`build_group_dashboard()` emits dashboard JSON consumed by Grafana's SQLite datasource. The SQL text has to be embedded in the dashboard model, so normal DB driver bind parameters are not available at application runtime.

The query builder will:

- Coerce `group_id` through `int(group_id)` before interpolation.
- Keep the resulting SQL shape unchanged for Grafana.
- Use a scoped `# nosec B608` on the interpolation line because the value is now runtime-validated as an integer.
- Add a regression test proving non-integer `group_id` values are rejected before dashboard SQL is produced.

### 2. Local backend security gate

`backend-check` will depend on:

- `lint`
- `format-check`
- `typecheck`
- `test`
- `backend-security`

This makes local backend checks match CI's backend job more closely.

### 3. Local contract freshness gate

Add a `contract-check` recipe that:

1. Runs `gen-client`, which dumps OpenAPI and regenerates the TypeScript client.
2. Runs `git diff --exit-code -- scada-reporter/frontend/openapi.json scada-reporter/frontend/src/api/generated`.

If generated artifacts drift, the command fails locally the same way CI fails.

### 4. Unified local check

`check` will include:

- `backend-check`
- `frontend-check`
- `cli-check`
- `mcp-check`
- `contract-check`

## Acceptance Criteria

- `bandit -r app/ -ll` exits successfully from `scada-reporter/backend`.
- `backend-check` includes backend security scanning.
- `contract-check` exists and fails on uncommitted OpenAPI/generated-client drift.
- `check` includes `contract-check`.
- Existing Grafana dashboard SQL shape remains compatible with current tests.
- A regression test rejects non-integer `group_id` input.

## Out of Scope

- Production Dockerfiles or production Compose topology.
- Alerting rule provisioning.
- Rewriting Grafana datasource queries to a different query model.
- Large frontend generated-client migration work.
