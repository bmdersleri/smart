# EKONT SMART REPORT — Frontend

React 19 + Vite + Tailwind CSS v4 + TanStack Query web interface for the EKONT SMART REPORT system.
Talks to the FastAPI backend (`http://localhost:8001`) through a generated OpenAPI TypeScript client.
Grafana panels are embedded from `VITE_GRAFANA_URL` (`http://localhost:3000` by default). The supported local setup uses Grafana as a Windows service; see [`../../docs/grafana-windows-service.md`](../../docs/grafana-windows-service.md).

## Tech Stack

| Tool | Purpose |
|------|---------|
| React 19 | UI framework |
| Vite | Dev server + bundler |
| Tailwind CSS v4 | Styling |
| TanStack Query | Server state / data fetching |
| React Router | Routing |
| Recharts | Trend charts (multi-Y-axis, zoom/pan) |
| axios | HTTP client |
| @hey-api/openapi-ts | Generated API client from the backend OpenAPI spec |
| vitest + Testing Library | Unit tests (jsdom) |
| Playwright | E2E smoke tests |

## Structure

```
src/
├── pages/      # Dashboard, Trend, Reports, AdvancedReports, ExcelTemplates,
│               # Tags, PlcConfig, PlcHealth, Metrics, Grafana, Users, Settings, Login
├── context/    # AuthContext, SettingsContext (localStorage)
├── components/ # Layout (sidebar nav)
└── api/        # Generated OpenAPI TypeScript client
```

## Commands

**Package Manager:** Use `pnpm` only; do not use npm (the pnpm-lock.yaml is the sole lockfile).

```bash
pnpm install        # Install dependencies
pnpm dev            # Dev server (http://localhost:5173)
pnpm build          # Production build
pnpm test           # Vitest unit tests
pnpm e2e            # Playwright E2E tests
pnpm lint           # ESLint
pnpm gen-client     # Generate from existing openapi.json
```

From the project root these are also available as `just run-frontend`, `just test-fe`, `just gen-client`, etc.

## API Client Generation

The TypeScript client under `src/api/` is generated from the backend's OpenAPI spec.
Regenerate it after API changes from the project root:

```bash
just gen-client      # dumps frontend/openapi.json, then runs pnpm openapi-ts
```

If `frontend/openapi.json` is already current, you can run `pnpm gen-client` inside this directory.
Config: `openapi-ts.config.ts`.
