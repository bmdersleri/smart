import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '../i18n'
import LicenseBadge from './LicenseBadge'

vi.mock('../api/client', () => ({ getLicenseStatus: vi.fn() }))

function status(over: Record<string, unknown>) {
  return {
    data: {
      mode: 'unlicensed',
      licensed: false,
      customer: null,
      license_id: null,
      product: null,
      features: [],
      max_tags: null,
      expires_at: null,
      demo_max_tags: null,
      ...over,
    },
  }
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('LicenseBadge', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders the demo badge', async () => {
    const { getLicenseStatus } = await import('../api/client')
    ;(getLicenseStatus as ReturnType<typeof vi.fn>).mockResolvedValue(status({ mode: 'demo' }))
    wrap(<LicenseBadge />)
    expect(await screen.findByText('Demo')).toBeInTheDocument()
  })

  it('renders licensed mode with customer', async () => {
    const { getLicenseStatus } = await import('../api/client')
    ;(getLicenseStatus as ReturnType<typeof vi.fn>).mockResolvedValue(
      status({ mode: 'licensed', licensed: true, customer: 'ACME Water' })
    )
    wrap(<LicenseBadge />)
    expect(await screen.findByText('Licensed')).toBeInTheDocument()
    expect(await screen.findByText(/ACME Water/)).toBeInTheDocument()
  })
})
