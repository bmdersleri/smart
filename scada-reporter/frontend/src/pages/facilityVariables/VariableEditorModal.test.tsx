import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../../i18n'
import { VariableEditorModal } from '../FacilityVariables'

const createMock = vi.fn().mockResolvedValue({ data: { id: 1 } })
vi.mock('../../api/client', () => ({
  createFacilityVariable: (...a: unknown[]) => createMock(...a),
  updateFacilityVariable: vi.fn().mockResolvedValue({ data: {} }),
  getTags: vi.fn().mockResolvedValue({ data: [{ id: 1, name: 'Debi', unit: 'm3' }] }),
  listFacilityVariables: vi.fn().mockResolvedValue({ data: [] }),
  validateExpression: vi.fn().mockResolvedValue({ data: { valid: true } }),
  previewVariable: vi.fn().mockResolvedValue({ data: { kind: 'scalar', value: 1, unit: 'm3' } }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('VariableEditorModal', () => {
  beforeEach(async () => { await i18n.changeLanguage('en'); vi.clearAllMocks() })

  it('creates a scalar const variable', async () => {
    wrap(<VariableEditorModal onClose={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/^Code$/i), { target: { value: 'v1' } })
    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: 'V One' } })
    // advance to save (default expression is const 0 → valid scalar)
    fireEvent.click(screen.getByRole('button', { name: /Save/i }))
    await waitFor(() => expect(createMock).toHaveBeenCalled())
    const body = createMock.mock.calls[0][0]
    expect(body).toMatchObject({ code: 'v1', name: 'V One', kind: 'scalar' })
    expect(body.expression).toBeTruthy()
  })
})
