import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import i18n from '../../i18n'
import Dashboard from '../Dashboard'

// The tab bar is static; mock the data-heavy tab bodies so Dashboard renders without providers.
vi.mock('../dashboard/OverviewTab', () => ({ default: () => null }))
vi.mock('../dashboard/WatchlistTab', () => ({ default: () => null }))
vi.mock('../dashboard/AllTagsTab', () => ({ default: () => null }))
// Dashboard reads live connection status via a TanStack-Query hook; stub it so the
// test needs no QueryClientProvider (it only asserts the static tab labels).
vi.mock('../../hooks/useLiveDashboard', () => ({ useLiveDashboard: () => ({ status: 'connected' }) }))

describe('Dashboard i18n', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })

  it('renders the English tab label', () => {
    render(<Dashboard />)
    expect(screen.getByRole('button', { name: 'Overview' })).toBeTruthy()
  })

  it('renders the Turkish tab label after switch', async () => {
    await i18n.changeLanguage('tr')
    render(<Dashboard />)
    expect(screen.getByRole('button', { name: 'Özet' })).toBeTruthy()
  })

  it('shows no raw translation keys', () => {
    render(<Dashboard />)
    expect(document.body.textContent).not.toMatch(/dashboard:/)
  })
})
