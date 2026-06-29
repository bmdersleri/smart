// scada-reporter/frontend/src/pages/dashboard/SystemTab.console.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import '../../i18n' // initialise i18n so translations resolve in test env

// Mock the hook so the panel renders deterministically.
vi.mock('../../hooks/useLogStream', () => ({
  useLogStream: () => ({
    lines: [
      { seq: 1, ts: '2026-06-17T10:00:00Z', level: 'INFO', levelno: 20, name: 'app.poller', msg: 'tick ok' },
      { seq: 2, ts: '2026-06-17T10:00:01Z', level: 'ERROR', levelno: 40, name: 'app', msg: 'boom' },
    ],
    clear: vi.fn(),
  }),
}))

// Stub the metrics queries so the tab body mounts without a backend.
vi.mock('../../api/client', () => ({
  getMetrics: () => Promise.resolve({ data: { rows_written_total: 0, bad_quality_total: 0, bad_ratio: null, tick_count: 0, tick_avg_seconds: null, plcs: [] } }),
  getDeadbandSavings: () => Promise.resolve({ data: null }),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SystemTab from './SystemTab'

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SystemTab active={true} />
    </QueryClientProvider>,
  )
}

describe('SystemTab live console', () => {
  it('renders streamed log lines', async () => {
    renderTab()
    expect(await screen.findByText('tick ok')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('shows the console title', async () => {
    renderTab()
    expect(await screen.findByText('Live Backend Console')).toBeInTheDocument()
  })
})
