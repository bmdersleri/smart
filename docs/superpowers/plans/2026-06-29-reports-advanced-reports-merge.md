# Reports And Advanced Reports Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the existing Reports and Advanced Reports frontend flows into a single `/reports` report center with `Hizli Rapor` as the default tab, while preserving advanced reporting behavior and redirecting the legacy `/advanced-reports` route.

**Architecture:** Extract the current ad-hoc and advanced reporting sections into focused tab components under `frontend/src/pages/reports/`, then rebuild `Reports.tsx` as the canonical shell that owns the tab state and page-level i18n strings. Keep backend APIs unchanged, replace the old Advanced Reports route with a redirect, and cover the merge with focused Vitest route, i18n, and navigation tests.

**Tech Stack:** React 19, TypeScript, React Router 7, TanStack Query 5, react-i18next, Vitest, Testing Library, Vite

---

## File Map

- Create: `scada-reporter/frontend/src/pages/reports/QuickReportTab.tsx`
  Responsibility: own the current ad-hoc report generation UI and history download behavior extracted from `Reports.tsx`.
- Create: `scada-reporter/frontend/src/pages/reports/TemplatesTab.tsx`
  Responsibility: own advanced template CRUD and template-run behavior currently embedded in `AdvancedReports.tsx`.
- Create: `scada-reporter/frontend/src/pages/reports/ScheduledTab.tsx`
  Responsibility: own scheduled-report list, create, toggle, and delete behavior currently embedded in `AdvancedReports.tsx`.
- Create: `scada-reporter/frontend/src/pages/reports/ArchiveTab.tsx`
  Responsibility: own advanced archive filters, listing, pagination, and download behavior currently embedded in `AdvancedReports.tsx`.
- Create: `scada-reporter/frontend/src/pages/reports/QuickReportTab.test.tsx`
  Responsibility: verify the extracted quick-report surface still renders the ad-hoc reporting UI.
- Create: `scada-reporter/frontend/src/pages/Reports.i18n.test.tsx`
  Responsibility: verify the merged `/reports` page renders localized shell text and defaults to the quick tab.
- Create: `scada-reporter/frontend/src/pages/Reports.route.test.tsx`
  Responsibility: verify `/advanced-reports` redirects to `/reports` and still lands on the quick tab.
- Create: `scada-reporter/frontend/src/components/Layout.reports-nav.test.tsx`
  Responsibility: verify the sidebar shows only one reports navigation entry after the merge.
- Modify: `scada-reporter/frontend/src/pages/Reports.tsx:1-388`
  Responsibility: stop owning the full ad-hoc implementation inline and become the merged report-center shell.
- Modify: `scada-reporter/frontend/src/pages/AdvancedReports.tsx:1-943`
  Responsibility: first become a thin consumer of the extracted advanced tab components, then be deleted after route migration.
- Modify: `scada-reporter/frontend/src/App.tsx:11-12,51-52`
  Responsibility: remove the standalone Advanced Reports screen from the route tree and redirect `/advanced-reports` to `/reports`.
- Modify: `scada-reporter/frontend/src/components/Layout.tsx:9-21`
  Responsibility: remove the duplicate advanced-reports sidebar item while keeping `nav_reports`.
- Modify: `scada-reporter/frontend/src/i18n/locales/en/reports.json`
  Responsibility: add merged report-center shell strings while preserving the existing quick-report strings.
- Modify: `scada-reporter/frontend/src/i18n/locales/tr/reports.json`
  Responsibility: Turkish equivalents of the merged report-center shell strings.
- Modify: `scada-reporter/frontend/src/i18n/locales/ru/reports.json`
  Responsibility: Russian equivalents of the merged report-center shell strings.
- Modify: `scada-reporter/frontend/src/i18n/locales/de/reports.json`
  Responsibility: German equivalents of the merged report-center shell strings.
- Modify: `scada-reporter/frontend/src/i18n/locales/ar/reports.json`
  Responsibility: Arabic equivalents of the merged report-center shell strings.
- Delete: `scada-reporter/frontend/src/pages/AdvancedReports.i18n.test.tsx`
  Responsibility: remove the old page-specific test after its coverage is replaced by merged-page tests.
- Delete: `scada-reporter/frontend/src/pages/AdvancedReports.tsx`
  Responsibility: retire the dead standalone page after routing is redirected.

### Task 1: Extract The Quick Report Tab

**Files:**
- Create: `scada-reporter/frontend/src/pages/reports/QuickReportTab.tsx`
- Create: `scada-reporter/frontend/src/pages/reports/QuickReportTab.test.tsx`
- Modify: `scada-reporter/frontend/src/pages/Reports.tsx:1-388`

- [ ] **Step 1: Write the failing extraction test**

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '../../i18n'
import QuickReportTab from './QuickReportTab'

vi.mock('../../api/client', () => ({
  getTags: () => Promise.resolve({ data: [] }),
  generateReport: vi.fn(),
  getReportHistory: () => Promise.resolve({ data: [] }),
  downloadHistoryReport: vi.fn(),
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <QuickReportTab />
    </QueryClientProvider>,
  )
}

describe('QuickReportTab', () => {
  it('renders the existing quick-report title', async () => {
    await i18n.changeLanguage('en')
    renderPage()
    expect(await screen.findByText('Generate Report')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/pages/reports/QuickReportTab.test.tsx`
Expected: FAIL with a module resolution error because `src/pages/reports/QuickReportTab.tsx` does not exist yet.

- [ ] **Step 3: Create the extracted quick-report component**

```tsx
// scada-reporter/frontend/src/pages/reports/QuickReportTab.tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getTags, generateReport, getReportHistory, downloadHistoryReport } from '../../api/client'
import type { ReportHistoryEntry } from '../../api/client'
import { format, subDays, startOfDay, endOfDay } from 'date-fns'
import { enUS, tr, ru, de } from 'date-fns/locale'
import { parseUtc } from '../../utils/time'

const DATE_LOCALES: Record<string, typeof tr> = { en: enUS, tr, ru, de }
const fmt = (d: Date) => format(d, "yyyy-MM-dd'T'HH:mm")

export default function QuickReportTab() {
  const { t } = useTranslation(['reports', 'common'])
  return (
    <div className="space-y-6 max-w-3xl">
      <h2 className="text-xl font-bold text-white">{t('title')}</h2>
    </div>
  )
}
```

Copy the full `HistoryRow` helper and the report-form state/query logic from `scada-reporter/frontend/src/pages/Reports.tsx:42-388` into this file. Keep the behavior identical; only change import roots from `../` to `../../`, keep the inner container width classes, and remove the page-level `p-6` wrapper because `Reports.tsx` will own the outer spacing.

```tsx
// scada-reporter/frontend/src/pages/Reports.tsx
import QuickReportTab from './reports/QuickReportTab'

export default function Reports() {
  return (
    <div className="p-6">
      <QuickReportTab />
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/pages/reports/QuickReportTab.test.tsx`
Expected: PASS with `renders the existing quick-report title`.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/pages/Reports.tsx scada-reporter/frontend/src/pages/reports/QuickReportTab.tsx scada-reporter/frontend/src/pages/reports/QuickReportTab.test.tsx
git commit -m "refactor: extract quick report tab"
```

### Task 2: Build The Merged Report Center Shell

**Files:**
- Create: `scada-reporter/frontend/src/pages/reports/TemplatesTab.tsx`
- Create: `scada-reporter/frontend/src/pages/reports/ScheduledTab.tsx`
- Create: `scada-reporter/frontend/src/pages/reports/ArchiveTab.tsx`
- Create: `scada-reporter/frontend/src/pages/Reports.i18n.test.tsx`
- Modify: `scada-reporter/frontend/src/pages/Reports.tsx:1-388`
- Modify: `scada-reporter/frontend/src/pages/AdvancedReports.tsx:1-943`
- Modify: `scada-reporter/frontend/src/i18n/locales/en/reports.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/tr/reports.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/ru/reports.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/de/reports.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/ar/reports.json`

- [ ] **Step 1: Write the failing merged-page i18n test**

```tsx
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '../i18n'
import Reports from './Reports'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'admin', permissions: [] }, can: () => true }),
}))

vi.mock('../api/client', () => ({
  getTags: () => Promise.resolve({ data: [] }),
  generateReport: vi.fn(),
  getReportHistory: () => Promise.resolve({ data: [] }),
  downloadHistoryReport: vi.fn(),
  listTemplates: () => Promise.resolve({ data: [] }),
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  runTemplate: vi.fn(),
  listScheduled: () => Promise.resolve({ data: [] }),
  createScheduled: vi.fn(),
  toggleScheduled: vi.fn(),
  deleteScheduled: vi.fn(),
  getArchive: () => Promise.resolve({ data: { items: [], total_pages: 0 } }),
  downloadArchiveReport: vi.fn(),
  listGrafanaDashboards: () => Promise.resolve({ data: [] }),
  listGrafanaPanels: () => Promise.resolve({ data: [] }),
  generateDashboardFromTemplate: vi.fn(),
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Reports />
    </QueryClientProvider>,
  )
}

describe('Reports i18n', () => {
  beforeEach(() => cleanup())

  it('renders the English merged page header and defaults to Quick Report', async () => {
    await i18n.changeLanguage('en')
    renderPage()
    expect(await screen.findByText('Reports')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quick Report' })).toBeInTheDocument()
    expect(screen.getByText('Generate Report')).toBeInTheDocument()
  })

  it('renders the Turkish merged page header', async () => {
    await i18n.changeLanguage('tr')
    renderPage()
    expect(await screen.findByText('Raporlar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hizli Rapor' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/pages/Reports.i18n.test.tsx`
Expected: FAIL because the current `Reports` page does not expose the merged shell title or the four-tab navigation.

- [ ] **Step 3: Extract the advanced tabs from `AdvancedReports.tsx`**

```text
Create scada-reporter/frontend/src/pages/reports/TemplatesTab.tsx by copying these blocks from scada-reporter/frontend/src/pages/AdvancedReports.tsx:
- lines 1-76 for shared helpers used by the template table
- lines 78-399 for TemplateEditorModal
- lines 534-652 for TemplatesTab

Create scada-reporter/frontend/src/pages/reports/ScheduledTab.tsx by copying these blocks from the same source file:
- lines 1-54 for fmtDate, STATUS_COLORS, and StatusBadge
- lines 401-532 for ScheduleCreateModal
- lines 654-745 for ScheduledTab

Create scada-reporter/frontend/src/pages/reports/ArchiveTab.tsx by copying these blocks from the same source file:
- lines 1-54 for fmtDate, fmtBytes, STATUS_COLORS, and StatusBadge
- lines 747-904 for ArchiveTab
```

```tsx
// scada-reporter/frontend/src/pages/AdvancedReports.tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import TemplatesTab from './reports/TemplatesTab'
import ScheduledTab from './reports/ScheduledTab'
import ArchiveTab from './reports/ArchiveTab'

type Tab = 'templates' | 'scheduled' | 'archive'

const TABS: Tab[] = ['templates', 'scheduled', 'archive']
```

```tsx
// scada-reporter/frontend/src/pages/AdvancedReports.tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import TemplatesTab from './reports/TemplatesTab'
import ScheduledTab from './reports/ScheduledTab'
import ArchiveTab from './reports/ArchiveTab'

type Tab = 'templates' | 'scheduled' | 'archive'

export default function AdvancedReports() {
  const { t } = useTranslation('advancedReports')
  const [tab, setTab] = useState<Tab>('templates')
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">{t('title')}</h1>
        <p className="text-gray-500 text-sm mt-1">{t('subtitle')}</p>
      </div>
      <div className="flex border-b border-edge mb-6">
        {TABS.map((id) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === id ? 'border-blue-500 text-cyan-400' : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {t(`tab_${id}`)}
          </button>
        ))}
      </div>
      {tab === 'templates' && <TemplatesTab onRunDone={() => setTab('archive')} />}
      {tab === 'scheduled' && <ScheduledTab />}
      {tab === 'archive' && <ArchiveTab />}
    </div>
  )
}
```

- [ ] **Step 4: Build the merged `Reports.tsx` shell**

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import QuickReportTab from './reports/QuickReportTab'
import TemplatesTab from './reports/TemplatesTab'
import ScheduledTab from './reports/ScheduledTab'
import ArchiveTab from './reports/ArchiveTab'

export type ReportTabId = 'quick' | 'templates' | 'scheduled' | 'archive'

const TABS: ReportTabId[] = ['quick', 'templates', 'scheduled', 'archive']

export default function Reports() {
  const { t } = useTranslation('reports')
  const [tab, setTab] = useState<ReportTabId>('quick')

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">{t('page_title')}</h1>
        <p className="text-gray-500 text-sm mt-1">{t('page_subtitle')}</p>
      </div>

      <div className="flex border-b border-edge">
        {TABS.map((id) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === id ? 'border-blue-500 text-cyan-400' : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {t(`tab_${id}`)}
          </button>
        ))}
      </div>

      {tab === 'quick' && <QuickReportTab />}
      {tab === 'templates' && <TemplatesTab onRunDone={() => setTab('archive')} />}
      {tab === 'scheduled' && <ScheduledTab />}
      {tab === 'archive' && <ArchiveTab />}
    </div>
  )
}
```

- [ ] **Step 5: Add the merged shell strings to every `reports.json` locale**

```json
{
  "page_title": "Reports",
  "page_subtitle": "Quick exports, reusable templates, scheduled runs, and archive access",
  "tab_quick": "Quick Report",
  "tab_templates": "Templates",
  "tab_scheduled": "Scheduled",
  "tab_archive": "Archive"
}
```

```json
{
  "page_title": "Raporlar",
  "page_subtitle": "Hizli ciktilar, tekrar kullanilan sablonlar, zamanlanmis calismalar ve arsiv erisimi",
  "tab_quick": "Hizli Rapor",
  "tab_templates": "Sablonlar",
  "tab_scheduled": "Zamanlanmis",
  "tab_archive": "Arsiv"
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pnpm test -- src/pages/reports/QuickReportTab.test.tsx src/pages/Reports.i18n.test.tsx`
Expected: PASS with the quick-tab extraction test and merged-page i18n tests all green.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/frontend/src/pages/Reports.tsx scada-reporter/frontend/src/pages/AdvancedReports.tsx scada-reporter/frontend/src/pages/reports/QuickReportTab.tsx scada-reporter/frontend/src/pages/reports/TemplatesTab.tsx scada-reporter/frontend/src/pages/reports/ScheduledTab.tsx scada-reporter/frontend/src/pages/reports/ArchiveTab.tsx scada-reporter/frontend/src/pages/Reports.i18n.test.tsx scada-reporter/frontend/src/i18n/locales/en/reports.json scada-reporter/frontend/src/i18n/locales/tr/reports.json scada-reporter/frontend/src/i18n/locales/ru/reports.json scada-reporter/frontend/src/i18n/locales/de/reports.json scada-reporter/frontend/src/i18n/locales/ar/reports.json
git commit -m "feat: merge reports page tabs"
```

### Task 3: Canonicalize Routes And Sidebar Navigation

**Files:**
- Create: `scada-reporter/frontend/src/pages/Reports.route.test.tsx`
- Create: `scada-reporter/frontend/src/components/Layout.reports-nav.test.tsx`
- Modify: `scada-reporter/frontend/src/App.tsx:11-12,51-52`
- Modify: `scada-reporter/frontend/src/components/Layout.tsx:9-21`
- Delete: `scada-reporter/frontend/src/pages/AdvancedReports.i18n.test.tsx`
- Delete: `scada-reporter/frontend/src/pages/AdvancedReports.tsx`

- [ ] **Step 1: Write the failing route-redirect test**

```tsx
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi } from 'vitest'
import App from '../App'

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>()
  return {
    ...actual,
    useAuth: () => ({ user: { role: 'admin', permissions: [] }, loading: false }),
  }
})

vi.mock('../components/Layout', async (importOriginal) => {
  const { Outlet } = await import('react-router-dom')
  return { default: () => <Outlet /> }
})

vi.mock('../api/client', () => ({
  getTags: () => Promise.resolve({ data: [] }),
  generateReport: vi.fn(),
  getReportHistory: () => Promise.resolve({ data: [] }),
  downloadHistoryReport: vi.fn(),
  listTemplates: () => Promise.resolve({ data: [] }),
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  runTemplate: vi.fn(),
  listScheduled: () => Promise.resolve({ data: [] }),
  createScheduled: vi.fn(),
  toggleScheduled: vi.fn(),
  deleteScheduled: vi.fn(),
  getArchive: () => Promise.resolve({ data: { items: [], total_pages: 0 } }),
  downloadArchiveReport: vi.fn(),
  listGrafanaDashboards: () => Promise.resolve({ data: [] }),
  listGrafanaPanels: () => Promise.resolve({ data: [] }),
  generateDashboardFromTemplate: vi.fn(),
}))

describe('reports route redirect', () => {
  it('redirects /advanced-reports to /reports and lands on Quick Report', async () => {
    window.history.pushState({}, '', '/advanced-reports')
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <App />
      </QueryClientProvider>,
    )
    expect(await screen.findByText('Generate Report')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quick Report' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Write the failing sidebar-navigation test**

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import Layout from './Layout'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'admin', username: 'admin' }, logout: vi.fn() }),
}))

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => ({
        nav_reports: 'Reports',
        nav_advanced_reports: 'Advanced Reports',
        nav_dashboard: 'Dashboard',
        nav_tags: 'Tags',
        nav_plc: 'PLC',
        nav_trend: 'Trend',
        nav_excel_templates: 'Excel Templates',
        nav_metrics: 'Metrics',
        nav_grafana: 'Grafana',
        nav_lab: 'Lab',
        nav_compliance: 'Compliance',
        nav_settings: 'Settings',
        nav_users: 'Users',
        app_subtitle: 'Subtitle',
        logout: 'Logout',
        menu_open: 'Open menu',
      }[key] ?? key),
    }),
  }
})

describe('Layout reports navigation', () => {
  it('shows only one reports navigation entry', () => {
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    )
    expect(screen.getByText('Reports')).toBeInTheDocument()
    expect(screen.queryByText('Advanced Reports')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pnpm test -- src/pages/Reports.route.test.tsx src/components/Layout.reports-nav.test.tsx`
Expected: FAIL because `App.tsx` still mounts `AdvancedReports` directly and `Layout.tsx` still renders `nav_advanced_reports`.

- [ ] **Step 4: Redirect the legacy route and remove the duplicate nav item**

```tsx
// scada-reporter/frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Reports from './pages/Reports'

// remove: import AdvancedReports from './pages/AdvancedReports'

<Route path="reports" element={<Reports />} />
<Route path="advanced-reports" element={<Navigate to="/reports" replace />} />
```

```tsx
// scada-reporter/frontend/src/components/Layout.tsx
const nav = [
  { to: '/', labelKey: 'nav_dashboard' },
  { to: '/tags', labelKey: 'nav_tags' },
  { to: '/plc', labelKey: 'nav_plc' },
  { to: '/trend', labelKey: 'nav_trend' },
  { to: '/reports', labelKey: 'nav_reports' },
  { to: '/excel-templates', labelKey: 'nav_excel_templates' },
  { to: '/metrics', labelKey: 'nav_metrics' },
  { to: '/grafana', labelKey: 'nav_grafana' },
  { to: '/lab', labelKey: 'nav_lab' },
  { to: '/compliance', labelKey: 'nav_compliance' },
  { to: '/settings', labelKey: 'nav_settings' },
]
```

- [ ] **Step 5: Retire the dead standalone artifacts**

```bash
git rm scada-reporter/frontend/src/pages/AdvancedReports.tsx
git rm scada-reporter/frontend/src/pages/AdvancedReports.i18n.test.tsx
```

- [ ] **Step 6: Run targeted tests to verify they pass**

Run: `pnpm test -- src/pages/Reports.route.test.tsx src/components/Layout.reports-nav.test.tsx src/pages/Reports.i18n.test.tsx`
Expected: PASS with redirect, sidebar, and merged-page i18n coverage all green.

- [ ] **Step 7: Run full frontend verification**

Run: `pnpm test`
Expected: PASS across the Vitest suite.

Run: `pnpm lint`
Expected: PASS with no hardcoded-string or ESLint regressions.

Run: `pnpm build`
Expected: PASS with a successful TypeScript and Vite production build.

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/src/App.tsx scada-reporter/frontend/src/components/Layout.tsx scada-reporter/frontend/src/pages/Reports.route.test.tsx scada-reporter/frontend/src/components/Layout.reports-nav.test.tsx
git add -u scada-reporter/frontend/src/pages/AdvancedReports.tsx scada-reporter/frontend/src/pages/AdvancedReports.i18n.test.tsx
git commit -m "refactor: canonicalize merged reports navigation"
```
