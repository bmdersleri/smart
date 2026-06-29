import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import i18n from '../i18n'
import ExcelTemplates from './ExcelTemplates'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: null, can: () => true, logout: vi.fn() }),
}))

vi.mock('../api/client', () => ({
  listFacilityVariables: vi.fn().mockResolvedValue({ data: [{ id: 9, code: 'var_x', is_active: true }] }),
}))

// ExcelTemplates uses raw fetch for its own endpoints; stub global fetch with a
// smarter dispatcher: POST …/inspect returns a proper inspect object; GET
// …/excel-templates returns the list; everything else returns [].
const inspectResult = {
  sheet_name: 'S', header_row: 1, date_col: 'A', data_start_row: 2, date_mode: 'write',
  columns: [{ col_letter: 'B', label: 'L', source_code: '', tag_id: 1, agg: 'last', enabled: true, source_type: 'tag' }],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    json: async () =>
      String(url).includes('/inspect')
        ? inspectResult
        : String(url).includes('excel-templates')
          ? [{ id: 1, name: 'T', sheet_name: 'S', columns: inspectResult.columns }]
          : [],
  })) as unknown as typeof fetch)
})

afterEach(() => vi.unstubAllGlobals())

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('ExcelTemplates variable binding UI', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })

  it('switching a column to variable source reveals the variable picker', async () => {
    const { container } = wrap(<ExcelTemplates />)
    // Enter map view by uploading a file (the page's real affordance).
    // The file input is inside the upload label; trigger it programmatically.
    const mockFile = new File(['fake'], 'test.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    Object.defineProperty(fileInput, 'files', { value: [mockFile], configurable: true })
    fireEvent.change(fileInput)
    // Wait for the map view to render (apiInspect resolves, setView("map"))
    const sourceSel = await screen.findByLabelText(/Source type/i)
    fireEvent.change(sourceSel, { target: { value: 'variable' } })
    expect(await screen.findByLabelText(/Variable/i)).toBeInTheDocument()
  })
})
