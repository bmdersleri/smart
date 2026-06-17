import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '../i18n'
import AdvancedReports from './AdvancedReports'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'admin', permissions: [] }, can: () => true }),
}))

// Minimal data-layer mocks so the page renders without a backend.
vi.mock('../api/client', () => ({
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
  getTags: () => Promise.resolve({ data: [] }),
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AdvancedReports />
    </QueryClientProvider>
  )
}

describe('AdvancedReports i18n', () => {
  beforeEach(() => { cleanup() })

  it('renders the English page header', async () => {
    await i18n.changeLanguage('en')
    renderPage()
    expect(await screen.findByText('Advanced Reports')).toBeTruthy()
  })

  it('renders the Turkish page header', async () => {
    await i18n.changeLanguage('tr')
    renderPage()
    expect(await screen.findByText('Gelişmiş Raporlar')).toBeTruthy()
  })

  it('does not leak raw namespace keys', async () => {
    await i18n.changeLanguage('en')
    renderPage()
    await screen.findByText('Advanced Reports')
    expect(document.body.textContent).not.toMatch(/advancedReports:/)
  })
})
