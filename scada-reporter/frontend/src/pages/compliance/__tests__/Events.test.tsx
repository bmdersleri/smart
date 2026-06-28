import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import EventsTab from '../EventsTab'
import * as client from '../../../api/client'
import type { ComplianceEvent } from '../../../api/client'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))

let role = 'operator'
vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({ user: { role } }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const SAMPLE_EVENT: ComplianceEvent = {
  id: 11,
  permit_id: 1,
  parameter_id: 2,
  limit_id: 3,
  event_type: 'limit_exceeded',
  severity: 'critical',
  period_start: '2026-06-01T00:00:00Z',
  period_end: '2026-06-30T23:59:59Z',
  observed_value: 12.5,
  limit_value: 10,
  status: 'open',
  event_key: 'k',
  evidence: { samples: 4, mean: 12.5 },
  created_at: '2026-06-15T00:00:00Z',
  updated_at: '2026-06-15T00:00:00Z',
  acknowledged_at: null,
  acknowledged_by: null,
  resolved_at: null,
  resolved_by: null,
  waived_at: null,
  waived_by: null,
  waive_reason: null,
  note_count: 0,
}

describe('Compliance EventsTab', () => {
  beforeEach(() => {
    role = 'operator'
    vi.restoreAllMocks()
    vi.spyOn(client, 'listPermits').mockResolvedValue({
      data: [{ id: 1, name: 'P1', is_active: true }],
    } as never)
  })

  it('passes the selected permit + status filters to listEvents', async () => {
    const spy = vi
      .spyOn(client, 'listEvents')
      .mockResolvedValue({ data: { total: 1, items: [SAMPLE_EVENT] } } as never)

    render(wrap(<EventsTab />))
    await waitFor(() => expect(screen.getByText('event_type_limit_exceeded')).toBeInTheDocument())

    // change status filter to "resolved" and assert the client is called with it.
    const statusSelect = screen.getByDisplayValue('all_statuses')
    fireEvent.change(statusSelect, { target: { value: 'resolved' } })

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith(expect.objectContaining({ status: 'resolved' })),
    )
  })

  it('blocks a waive status change when no reason is provided', async () => {
    vi.spyOn(client, 'listEvents').mockResolvedValue({
      data: { total: 1, items: [SAMPLE_EVENT] },
    } as never)
    const statusSpy = vi.spyOn(client, 'setEventStatus')

    render(wrap(<EventsTab />))
    await waitFor(() => expect(screen.getByText('event_type_limit_exceeded')).toBeInTheDocument())

    // open the detail panel
    fireEvent.click(screen.getByText('event_type_limit_exceeded'))
    await waitFor(() => expect(screen.getByText('change_status')).toBeInTheDocument())

    // click the "Waive" BUTTON (the status select also has a "status_waived"
    // option, so scope the query to buttons) without entering a reason →
    // blocked, error shown, no API call.
    const waiveBtn = screen
      .getAllByRole('button', { name: 'status_waived' })
      .find((el) => el.tagName === 'BUTTON')
    fireEvent.click(waiveBtn!)
    await waitFor(() => expect(screen.getByText('waive_reason_required')).toBeInTheDocument())
    expect(statusSpy).not.toHaveBeenCalled()
  })
})
