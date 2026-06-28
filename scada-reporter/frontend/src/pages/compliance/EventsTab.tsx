import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listEvents,
  listPermits,
  addEventNote,
  setEventStatus,
  type ComplianceEvent,
  type ComplianceEventFilters,
} from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { Card } from './helpers'
import { fmtDateTime, fmtNum } from './format'
import { EVENT_STATUSES, SEVERITIES, STATUS_ACCENT, SEVERITY_ACCENT } from './constants'

export default function EventsTab() {
  const { t, i18n } = useTranslation(['compliance', 'common'])
  const { user } = useAuth()
  const qc = useQueryClient()
  const canAct = user?.role === 'admin' || user?.role === 'operator'
  const locale = i18n.language

  const [filters, setFilters] = useState<ComplianceEventFilters>({ limit: 100, offset: 0 })
  const [severity, setSeverity] = useState('')
  const [selected, setSelected] = useState<ComplianceEvent | null>(null)

  const { data: permits = [] } = useQuery({
    queryKey: ['compliance-permits'],
    queryFn: () => listPermits().then((r) => r.data),
  })

  const { data, isLoading, isError } = useQuery({
    queryKey: ['compliance-events', filters],
    queryFn: () => listEvents(filters).then((r) => r.data),
  })

  // severity is filtered client-side (backend list does not expose it).
  const rows = (data?.items ?? []).filter((e) => !severity || e.severity === severity)

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['compliance-events'] })
    qc.invalidateQueries({ queryKey: ['compliance-overview'] })
  }

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <Card className="p-4 flex flex-wrap gap-2 items-end">
        <div className="flex flex-col">
          <label className="text-xs text-gray-400 mb-1">{t('permit')}</label>
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            value={filters.permit_id ?? ''}
            onChange={(e) =>
              setFilters((f) => ({ ...f, permit_id: e.target.value ? Number(e.target.value) : undefined }))
            }
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
          <label className="text-xs text-gray-400 mb-1">{t('status')}</label>
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            value={filters.status ?? ''}
            onChange={(e) =>
              setFilters((f) => ({ ...f, status: e.target.value || undefined }))
            }
          >
            <option value="">{t('all_statuses')}</option>
            {EVENT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`status_${s}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-gray-400 mb-1">{t('severity')}</label>
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            <option value="">{t('all_severities')}</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {t(`severity_${s}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-gray-400 mb-1">{t('period_start')}</label>
          <input
            type="datetime-local"
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                start: e.target.value ? new Date(e.target.value).toISOString() : undefined,
              }))
            }
          />
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-gray-400 mb-1">{t('period_end')}</label>
          <input
            type="datetime-local"
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                end: e.target.value ? new Date(e.target.value).toISOString() : undefined,
              }))
            }
          />
        </div>
      </Card>

      {isLoading && <div className="text-center py-12 text-gray-500">{t('common:loading')}</div>}
      {isError && <div className="text-center py-12 text-red-400">{t('load_error')}</div>}

      {!isLoading && !isError && (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wide text-start">
                <th className="px-3 py-2 text-start">{t('col_type')}</th>
                <th className="px-3 py-2 text-start">{t('col_severity')}</th>
                <th className="px-3 py-2 text-end">{t('col_observed')}</th>
                <th className="px-3 py-2 text-end">{t('col_limit')}</th>
                <th className="px-3 py-2 text-start">{t('col_period')}</th>
                <th className="px-3 py-2 text-end">{t('col_notes')}</th>
                <th className="px-3 py-2 text-start">{t('col_status')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr
                  key={e.id}
                  className="border-t border-edge hover:bg-white/5 cursor-pointer"
                  onClick={() => setSelected(e)}
                >
                  <td className="px-3 py-2 text-gray-200">{t(`event_type_${e.event_type}`)}</td>
                  <td className={`px-3 py-2 ${SEVERITY_ACCENT[e.severity] ?? 'text-gray-300'}`}>
                    {t(`severity_${e.severity}`, e.severity)}
                  </td>
                  <td className="px-3 py-2 text-end font-mono text-gray-300">{fmtNum(e.observed_value)}</td>
                  <td className="px-3 py-2 text-end font-mono text-gray-300">{fmtNum(e.limit_value)}</td>
                  <td className="px-3 py-2 text-gray-400 text-xs">
                    {fmtDateTime(e.period_start, locale)} – {fmtDateTime(e.period_end, locale)}
                  </td>
                  <td className="px-3 py-2 text-end text-gray-300">{e.note_count}</td>
                  <td className={`px-3 py-2 ${STATUS_ACCENT[e.status] ?? 'text-gray-300'}`}>
                    {t(`status_${e.status}`)}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center text-gray-500">
                    {t('no_events')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {data && (
            <div className="px-3 py-2 text-xs text-gray-500 border-t border-edge">
              {t('total_events', { count: data.total })}
            </div>
          )}
        </Card>
      )}

      {selected && (
        <EventDetail
          event={selected}
          canAct={canAct}
          onClose={() => setSelected(null)}
          onChanged={(updated) => {
            setSelected(updated)
            invalidate()
          }}
        />
      )}
    </div>
  )
}

function EventDetail({
  event,
  canAct,
  onClose,
  onChanged,
}: {
  event: ComplianceEvent
  canAct: boolean
  onClose: () => void
  onChanged: (e: ComplianceEvent) => void
}) {
  const { t, i18n } = useTranslation(['compliance', 'common'])
  const locale = i18n.language
  const [note, setNote] = useState('')
  const [waiveReason, setWaiveReason] = useState('')
  const [err, setErr] = useState('')

  const noteMut = useMutation({
    mutationFn: () => addEventNote(event.id, note),
    onSuccess: () => {
      setNote('')
      // note_count is recomputed server-side on next list fetch; bump locally too.
      onChanged({ ...event, note_count: event.note_count + 1 })
    },
    onError: (e: unknown) => {
      const ax = e as { response?: { data?: { detail?: string } } }
      setErr(ax.response?.data?.detail || t('note_error'))
    },
  })

  const statusMut = useMutation({
    mutationFn: (status: string) =>
      setEventStatus(event.id, {
        status,
        waive_reason: status === 'waived' ? waiveReason : undefined,
      }).then((r) => r.data),
    onSuccess: (updated) => {
      setErr('')
      setWaiveReason('')
      onChanged(updated)
    },
    onError: (e: unknown) => {
      const ax = e as { response?: { data?: { detail?: string } } }
      setErr(ax.response?.data?.detail || t('status_error'))
    },
  })

  const applyStatus = (status: string) => {
    setErr('')
    if (status === 'waived' && !waiveReason.trim()) {
      setErr(t('waive_reason_required'))
      return
    }
    statusMut.mutate(status)
  }

  const evidenceEntries = event.evidence ? Object.entries(event.evidence) : []

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-40" onClick={onClose}>
      <div
        className="bg-surface-raised border border-white/10 rounded-2xl p-5 w-full max-w-2xl max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-medium text-white">
            {t(`event_type_${event.event_type}`)} · #{event.id}
          </h3>
          <button className="text-gray-400 hover:text-white" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 text-sm mb-4">
          <div>
            <span className="text-gray-500">{t('col_status')}: </span>
            <span className={STATUS_ACCENT[event.status] ?? 'text-gray-300'}>
              {t(`status_${event.status}`)}
            </span>
          </div>
          <div>
            <span className="text-gray-500">{t('col_severity')}: </span>
            <span className={SEVERITY_ACCENT[event.severity] ?? 'text-gray-300'}>
              {t(`severity_${event.severity}`, event.severity)}
            </span>
          </div>
          <div>
            <span className="text-gray-500">{t('col_observed')}: </span>
            <span className="font-mono text-gray-300">{fmtNum(event.observed_value)}</span>
          </div>
          <div>
            <span className="text-gray-500">{t('col_limit')}: </span>
            <span className="font-mono text-gray-300">{fmtNum(event.limit_value)}</span>
          </div>
          <div className="col-span-2 text-xs text-gray-400">
            {fmtDateTime(event.period_start, locale)} – {fmtDateTime(event.period_end, locale)}
          </div>
          {event.waive_reason && (
            <div className="col-span-2 text-xs text-gray-400">
              {t('waive_reason')}: {event.waive_reason}
            </div>
          )}
        </div>

        {/* Evidence */}
        <div className="mb-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t('evidence')}</p>
          {evidenceEntries.length === 0 ? (
            <p className="text-xs text-gray-600">{t('no_evidence')}</p>
          ) : (
            <table className="w-full text-xs">
              <tbody>
                {evidenceEntries.map(([k, v]) => (
                  <tr key={k} className="border-t border-edge">
                    <td className="py-1 pe-3 text-gray-500 font-mono align-top">{k}</td>
                    <td className="py-1 text-gray-300 font-mono break-all">
                      {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Notes */}
        <div className="mb-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
            {t('notes')} ({event.note_count})
          </p>
          {canAct ? (
            <div className="flex gap-2">
              <input
                className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm flex-1"
                placeholder={t('add_note_placeholder')}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <button
                className="bg-blue-600 hover:bg-blue-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
                disabled={!note.trim() || noteMut.isPending}
                onClick={() => noteMut.mutate()}
              >
                {t('add_note')}
              </button>
            </div>
          ) : (
            <p className="text-xs text-gray-600">{t('view_only')}</p>
          )}
        </div>

        {/* Status transitions */}
        {canAct && (
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t('change_status')}</p>
            <input
              className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm w-full mb-2"
              placeholder={t('waive_reason_placeholder')}
              value={waiveReason}
              onChange={(e) => setWaiveReason(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              <button
                className="bg-amber-600 hover:bg-amber-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
                disabled={statusMut.isPending}
                onClick={() => applyStatus('acknowledged')}
              >
                {t('status_acknowledged')}
              </button>
              <button
                className="bg-green-600 hover:bg-green-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
                disabled={statusMut.isPending}
                onClick={() => applyStatus('resolved')}
              >
                {t('status_resolved')}
              </button>
              <button
                className="bg-gray-600 hover:bg-gray-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
                disabled={statusMut.isPending}
                onClick={() => applyStatus('waived')}
              >
                {t('status_waived')}
              </button>
            </div>
          </div>
        )}

        {err && <p className="text-xs text-red-400 mt-2">{err}</p>}
      </div>
    </div>
  )
}
