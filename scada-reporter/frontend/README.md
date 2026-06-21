# EKONT SMART REPORT — Frontend

React 19 + Vite + Tailwind CSS v4 + TanStack Query web interface for the EKONT SMART REPORT system.
Talks to the FastAPI backend (`http://localhost:8001`) through a generated OpenAPI TypeScript client.

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

## Structure

```
src/
├── pages/      # Dashboard, Trend, Reports, AdvancedReports, Tags, PlcConfig, Settings, Login
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
pnpm lint           # ESLint
pnpm gen-client     # Regenerate the API client (backend must be running)
```

From the project root these are also available as `just run-frontend`, `just gen-client`, etc.

## API Client Generation

The TypeScript client under `src/api/` is generated from the backend's OpenAPI spec.
With the backend running, regenerate it after API changes:

```bash
pnpm gen-client      # or: just gen-client
```

Config: `openapi-ts.config.ts`.
