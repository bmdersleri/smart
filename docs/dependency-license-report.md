# Dependency License Report

Generated: 2026-06-22

Scope: direct backend production dependencies from
`scada-reporter/backend/requirements.txt` and direct frontend dependencies
from `scada-reporter/frontend/package.json`. Transitive dependencies are not
listed here; regenerate a full bill of materials before every commercial
release.

This report is not legal advice. Treat packages marked `UNKNOWN` or packages
with copyleft-style terms as release blockers until reviewed.

## Backend Direct Dependencies

| Package | Installed version | Reported license |
|---|---:|---|
| fastapi | 0.138.0 | MIT |
| uvicorn | 0.49.0 | BSD-3-Clause |
| asyncua | 2.0 | GNU Lesser General Public License v3 or later |
| sqlalchemy | 2.0.51 | MIT |
| asyncpg | 0.31.0 | Apache-2.0 |
| alembic | 1.18.4 | MIT |
| pydantic | 2.13.4 | MIT |
| pydantic-settings | 2.14.2 | MIT |
| python-jose | 3.5.0 | MIT |
| bcrypt | 5.0.0 | Apache-2.0 |
| python-multipart | 0.0.32 | Apache-2.0 |
| weasyprint | 69.0 | BSD License |
| openpyxl | 3.1.5 | MIT |
| celery | 5.6.3 | BSD-3-Clause |
| redis | 8.0.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| sentry-sdk | 2.63.0 | MIT |
| python-snap7 | 3.0.0 | MIT |
| pandas | 3.0.3 | BSD 3-Clause License |
| matplotlib | 3.11.0 | Matplotlib License |
| plotly | 6.8.0 | MIT |
| apscheduler | 3.11.2 | MIT |
| tabulate | 0.10.0 | MIT |
| python-docx | 1.2.0 | MIT |
| reportlab | 4.5.1 | BSD-style |
| jinja2 | 3.1.6 | BSD License |
| python-dotenv | 1.2.2 | BSD-3-Clause |
| prometheus-client | 0.25.0 | Apache-2.0 AND BSD-2-Clause |
| gunicorn | 26.0.0 | MIT |

## Frontend Direct Dependencies

| Package | Installed version | Reported license | Scope |
|---|---:|---|---|
| @tanstack/react-query | 5.101.0 | MIT | runtime |
| axios | 1.17.0 | MIT | runtime |
| date-fns | 4.4.0 | MIT | runtime |
| html-to-image | 1.11.13 | MIT | runtime |
| i18next | 26.3.1 | MIT | runtime |
| lucide-react | 1.18.0 | ISC | runtime |
| react | 19.2.7 | MIT | runtime |
| react-dom | 19.2.7 | MIT | runtime |
| react-i18next | 17.0.8 | MIT | runtime |
| react-router-dom | 7.17.0 | MIT | runtime |
| recharts | 3.8.1 | MIT | runtime |
| @eslint/js | 10.0.1 | MIT | dev |
| @hey-api/openapi-ts | 0.98.2 | MIT | dev |
| @playwright/test | 1.61.0 | Apache-2.0 | dev |
| @tailwindcss/vite | 4.3.1 | MIT | dev |
| @testing-library/jest-dom | 6.9.1 | MIT | dev |
| @testing-library/react | 16.3.2 | MIT | dev |
| @testing-library/user-event | 14.6.1 | MIT | dev |
| @types/node | 24.13.2 | MIT | dev |
| @types/react | 19.2.17 | MIT | dev |
| @types/react-dom | 19.2.3 | MIT | dev |
| @vitejs/plugin-react | 6.0.2 | MIT | dev |
| eslint | 10.5.0 | MIT | dev |
| eslint-plugin-react-hooks | 7.1.1 | MIT | dev |
| eslint-plugin-react-refresh | 0.5.2 | MIT | dev |
| globals | 17.6.0 | MIT | dev |
| jsdom | 29.1.1 | MIT | dev |
| puppeteer-core | 25.1.0 | Apache-2.0 | dev |
| tailwindcss | 4.3.1 | MIT | dev |
| typescript | 6.0.3 | Apache-2.0 | dev |
| typescript-eslint | 8.61.0 | MIT | dev |
| vite | 8.0.16 | MIT | dev |
| vitest | 4.1.8 | MIT | dev |

## Release Notes

- Include this repository's `LICENSE` and `NOTICE` files in customer
  deliverables.
- Before distributing Docker images, installers, or on-premise packages,
  generate a full transitive SBOM/license inventory from the exact lockfiles.
- Review LGPL obligations for `asyncua` before binary/on-premise distribution.
- Keep third-party copyright notices from bundled frontend and Python
  dependencies.
