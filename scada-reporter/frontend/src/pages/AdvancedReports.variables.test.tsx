import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../i18n'
import { TemplateEditorModal } from './AdvancedReports'

// createMock must be declared at module scope so the vi.mock factory closure
// can reference it; vitest hoists vi.mock() but calls the factory lazily,
// so createMock is already initialised by the time the factory runs.
const createMock = vi.fn().mockResolvedValue({ data: { id: 1 } })

vi.mock('../api/client', () => ({
  createTemplate: (...a: unknown[]) => createMock(...a),
  updateTemplate: vi.fn(),
  getTags: vi.fn().mockResolvedValue({ data: [{ id: 1, name: 'Debi' }] }),
  listFacilityVariables: vi.fn().mockResolvedValue({
    data: [{ id: 9, code: 'var_x', name: 'Var X', kind: 'scalar', is_active: true }],
  }),
  listGrafanaDashboards: vi.fn().mockResolvedValue({ data: [] }),
  listGrafanaPanels: vi.fn().mockResolvedValue({ data: [] }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('AdvancedReports variable picker', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
    vi.clearAllMocks()
  })

  it('includes selected variable_ids in the create payload', async () => {
    wrap(<TemplateEditorModal onClose={vi.fn()} />)

    // Wait for tags and variables to load as pills in step 0
    const tagBtn = await screen.findByRole('button', { name: 'Debi' })
    const varBtn = await screen.findByRole('button', { name: 'var_x' })

    // Select the tag (required to pass step-0 guard) and the variable pill
    fireEvent.click(tagBtn)
    fireEvent.click(varBtn)

    // Advance stepper 0→1→2→3 ("Next →" in EN i18n)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.click(screen.getByRole('button', { name: /next/i }))

    // Step 3: fill in the required template name, then click Create
    fireEvent.change(
      screen.getByPlaceholderText(/Daily Pump Report/i),
      { target: { value: 'T' } },
    )
    fireEvent.click(screen.getByRole('button', { name: /create/i }))

    await waitFor(() => expect(createMock).toHaveBeenCalled())
    // The non-negotiable assertion: variable_ids reaches the create payload
    expect(createMock.mock.calls[0][0]).toMatchObject({ variable_ids: [9] })
  })
})
