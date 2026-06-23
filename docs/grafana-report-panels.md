# Grafana Report Panels

Attach Grafana panels directly to report templates. When a report is generated, the backend renders each panel via Grafana's `/render` API and embeds the PNG into the PDF and Excel outputs.

## Feature Overview

1. **Define templates in the UI** — add a Grafana panel reference to a report template (panel UID, time range, etc.).
2. **Generate reports** — report generation calls `app/services/grafana_render.py` to fetch each panel.
3. **Embed in outputs** — rendered PNG is embedded in the PDF and Excel outputs.

## Authentication

The render service supports two authentication methods (in order of priority):

1. **Service-Account Token** (recommended for production):
   - Set `GRAFANA_SA_TOKEN` in `.env`
   - Token is passed as HTTP Bearer in the `Authorization` header

2. **Basic Auth** (fallback):
   - Uses `GRAFANA_USER` and `GRAFANA_PASSWORD` from `.env`
   - Used automatically if `GRAFANA_SA_TOKEN` is empty

### Creating a Service-Account Token

1. Open **Grafana Administration** (`http://localhost:3000/admin`)
2. Click **Service Accounts** (in the left sidebar)
3. Click **Add service account** button
4. Enter a name (e.g., `ekont-smart-report`)
5. Set the role to **Viewer** (sufficient for rendering; no editing required)
6. Click **Create**
7. Click **Add token**
8. Copy the token immediately (it is shown only once)
9. Paste into `.env`:
   ```
   GRAFANA_SA_TOKEN=glsa_1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p
   ```

## Environment Variables

Add these to `scada-reporter/backend/.env` (copy from `.env.example` and customize):

```bash
# Grafana connection (backend dashboard sync at startup)
GRAFANA_URL=http://localhost:3000
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin123

# Panel rendering in reports — empty falls back to GRAFANA_USER/PASSWORD basic-auth
GRAFANA_SA_TOKEN=
GRAFANA_RENDER_TIMEOUT=30.0
GRAFANA_RENDER_WIDTH=1000
GRAFANA_RENDER_HEIGHT=500
```

### Environment Variable Details

| Variable | Default | Purpose |
|----------|---------|---------|
| `GRAFANA_URL` | `http://localhost:3000` | Grafana server URL |
| `GRAFANA_USER` | `admin` | Basic auth username (fallback if no token) |
| `GRAFANA_PASSWORD` | `admin123` | Basic auth password (fallback if no token) |
| `GRAFANA_SA_TOKEN` | (empty) | Service-account token for rendering; overrides basic auth |
| `GRAFANA_RENDER_TIMEOUT` | `30.0` | Request timeout in seconds |
| `GRAFANA_RENDER_WIDTH` | `1000` | Render width in pixels |
| `GRAFANA_RENDER_HEIGHT` | `500` | Render height in pixels |

## Grafana Renderer Service

The embedded Grafana Image Renderer service must be running to generate panel PNGs.

### Renderer URL & Discovery

- **Default URL**: `http://localhost:8081`
- **Service Name**: `EkontRenderer` (registered in Grafana's `custom.ini`)

### Grafana Configuration

In Grafana's `custom.ini` (or Docker environment variables), enable the renderer:

```ini
[rendering]
server_url = http://localhost:8081
```

### Running the Renderer

The renderer service is started alongside Grafana (Docker or standalone binary). Ensure it is healthy before generating reports:

```bash
# Health check (example)
curl http://localhost:8081/health
```

## Constraints

- **Render Theme**: Always `light`
- **Time Range**: Comes from the template definition; no per-panel time-range override
- **Auth Scope**: Service account must have **Viewer** role (or higher)

## Example: Adding a Panel to a Template

1. Go to **Reports** → **Templates** → **Edit** a template
2. In the template editor, attach a Grafana panel:
   - **Panel UID** (from Grafana dashboard panel settings)
   - **Dashboard UID** (from Grafana dashboard URL)
   - **Time range** (e.g., last 7 days)
3. Save the template
4. When generating a report from this template, the backend will:
   - Fetch the panel via Grafana's `/render` API
   - Embed the PNG in the PDF and Excel output

## Troubleshooting

### "Panel render failed"
- Verify `GRAFANA_URL` is reachable
- Check `GRAFANA_SA_TOKEN` or `GRAFANA_USER`/`GRAFANA_PASSWORD` are correct
- Ensure Grafana Image Renderer service is running on port 8081
- Check Grafana logs: `docker logs grafana` (or container name)

### "Connection refused on port 8081"
- Renderer service is not running
- Start the renderer service (via Docker or standalone binary)
- Verify `custom.ini [rendering] server_url` points to `http://localhost:8081`

### "Forbidden (403)" or "Unauthorized (401)"
- Token or credentials are invalid or missing
- Regenerate the service-account token or verify `GRAFANA_USER`/`GRAFANA_PASSWORD`

## Implementation

Rendering logic lives in `app/services/grafana_render.py`:

- `fetch_panel_png()` — calls Grafana `/render` API with auth, width, height, theme
- `embed_in_pdf()` — inserts PNG into PDF report
- `embed_in_excel()` — inserts PNG into Excel sheet

Template model (`app/models/report_template.py`) stores panel metadata:
- `grafana_panels` — list of {uid, dashboard_uid, time_range}

## See Also

- [License Deployment Guide](docs/license-deployment.md)
- [Grafana Official Docs](https://grafana.com/docs/)
