// src/pages/__tests__/PlcHealth.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PlcHealth from '../PlcHealth'
import * as client from '../../api/client'

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ can: () => true }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('PlcHealth page', () => {
  it('renders open incidents from api', async () => {
    vi.spyOn(client, 'getIncidentSummary').mockResolvedValue({ data: { open_total: 1, critical: 1, warning: 0 } } as never)
    vi.spyOn(client, 'getPlcIncidents').mockResolvedValue({
      data: [{ id: 1, plc_ip: '10.0.0.1', plc_name: 'P1', kind: 'disconnected', severity: 'critical', message: 'down', detail: {}, opened_at: '2026-06-21T00:00:00Z', resolved_at: null, acknowledged_by: null, acknowledged_at: null }],
    } as never)
    vi.spyOn(client, 'getPlcHealth').mockResolvedValue({ data: [] } as never)

    render(wrap(<PlcHealth />))
    await waitFor(() => expect(screen.getByText('P1')).toBeInTheDocument())
    expect(screen.getByText('down')).toBeInTheDocument()
  })
})
