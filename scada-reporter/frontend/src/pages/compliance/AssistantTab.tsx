import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  askComplianceAssistant,
  listPermits,
  addEventNote,
  createReportPack,
  type ComplianceAssistantResponse,
  type ComplianceAssistantLink,
} from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { Card } from './helpers'

// The five example prompts from the compliance design ("AI Compliance Assistant").
// Each maps to an i18n key; the English/Turkish text matches the design wording.
const EXAMPLE_PROMPT_KEYS = [
  'ai_prompt_readiness',
  'ai_prompt_breaches',
  'ai_prompt_missing',
  'ai_prompt_draft',
  'ai_prompt_create_pack',
] as const

export default function AssistantTab({
  onOpenEvent,
  onOpenPack,
  onOpenPermit,
}: {
  onOpenEvent: (id: number) => void
  onOpenPack: (id: number) => void
  onOpenPermit: (id: number) => void
}) {
  const { t } = useTranslation(['compliance', 'common'])
  const { user } = useAuth()
  const qc = useQueryClient()
  // GUARDRAIL: write buttons (Save-as-note / Create-pack) are operator+admin only.
  const canAct = user?.role === 'admin' || user?.role === 'operator'

  const [question, setQuestion] = useState('')
  const [permitId, setPermitId] = useState<number | undefined>(undefined)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [result, setResult] = useState<ComplianceAssistantResponse | null>(null)
  const [err, setErr] = useState('')
  // Track whether the proposed pack was created / a draft was saved, so the
  // one-shot write buttons reflect their state after the explicit user action.
  const [packCreated, setPackCreated] = useState(false)
  const [noteSaved, setNoteSaved] = useState(false)

  const { data: permits = [] } = useQuery({
    queryKey: ['compliance-permits'],
    queryFn: () => listPermits().then((r) => r.data),
  })

  const onErr = (e: unknown, fallbackKey: string) => {
    const ax = e as { response?: { data?: { detail?: string } } }
    setErr(ax.response?.data?.detail || t(fallbackKey))
  }

  const askMut = useMutation({
    mutationFn: (q: string) =>
      askComplianceAssistant({
        question: q,
        permit_id: permitId,
        start: start ? new Date(start).toISOString() : undefined,
        end: end ? new Date(end).toISOString() : undefined,
      }).then((r) => r.data),
    onSuccess: (data) => {
      setErr('')
      setPackCreated(false)
      setNoteSaved(false)
      setResult(data)
    },
    onError: (e) => onErr(e, 'ai_error'),
  })

  const draftEventId = result?.links.find((l) => l.type === 'event')?.id ?? null
  const draft = typeof result?.data?.draft === 'string' ? result.data.draft : null

  const saveNoteMut = useMutation({
    mutationFn: () => {
      if (draftEventId === null || !draft) throw new Error('no_draft')
      return addEventNote(draftEventId, draft)
    },
    onSuccess: () => {
      setErr('')
      setNoteSaved(true)
      qc.invalidateQueries({ queryKey: ['compliance-events'] })
      qc.invalidateQueries({ queryKey: ['compliance-overview'] })
    },
    onError: (e) => onErr(e, 'note_error'),
  })

  const createPackMut = useMutation({
    mutationFn: () => {
      const pa = result?.proposed_action
      if (!pa || pa.permit_id === undefined || !pa.period_start || !pa.period_end) {
        throw new Error('no_action')
      }
      return createReportPack({
        permit_id: pa.permit_id,
        start: pa.period_start,
        end: pa.period_end,
      })
    },
    onSuccess: (res) => {
      setErr('')
      setPackCreated(true)
      qc.invalidateQueries({ queryKey: ['compliance-report-packs'] })
      qc.invalidateQueries({ queryKey: ['compliance-overview'] })
      onOpenPack(res.data.id)
    },
    onError: (e) => onErr(e, 'save_error'),
  })

  const submit = (q: string) => {
    const trimmed = q.trim()
    if (!trimmed || askMut.isPending) return
    setQuestion(trimmed)
    askMut.mutate(trimmed)
  }

  const onLinkClick = (link: ComplianceAssistantLink) => {
    if (link.type === 'event') onOpenEvent(link.id)
    else if (link.type === 'pack') onOpenPack(link.id)
    else if (link.type === 'permit') onOpenPermit(link.id)
  }

  const proposed = result?.proposed_action
  const canCreatePack =
    !!proposed &&
    proposed.action === 'create_report_pack' &&
    proposed.permit_id !== undefined &&
    !!proposed.period_start &&
    !!proposed.period_end

  return (
    <div className="grid lg:grid-cols-[22rem_1fr] gap-4">
      {/* Left: question form + scope + quick prompts */}
      <div className="space-y-3">
        <Card className="p-4 space-y-3">
          <div className="flex flex-col">
            <label className="text-xs text-gray-400 mb-1">{t('ai_question')}</label>
            <textarea
              className="bg-surface-sunken px-2 py-1.5 rounded text-gray-200 text-sm min-h-[4rem] resize-y"
              placeholder={t('ai_question_placeholder')}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(question)
              }}
            />
          </div>

          {/* Optional scope: permit + period passed straight to the assistant. */}
          <div className="flex flex-col">
            <label className="text-xs text-gray-400 mb-1">{t('permit')}</label>
            <select
              className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
              value={permitId ?? ''}
              onChange={(e) => setPermitId(e.target.value ? Number(e.target.value) : undefined)}
            >
              <option value="">{t('all_permits')}</option>
              {permits.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-gray-400 mb-1">{t('period_start')}</label>
            <input
              type="datetime-local"
              className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-gray-400 mb-1">{t('period_end')}</label>
            <input
              type="datetime-local"
              className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>

          <button
            className="bg-blue-600 hover:bg-blue-500 px-3 py-1.5 rounded text-sm text-white disabled:opacity-50"
            disabled={!question.trim() || askMut.isPending}
            onClick={() => submit(question)}
          >
            {t('ai_ask')}
          </button>
        </Card>

        <Card className="p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">{t('ai_examples')}</p>
          <div className="flex flex-col gap-2">
            {EXAMPLE_PROMPT_KEYS.map((key) => (
              <button
                key={key}
                className="text-start text-sm text-cyan-300 hover:text-cyan-200 bg-surface-sunken hover:bg-white/5 rounded px-2 py-1.5 disabled:opacity-50"
                disabled={askMut.isPending}
                onClick={() => submit(t(key))}
              >
                {t(key)}
              </button>
            ))}
          </div>
        </Card>
      </div>

      {/* Right: answer + links + actions */}
      <div>
        {askMut.isPending && (
          <Card className="p-8 text-center text-gray-500 text-sm">{t('common:loading')}</Card>
        )}

        {!askMut.isPending && !result && (
          <Card className="p-8 text-center text-gray-500 text-sm">{t('ai_empty')}</Card>
        )}

        {!askMut.isPending && result && (
          <Card className="p-5 space-y-4">
            {/* Answer text */}
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t('ai_answer')}</p>
              <p className="text-sm text-gray-200 whitespace-pre-line">{result.answer}</p>
            </div>

            {/* Deterministic ID links as clickable chips */}
            {result.links.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t('ai_links')}</p>
                <div className="flex flex-wrap gap-2">
                  {result.links.map((link, i) => (
                    <button
                      key={`${link.type}-${link.id}-${i}`}
                      className="text-xs font-medium px-2 py-1 rounded border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/10"
                      onClick={() => onLinkClick(link)}
                    >
                      {t(`ai_link_${link.type}`)} #{link.id}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Draft explanation → explicit Save-as-note (operator+admin only) */}
            {draft && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t('ai_draft')}</p>
                <p className="text-sm text-gray-300 whitespace-pre-line bg-surface-sunken rounded p-3">
                  {draft}
                </p>
                {canAct && draftEventId !== null && (
                  <button
                    className="mt-2 bg-blue-600 hover:bg-blue-500 px-3 py-1.5 rounded text-sm text-white disabled:opacity-50"
                    disabled={saveNoteMut.isPending || noteSaved}
                    onClick={() => saveNoteMut.mutate()}
                  >
                    {noteSaved ? t('ai_note_saved') : t('ai_save_note')}
                  </button>
                )}
              </div>
            )}

            {/* Proposed create_pack → explicit Create-pack (operator+admin only) */}
            {canCreatePack && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                  {t('ai_proposed_action')}
                </p>
                {canAct ? (
                  <button
                    className="bg-green-600 hover:bg-green-500 px-3 py-1.5 rounded text-sm text-white disabled:opacity-50"
                    disabled={createPackMut.isPending || packCreated}
                    onClick={() => createPackMut.mutate()}
                  >
                    {packCreated ? t('ai_pack_created') : t('ai_create_pack')}
                  </button>
                ) : (
                  <p className="text-xs text-gray-600">{t('view_only')}</p>
                )}
              </div>
            )}

            {err && <p className="text-xs text-red-400">{err}</p>}
          </Card>
        )}
      </div>
    </div>
  )
}
