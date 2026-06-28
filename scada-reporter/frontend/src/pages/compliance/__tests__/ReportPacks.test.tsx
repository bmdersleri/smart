import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ReportPacksTab from '../ReportPacksTab'
import * as client from '../../../api/client'
import type { ComplianceReportPack, ComplianceReportPackDetail } from '../../../api/client'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))

let role = 'operator'
vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({ user: { role } }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const PACK: ComplianceReportPack = {
  id: 7,
  permit_id: 1,
  period_start: '2026-06-01T00:00:00Z',
  period_end: '2026-06-30T23:59:59Z',
  status: 'ready_for_review',
  error_message: null,
  prepared_by: 2,
  approved_by: null,
  approved_at: null,
  created_at: '2026-06-15T00:00:00Z',
  updated_at: '2026-06-15T00:00:00Z',
  has_pdf: true,
  has_xlsx: true,
  has_json: true,
}

function detail(over: Partial<ComplianceReportPackDetail> = {}): ComplianceReportPackDetail {
  return { ...PACK, blocking_issues: [], ...over }
}

describe('Compliance ReportPacksTab', () => {
  beforeEach(() => {
    role = 'operator'
    vi.restoreAllMocks()
    vi.spyOn(client, 'listPermits').mockResolvedValue({
      data: [{ id: 1, name: 'P1', is_active: true }],
    } as never)
  })

  it('renders the pack list from the mocked API', async () => {
    vi.spyOn(client, 'listReportPacks').mockResolvedValue({
      data: { total: 1, items: [PACK] },
    } as never)

    render(wrap(<ReportPacksTab />))
    await waitFor(() => expect(screen.getByText('#7')).toBeInTheDocument())
    expect(screen.getByText('pack_status_ready_for_review')).toBeInTheDocument()
  })

  it('hides the approve button for non-admin (operator) users', async () => {
    role = 'operator'
    vi.spyOn(client, 'listReportPacks').mockResolvedValue({
      data: { total: 1, items: [PACK] },
    } as never)
    vi.spyOn(client, 'getReportPack').mockResolvedValue({ data: detail() } as never)

    render(wrap(<ReportPacksTab />))
    await waitFor(() => expect(screen.getByText('#7')).toBeInTheDocument())
    fireEvent.click(screen.getByText('#7'))
    await waitFor(() => expect(screen.getByText('pack_generate')).toBeInTheDocument())
    // Operators can generate/submit but never approve.
    expect(screen.queryByText('pack_approve')).not.toBeInTheDocument()
    expect(screen.getByText('pack_submit_review')).toBeInTheDocument()
  })

  it('shows the approve button for admins and disables it when blocking issues exist', async () => {
    role = 'admin'
    vi.spyOn(client, 'listReportPacks').mockResolvedValue({
      data: { total: 1, items: [PACK] },
    } as never)
    vi.spyOn(client, 'getReportPack').mockResolvedValue({
      data: detail({
        blocking_issues: [
          { event_id: 99, parameter_id: 2, event_type: 'needs_explanation', status: 'open' },
        ],
      }),
    } as never)

    render(wrap(<ReportPacksTab />))
    await waitFor(() => expect(screen.getByText('#7')).toBeInTheDocument())
    fireEvent.click(screen.getByText('#7'))

    await waitFor(() => expect(screen.getByText('pack_approve')).toBeInTheDocument())
    // The blocking issue is rendered for the operator to see.
    expect(screen.getByText('pack_blocking_issues')).toBeInTheDocument()
    expect(screen.getByText(/#99/)).toBeInTheDocument()
    // Approve is disabled while a blocking issue is open.
    const approveBtn = screen.getByText('pack_approve') as HTMLButtonElement
    expect(approveBtn.disabled).toBe(true)
  })

  it('enables approve for admins when there are no blocking issues', async () => {
    role = 'admin'
    vi.spyOn(client, 'listReportPacks').mockResolvedValue({
      data: { total: 1, items: [PACK] },
    } as never)
    vi.spyOn(client, 'getReportPack').mockResolvedValue({ data: detail() } as never)

    render(wrap(<ReportPacksTab />))
    await waitFor(() => expect(screen.getByText('#7')).toBeInTheDocument())
    fireEvent.click(screen.getByText('#7'))

    await waitFor(() => expect(screen.getByText('pack_no_blocking_issues')).toBeInTheDocument())
    const approveBtn = screen.getByText('pack_approve') as HTMLButtonElement
    expect(approveBtn.disabled).toBe(false)
  })
})
