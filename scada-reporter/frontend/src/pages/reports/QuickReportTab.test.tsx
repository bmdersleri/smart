import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '../../i18n'
import QuickReportTab from './QuickReportTab'

vi.mock('../../api/client', () => ({
  getTags: () => Promise.resolve({ data: [] }),
  getReportHistory: () => Promise.resolve({ data: [] }),
  generateReport: vi.fn(),
  downloadHistoryReport: vi.fn(),
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <QuickReportTab />
    </QueryClientProvider>,
  )
}

describe('QuickReportTab', () => {
  beforeEach(() => { cleanup() })

  it('renders the English quick-report title and empty report history state', async () => {
    await i18n.changeLanguage('en')
    renderPage()
    expect(await screen.findByText('Create Report')).toBeInTheDocument()
    expect(await screen.findByText('No reports generated yet.')).toBeInTheDocument()
  })
})
