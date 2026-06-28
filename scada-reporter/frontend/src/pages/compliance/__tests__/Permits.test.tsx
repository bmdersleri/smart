import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PermitsTab from '../PermitsTab'
import * as client from '../../../api/client'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))

let role = 'admin'
vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({ user: { role } }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('Compliance PermitsTab permission gating', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(client, 'listPermits').mockResolvedValue({
      data: [{ id: 1, name: 'P1', permit_number: 'A-1', is_active: true }],
    } as never)
  })

  it('shows the New Permit control for admins', async () => {
    role = 'admin'
    render(wrap(<PermitsTab />))
    await waitFor(() => expect(screen.getByText('P1')).toBeInTheDocument())
    expect(screen.getByText('new_permit')).toBeInTheDocument()
  })

  it('hides write controls for non-admin (operator) users', async () => {
    role = 'operator'
    render(wrap(<PermitsTab />))
    await waitFor(() => expect(screen.getByText('P1')).toBeInTheDocument())
    // No "New Permit" button for operators.
    expect(screen.queryByText('new_permit')).not.toBeInTheDocument()
  })
})
