import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../../i18n'
import PreviewPanel from './PreviewPanel'

const previewMock = vi.fn()
vi.mock('../../api/client', () => ({ previewVariable: (...a: unknown[]) => previewMock(...a) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('PreviewPanel', () => {
  beforeEach(async () => { await i18n.changeLanguage('en'); vi.clearAllMocks() })

  it('renders a scalar preview value', async () => {
    previewMock.mockResolvedValue({ data: { kind: 'scalar', value: 42.5, unit: 'm3' } })
    wrap(<PreviewPanel variableId={3} />)
    fireEvent.click(screen.getByRole('button', { name: /Preview/i }))
    await waitFor(() => expect(previewMock).toHaveBeenCalledWith(3, expect.objectContaining({ window: expect.objectContaining({ type: 'month' }) })))
    expect(await screen.findByText(/42.5/)).toBeInTheDocument()
  })

  it('renders the series point count', async () => {
    previewMock.mockResolvedValue({ data: { kind: 'series', points: [{ ts: 'x', value: 1 }, { ts: 'y', value: 2 }], unit: 'm3' } })
    wrap(<PreviewPanel variableId={5} />)
    fireEvent.click(screen.getByRole('button', { name: /Preview/i }))
    expect(await screen.findByText(/2 points/i)).toBeInTheDocument()
  })
})
