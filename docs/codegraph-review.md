# CodeGraph Review Workflow

CodeGraph is the preferred first pass for architecture and blast-radius review in this
repository. Use it before editing high-connectivity runtime paths such as scheduler,
authentication, report generation, query execution, upload parsing, and agent contracts.

## Basic Commands

```powershell
codegraph status
codegraph sync
codegraph query "symbol or concept"
codegraph node <symbol>
codegraph impact <symbol> --depth 3 --json
codegraph explore "<flow or feature>" --max-files 8
```

Run `codegraph sync` after branch switches or file edits when `codegraph status`
reports pending changes.

## Review Recipes

### Scheduler Runtime

```powershell
codegraph impact get_scheduler --depth 3 --json
codegraph explore "backend startup scheduler collector database readiness flow" --max-files 8
```

Use this before changing scheduler startup, readiness, scheduled reports, or process
role configuration.

### Authentication

```powershell
codegraph impact authenticate_token --depth 3 --json
codegraph explore "authentication token get_current_user require_role permissions" --max-files 8
```

Use this before changing JWT validation, role checks, permissions, stream tokens, or
frontend token handling.

### Report Generation

```powershell
codegraph impact generate_report_from_template --depth 3 --json
codegraph explore "report generation scheduled report archive generate_report_from_template" --max-files 8
```

Use this before changing report templates, archives, scheduled report execution, Excel,
PDF, JSON output, or Grafana panel rendering.

### Input Boundaries

```powershell
codegraph node run_query
codegraph explore "UploadFile tags import excel templates license upload" --max-files 8
```

Use this before changing SQL query execution, CSV/XLSX import, Excel template upload,
or license upload behavior.

### Frontend Complexity

```powershell
codegraph node Trend
codegraph node TemplateEditorModal
codegraph node Tags
codegraph node Reports
```

Use this before splitting large frontend pages. Generated OpenAPI files should be
excluded from maintainability conclusions unless the generator configuration itself is
being changed.

### Agent Contracts

```powershell
codegraph explore "agent cli scada-core MCP server resources tools SKILL" --max-files 8
```

Use this before changing `scada-core`, the agent CLI, MCP server resources/tools, or
`SKILL.md`.

## Interpretation Rules

- Treat CodeGraph as a map, not a proof. Cross-check critical claims with source and
  tests.
- Generated frontend files can dominate node and edge counts; filter them out for
  hand-written complexity analysis.
- Some TypeScript import relationships may require text verification.
- Prefer `impact` for blast radius and `explore` for flow-level context.
- After large refactors, run `codegraph sync` and repeat the relevant review recipe.

## Subagent Workflow

When delegating implementation:

- Give each subagent a disjoint file ownership scope.
- Include the relevant CodeGraph preflight command in the delegated task.
- Ask workers to list changed files and verification commands.
- Use smaller models for narrow implementation or investigation tasks.
- Keep integration and final review in the main thread.
