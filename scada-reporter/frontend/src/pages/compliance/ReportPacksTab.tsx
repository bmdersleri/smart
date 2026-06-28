import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listPermits,
  listReportPacks,
  createReportPack,
  getReportPack,
  generateReportPack,
  submitReportPackReview,
  approveReportPack,
  deleteReportPack,
  downloadReportPack,
  type ComplianceReportPack,
  type ComplianceReportPackDetail,
  type ComplianceReportPackFormat,
} from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { Card } from './helpers'
import { fmtDateTime, startOfMonthISO, nowISO } from './format'
import { PACK_STATUS_ACCENT } from './constants'

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation(['compliance'])
  return (
    <span className={`text-xs font-medium ${PACK_STATUS_ACCENT[status] ?? 'text-gray-300'}`}>
      {t(`pack_status_${status}`, status)}
    </span>
  )
}

export default function ReportPacksTab({ focusPackId }: { focusPackId?: number | null } = {}) {
  const { t, i18n } = useTranslation(['compliance', 'common'])
  const { user } = useAuth()
  const qc = useQueryClient()
  const locale = i18n.language
  const isAdmin = user?.role === 'admin'
  const canAct = user?.role === 'admin' || user?.role === 'operator'

  const [permitId, setPermitId] = useState<number | undefined>(undefined)
  const [start, setStart] = useState(startOfMonthISO())
  const [end, setEnd] = useState(nowISO())
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [err, setErr] = useState('')

  // When the assistant links a pack, select it so its detail loads. Adjust
  // state during render (React's recommended pattern over an effect) so a fresh
  // focus id wins until the user clicks a different pack.
  const [consumedFocus, setConsumedFocus] = useState<number | null>(null)
  if (focusPackId != null && focusPackId !== consumedFocus) {
    setConsumedFocus(focusPackId)
    setSelectedId(focusPackId)
  }

  const { data: permits = [] } = useQuery({
    queryKey: ['compliance-permits'],
    queryFn: () => listPermits().then((r) => r.data),
  })

  const {
    data: packs,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['compliance-report-packs', permitId],
    queryFn: () => listReportPacks(permitId).then((r) => r.data),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['compliance-report-packs'] })
    qc.invalidateQueries({ queryKey: ['compliance-overview'] })
  }

  const onErr = (e: unknown) => {
    const ax = e as { response?: { data?: { detail?: string } } }
    setErr(ax.response?.data?.detail || t('save_error'))
  }

  const createMut = useMutation({
    mutationFn: () => {
      if (permitId === undefined) throw new Error('permit_required')
      return createReportPack({
        permit_id: permitId,
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
      })
    },
    onSuccess: (res) => {
      setErr('')
      invalidate()
      setSelectedId(res.data.id)
    },
    onError: onErr,
  })

  const onCreate = () => {
    setErr('')
    if (permitId === undefined) {
      setErr(t('pack_select_permit'))
      return
    }
    createMut.mutate()
  }

  return (
    <div className="grid md:grid-cols-[20rem_1fr] gap-4">
      {/* Left: period picker + pack list */}
      <div className="space-y-3">
        <Card className="p-3 grid gap-2">
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
          {canAct && (
            <>
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
                disabled={createMut.isPending}
                onClick={onCreate}
              >
                {t('pack_create')}
              </button>
              {err && <p className="text-xs text-red-400">{err}</p>}
            </>
          )}
        </Card>

        {isLoading && (
          <Card className="p-6 text-center text-gray-500 text-sm">{t('common:loading')}</Card>
        )}
        {isError && (
          <Card className="p-6 text-center text-red-400 text-sm">{t('load_error')}</Card>
        )}
        {!isLoading && !isError && (
          <Card className="overflow-hidden">
            <ul>
              {(packs?.items ?? []).map((p: ComplianceReportPack) => (
                <li key={p.id}>
                  <button
                    className={`w-full text-start px-3 py-2 text-sm border-t border-edge first:border-t-0 hover:bg-white/5 ${
                      selectedId === p.id ? 'bg-cyan-500/10 text-cyan-300' : 'text-gray-200'
                    }`}
                    onClick={() => setSelectedId(p.id)}
                  >
                    <span className="flex items-center justify-between">
                      <span className="font-medium">#{p.id}</span>
                      <StatusBadge status={p.status} />
                    </span>
                    <span className="block text-xs text-gray-500">
                      {fmtDateTime(p.period_start, locale)} – {fmtDateTime(p.period_end, locale)}
                    </span>
                  </button>
                </li>
              ))}
              {(packs?.items.length ?? 0) === 0 && (
                <li className="px-3 py-6 text-center text-sm text-gray-500">{t('no_packs')}</li>
              )}
            </ul>
            {packs && (
              <div className="px-3 py-2 text-xs text-gray-500 border-t border-edge">
                {t('total_packs', { count: packs.total })}
              </div>
            )}
          </Card>
        )}
      </div>

      {/* Right: pack detail */}
      <div>
        {selectedId === null ? (
          <Card className="p-8 text-center text-gray-500 text-sm">{t('pack_select_hint')}</Card>
        ) : (
          <PackDetail
            packId={selectedId}
            isAdmin={isAdmin}
            canAct={canAct}
            onChanged={invalidate}
            onDeleted={() => {
              setSelectedId(null)
              invalidate()
            }}
          />
        )}
      </div>
    </div>
  )
}

function PackDetail({
  packId,
  isAdmin,
  canAct,
  onChanged,
  onDeleted,
}: {
  packId: number
  isAdmin: boolean
  canAct: boolean
  onChanged: () => void
  onDeleted: () => void
}) {
  const { t, i18n } = useTranslation(['compliance', 'common'])
  const qc = useQueryClient()
  const locale = i18n.language
  const [err, setErr] = useState('')

  const {
    data: pack,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['compliance-report-pack', packId],
    queryFn: () => getReportPack(packId).then((r) => r.data),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['compliance-report-pack', packId] })
    onChanged()
  }
  const onErr = (e: unknown) => {
    const ax = e as { response?: { data?: { detail?: string } } }
    setErr(ax.response?.data?.detail || t('save_error'))
  }

  const generateMut = useMutation({
    mutationFn: () => generateReportPack(packId),
    onSuccess: () => {
      setErr('')
      refresh()
    },
    onError: onErr,
  })
  const submitMut = useMutation({
    mutationFn: () => submitReportPackReview(packId),
    onSuccess: () => {
      setErr('')
      refresh()
    },
    onError: onErr,
  })
  const approveMut = useMutation({
    mutationFn: () => approveReportPack(packId),
    onSuccess: () => {
      setErr('')
      refresh()
    },
    onError: onErr,
  })
  const deleteMut = useMutation({
    mutationFn: () => deleteReportPack(packId),
    onSuccess: () => {
      setErr('')
      onDeleted()
    },
    onError: onErr,
  })

  async function onDownload(format: ComplianceReportPackFormat) {
    setErr('')
    try {
      const res = await downloadReportPack(packId, format)
      const ext = format === 'excel' ? 'xlsx' : format
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `compliance_report_pack_${packId}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      // An approved pack flips to exported on download — refresh status.
      refresh()
    } catch (e) {
      onErr(e)
    }
  }

  if (isLoading)
    return <Card className="p-8 text-center text-gray-500 text-sm">{t('common:loading')}</Card>
  if (isError || !pack)
    return <Card className="p-8 text-center text-red-400 text-sm">{t('load_error')}</Card>

  const detail = pack as ComplianceReportPackDetail
  const blockers = detail.blocking_issues ?? []
  const hasBlockers = blockers.length > 0
  const outputsReady = pack.has_pdf && pack.has_xlsx && pack.has_json
  const isImmutable = pack.status === 'approved' || pack.status === 'exported'
  const busy =
    generateMut.isPending || submitMut.isPending || approveMut.isPending || deleteMut.isPending

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-white">
          {t('pack')} #{pack.id}
        </h3>
        <StatusBadge status={pack.status} />
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="col-span-2 text-xs text-gray-400">
          {fmtDateTime(pack.period_start, locale)} – {fmtDateTime(pack.period_end, locale)}
        </div>
        <div>
          <span className="text-gray-500">{t('pack_outputs')}: </span>
          <span className="text-gray-300">
            {outputsReady ? t('pack_outputs_ready') : t('pack_outputs_missing')}
          </span>
        </div>
        {pack.approved_at && (
          <div>
            <span className="text-gray-500">{t('pack_approved_at')}: </span>
            <span className="text-gray-300">{fmtDateTime(pack.approved_at, locale)}</span>
          </div>
        )}
      </div>

      {pack.error_message && (
        <div className="text-xs text-red-400 break-all">
          {t('pack_error')}: {pack.error_message}
        </div>
      )}

      {/* Blocking issues / readiness */}
      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t('pack_readiness')}</p>
        {hasBlockers ? (
          <div className="text-xs text-amber-400">
            <p className="mb-1">{t('pack_blocking_issues')}</p>
            <ul className="list-disc ps-5 space-y-0.5">
              {blockers.map((b) => (
                <li key={b.event_id}>
                  #{b.event_id} · {t(`event_type_${b.event_type}`, b.event_type)} ·{' '}
                  {t(`status_${b.status}`, b.status)}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-xs text-green-400">{t('pack_no_blocking_issues')}</p>
        )}
      </div>

      {/* Downloads */}
      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t('pack_download')}</p>
        <div className="flex flex-wrap gap-2">
          <button
            className="bg-surface-sunken hover:bg-white/10 px-3 py-1 rounded text-sm text-gray-200 disabled:opacity-40"
            disabled={!pack.has_pdf}
            onClick={() => onDownload('pdf')}
          >
            PDF
          </button>
          <button
            className="bg-surface-sunken hover:bg-white/10 px-3 py-1 rounded text-sm text-gray-200 disabled:opacity-40"
            disabled={!pack.has_xlsx}
            onClick={() => onDownload('excel')}
          >
            Excel
          </button>
          <button
            className="bg-surface-sunken hover:bg-white/10 px-3 py-1 rounded text-sm text-gray-200 disabled:opacity-40"
            disabled={!pack.has_json}
            onClick={() => onDownload('json')}
          >
            JSON
          </button>
        </div>
      </div>

      {/* Workflow actions */}
      {canAct && (
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t('pack_actions')}</p>
          <div className="flex flex-wrap gap-2">
            <button
              className="bg-blue-600 hover:bg-blue-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
              disabled={busy || isImmutable}
              onClick={() => generateMut.mutate()}
            >
              {t('pack_generate')}
            </button>
            <button
              className="bg-amber-600 hover:bg-amber-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
              disabled={busy || pack.status !== 'draft' || !outputsReady}
              onClick={() => submitMut.mutate()}
            >
              {t('pack_submit_review')}
            </button>
            {isAdmin && (
              <button
                className="bg-green-600 hover:bg-green-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
                disabled={busy || isImmutable || !outputsReady || hasBlockers}
                onClick={() => approveMut.mutate()}
              >
                {t('pack_approve')}
              </button>
            )}
            {isAdmin && (pack.status === 'draft' || pack.status === 'failed') && (
              <button
                className="bg-gray-600 hover:bg-gray-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
                disabled={busy}
                onClick={() => {
                  if (confirm(t('pack_confirm_delete'))) deleteMut.mutate()
                }}
              >
                {t('common:delete')}
              </button>
            )}
          </div>
        </div>
      )}

      {err && <p className="text-xs text-red-400">{err}</p>}
    </Card>
  )
}
