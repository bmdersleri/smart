import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import '../../i18n'

// Stub the DB-stats query so the tab renders without a backend.
vi.mock('../../api/client', () => ({
  getDatabaseStats: () => Promise.resolve({
    data: {
      size_bytes: 1024,
      total_readings: 42,
      total_is_estimate: false,
      earliest: '2026-06-01T00:00:00Z',
      tag_count: 7,
      last_day: 1,
      last_week: 2,
      last_month: 3,
      daily_rows: 4,
      est_monthly_growth_bytes: 2048,
      tables: [{ name: 'tag_readings', rows: 42 }],
    },
  }),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DatabaseTab from './DatabaseTab'

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <DatabaseTab active={true} />
    </QueryClientProvider>,
  )
}

describe('DatabaseTab', () => {
  it('renders DB stats once loaded', async () => {
    renderTab()
    expect(await screen.findByText('1.0 KB')).toBeInTheDocument()
    expect(screen.getByText('tag_readings')).toBeInTheDocument()
  })
})
