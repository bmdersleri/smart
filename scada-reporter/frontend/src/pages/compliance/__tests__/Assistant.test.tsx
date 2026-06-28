import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AssistantTab from '../AssistantTab'
import * as client from '../../../api/client'
import type { ComplianceAssistantResponse } from '../../../api/client'

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

const noop = () => {}

function renderTab() {
  return render(
    wrap(<AssistantTab onOpenEvent={noop} onOpenPack={noop} onOpenPermit={noop} />),
  )
}

const READINESS: ComplianceAssistantResponse = {
  intent: 'readiness',
  answer: 'Period is NOT report-ready: 1 required explanation is still open.',
  links: [
    { type: 'event', id: 11 },
    { type: 'permit', id: 1 },
  ],
  data: {},
  proposed_action: null,
}

const DRAFT: ComplianceAssistantResponse = {
  intent: 'draft_explanation',
  answer: 'Drafted an operator explanation for event 11.',
  links: [{ type: 'event', id: 11 }],
  data: { draft: 'A limit exceedance was recorded for parameter X.' },
  proposed_action: null,
}

const CREATE_PACK: ComplianceAssistantResponse = {
  intent: 'create_pack',
  answer: 'Proposed creating a report pack for permit 1.',
  links: [{ type: 'permit', id: 1 }],
  data: {},
  proposed_action: {
    action: 'create_report_pack',
    permit_id: 1,
    period_start: '2026-05-01T00:00:00',
    period_end: '2026-05-31T23:59:59',
  },
}

describe('Compliance AssistantTab', () => {
  beforeEach(() => {
    role = 'operator'
    vi.restoreAllMocks()
    vi.spyOn(client, 'listPermits').mockResolvedValue({
      data: [{ id: 1, name: 'P1', is_active: true }],
    } as never)
  })

  it('renders the answer text and clickable link chips from a mocked response', async () => {
    vi.spyOn(client, 'askComplianceAssistant').mockResolvedValue({ data: READINESS } as never)

    renderTab()
    fireEvent.click(screen.getByText('ai_prompt_readiness'))

    await waitFor(() => expect(screen.getByText(READINESS.answer)).toBeInTheDocument())
    // Link chips for the event + permit ids.
    expect(screen.getByText(/ai_link_event #11/)).toBeInTheDocument()
    expect(screen.getByText(/ai_link_permit #1/)).toBeInTheDocument()
  })

  it('shows Save-as-note for a draft response (operator) and saves on click', async () => {
    vi.spyOn(client, 'askComplianceAssistant').mockResolvedValue({ data: DRAFT } as never)
    const noteSpy = vi
      .spyOn(client, 'addEventNote')
      .mockResolvedValue({ data: { id: 1 } } as never)

    renderTab()
    fireEvent.click(screen.getByText('ai_prompt_draft'))

    await waitFor(() => expect(screen.getByText('ai_save_note')).toBeInTheDocument())
    expect(screen.getByText(DRAFT.data.draft as string)).toBeInTheDocument()

    fireEvent.click(screen.getByText('ai_save_note'))
    await waitFor(() =>
      expect(noteSpy).toHaveBeenCalledWith(11, DRAFT.data.draft),
    )
  })

  it('hides Save-as-note from a viewer-role user', async () => {
    role = 'viewer'
    vi.spyOn(client, 'askComplianceAssistant').mockResolvedValue({ data: DRAFT } as never)

    renderTab()
    fireEvent.click(screen.getByText('ai_prompt_draft'))

    // The draft text still renders for the viewer…
    await waitFor(() => expect(screen.getByText(DRAFT.data.draft as string)).toBeInTheDocument())
    // …but the write action is hidden.
    expect(screen.queryByText('ai_save_note')).not.toBeInTheDocument()
  })

  it('shows Create-pack for a create_pack proposal (operator) and creates on click', async () => {
    vi.spyOn(client, 'askComplianceAssistant').mockResolvedValue({ data: CREATE_PACK } as never)
    const createSpy = vi
      .spyOn(client, 'createReportPack')
      .mockResolvedValue({ data: { id: 99 } } as never)

    renderTab()
    fireEvent.click(screen.getByText('ai_prompt_create_pack'))

    await waitFor(() => expect(screen.getByText('ai_create_pack')).toBeInTheDocument())
    fireEvent.click(screen.getByText('ai_create_pack'))
    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith({
        permit_id: 1,
        start: '2026-05-01T00:00:00',
        end: '2026-05-31T23:59:59',
      }),
    )
  })

  it('hides Create-pack from a viewer-role user', async () => {
    role = 'viewer'
    vi.spyOn(client, 'askComplianceAssistant').mockResolvedValue({ data: CREATE_PACK } as never)

    renderTab()
    fireEvent.click(screen.getByText('ai_prompt_create_pack'))

    await waitFor(() => expect(screen.getByText(CREATE_PACK.answer)).toBeInTheDocument())
    expect(screen.queryByText('ai_create_pack')).not.toBeInTheDocument()
    // Viewer sees the read-only notice instead.
    expect(screen.getByText('view_only')).toBeInTheDocument()
  })
})
