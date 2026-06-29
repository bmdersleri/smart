import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../i18n'
import FacilityVariables from './FacilityVariables'

const canMock = vi.fn()
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'operator', permissions: [] }, can: canMock, logout: vi.fn() }),
}))
vi.mock('../api/client', () => ({
  listFacilityVariables: vi.fn().mockResolvedValue({ data: [] }),
  deleteFacilityVariable: vi.fn().mockResolvedValue({ data: {} }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('FacilityVariables create gating', () => {
  beforeEach(() => vi.clearAllMocks())
  it('hides add button when can() is false', async () => {
    await i18n.changeLanguage('en')
    canMock.mockReturnValue(false)
    wrap(<FacilityVariables />)
    expect(screen.queryByRole('button', { name: /Add Variable/i })).not.toBeInTheDocument()
  })
  it('shows add button when can(facility_variable:create) is true', async () => {
    await i18n.changeLanguage('en')
    canMock.mockImplementation((p: string) => p === 'facility_variable:create')
    wrap(<FacilityVariables />)
    expect(await screen.findByRole('button', { name: /Add Variable/i })).toBeInTheDocument()
  })
})
