# Release Policy — EKONT SMART REPORT

## Versioning scheme

EKONT SMART REPORT follows [Semantic Versioning 2.0.0](https://semver.org/) (`vMAJOR.MINOR.PATCH`).

| Segment | Increment when… |
|---------|-----------------|
| **MAJOR** | Backward-incompatible API or DB schema changes; breaking changes to the agent CLI contract; removal of previously-supported features. |
| **MINOR** | New features added in a backward-compatible way (new endpoints, new CLI commands, new MCP tools, new dashboard pages). |
| **PATCH** | Backward-compatible bug fixes, security patches, documentation corrections, dependency updates with no API change. |

Pre-release suffixes (`-rc.1`, `-beta.1`) may be appended for release candidates.

---

## Single-product version strategy

All components of the monorepo share **one version tag** (`vX.Y.Z`).

| Component | Authoritative location |
|-----------|------------------------|
| Backend (FastAPI) | `scada-reporter/backend/pyproject.toml` — `[project] version` |
| Frontend (React) | `scada-reporter/frontend/package.json` — `"version"` |
| scada-core package | `scada-reporter/packages/scada-core/pyproject.toml` — `[project] version` |
| Agent CLI harness | `scada-reporter/agent-harness/setup.py` — `version=` |

Rationale: the system is deployed as a single unit (one backend + one frontend + one CLI). Separate version lines would introduce gratuitous coordination overhead with no semantic benefit.

---

## Release process

### Standard release (MINOR or PATCH)

1. **Implement and merge** all intended changes into `master` via PRs; CI must be green.

2. **Update `CHANGELOG.md`** (repo root):
   - Move every item from the `[Unreleased]` section into a new `[X.Y.Z] - YYYY-MM-DD` section.
   - Leave a fresh empty `[Unreleased]` section at the top.

3. **Bump component versions** — update all four locations listed in the table above to `X.Y.Z`.

4. **Commit** the version + changelog changes directly on `master` (or via a short-lived `release/vX.Y.Z` branch if the team prefers):
   ```
   git commit -m "chore(release): bump to vX.Y.Z"
   ```

5. **Tag and push**:
   ```
   git tag vX.Y.Z
   git push origin master --tags
   ```

6. **CI `release.yml`** triggers automatically on `v*` tags:
   - Extracts the relevant section from `CHANGELOG.md`.
   - Creates a GitHub Release at that tag with the extracted notes.

### MAJOR release

Same as above, but coordinate with all consumers of the REST API and agent CLI before publishing (breaking changes must be documented in `CHANGELOG.md` under `### Changed` or `### Removed`).

---

## Notes

- The git tag (`vX.Y.Z`) is the single source of truth for a shipped version; the component `version` fields must match it.
- Do **not** push a tag before CI is green on master.
- `CHANGELOG.md` must be updated **before** the tag is pushed so the release workflow can extract the notes.
- Hotfixes branch from the release tag (`git checkout -b hotfix/vX.Y.Z+1 vX.Y.Z`), are merged back to master, and follow the same tag + release process.
