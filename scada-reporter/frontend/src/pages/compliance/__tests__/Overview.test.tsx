import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import OverviewTab from '../OverviewTab'
import * as client from '../../../api/client'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('Compliance OverviewTab', () => {
  it('renders counters from mocked overview data', async () => {
    vi.spyOn(client, 'getComplianceOverview').mockResolvedValue({
      data: {
        active_permits: 3,
        open_events: 7,
        by_event_type: { limit_exceeded: 5, missing_sample: 2 },
        missing_samples: 2,
        unresolved_explanations: 1,
        packs_waiting: 0,
      },
    } as never)
    vi.spyOn(client, 'listPermits').mockResolvedValue({ data: [] } as never)
    vi.spyOn(client, 'listEvents').mockResolvedValue({ data: { total: 0, items: [] } } as never)

    render(wrap(<OverviewTab onOpenEvents={() => {}} />))

    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument())
    expect(screen.getByText('7')).toBeInTheDocument()
    // missing_samples (2) and unresolved_explanations (1) cards render.
    expect(screen.getByText('1')).toBeInTheDocument()
  })
})
