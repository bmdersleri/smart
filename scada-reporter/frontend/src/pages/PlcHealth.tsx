// src/pages/PlcHealth.tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import {
  getPlcHealth, getPlcIncidents, getIncidentSummary, ackIncident,
  type PlcIncidentRow,
} from '../api/client'
import { parseUtc } from '../utils/time'

// Backend datetimes are UTC; render in the viewer's local zone (fixes the
// "3 hours behind" display when the string has no offset).
const localTime = (s: string) => parseUtc(s).toLocaleString()

function sevClass(sev: string) {
  return sev === 'critical' ? 'bg-red-900/30 text-red-300' : 'bg-yellow-900/30 text-yellow-300'
}

export default function PlcHealth() {
  const { t } = useTranslation('plcHealth')
  const { can } = useAuth()
  const qc = useQueryClient()

  const { data: summary } = useQuery({
    queryKey: ['plc-incident-summary'],
    queryFn: () => getIncidentSummary().then((r) => r.data),
    refetchInterval: 10000,
  })
  const { data: open = [] } = useQuery({
    queryKey: ['plc-incidents-open'],
    queryFn: () => getPlcIncidents({ open: true }).then((r) => r.data),
    refetchInterval: 10000,
  })
  const { data: health = [] } = useQuery({
    queryKey: ['plc-health'],
    queryFn: () => getPlcHealth().then((r) => r.data),
    refetchInterval: 10000,
  })
  const { data: history = [] } = useQuery({
    queryKey: ['plc-incidents-history'],
    queryFn: () => getPlcIncidents({ open: false, limit: 50 }).then((r) => r.data),
    refetchInterval: 30000,
  })

  const ack = useMutation({
    mutationFn: (id: number) => ackIncident(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plc-incidents-open'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">{t('title')}</h1>
          <p className="text-sm text-gray-500 mt-0.5">{t('subtitle')}</p>
        </div>
        <div className="flex gap-2 text-sm">
          <span className="px-3 py-1.5 rounded-lg bg-red-900/30 text-red-300">
            {t('critical')}: {summary?.critical ?? 0}
          </span>
          <span className="px-3 py-1.5 rounded-lg bg-yellow-900/30 text-yellow-300">
            {t('warning')}: {summary?.warning ?? 0}
          </span>
        </div>
      </div>

      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2">{t('open_incidents')}</h2>
        {open.length === 0 ? (
          <p className="text-sm text-green-400">{t('all_healthy')}</p>
        ) : (
          <div className="grid gap-2">
            {open.map((i: PlcIncidentRow) => (
              <div key={i.id} className={`flex items-center justify-between px-4 py-2.5 rounded-lg ${sevClass(i.severity)}`}>
                <div>
                  <span className="font-medium">{i.plc_name || i.plc_ip}</span>
                  <span className="mx-2 opacity-60">·</span>
                  <span>{i.message}</span>
                  <span className="ms-2 text-xs opacity-60">{localTime(i.opened_at)}</span>
                </div>
                {can('plc:manage') && !i.acknowledged_by && (
                  <button onClick={() => ack.mutate(i.id)} className="text-xs px-2 py-1 rounded bg-surface-sunken hover:bg-gray-700 text-gray-200">
                    {t('ack')}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2">{t('per_plc')}</h2>
        <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 uppercase">
                <th className="px-4 py-2 text-start">{t('col_plc')}</th>
                <th className="px-4 py-2 text-start">{t('col_status')}</th>
                <th className="px-4 py-2 text-start">{t('col_last_success')}</th>
                <th className="px-4 py-2 text-start">{t('col_fail')}</th>
                <th className="px-4 py-2 text-start">{t('col_reconnects')}</th>
                <th className="px-4 py-2 text-start">{t('col_last_error')}</th>
              </tr>
            </thead>
            <tbody>
              {health.map((h) => (
                <tr key={`${h.plc_ip}-${h.rack}-${h.slot}`} className="border-t border-edge">
                  <td className="px-4 py-2 text-gray-200">
                    <div className="font-medium">{h.plc_name || h.plc_ip}</div>
                    {h.plc_name && <div className="text-xs text-gray-500 font-mono">{h.plc_ip}</div>}
                  </td>
                  <td className="px-4 py-2">
                    <span className={h.connected ? 'text-green-400' : 'text-red-400'}>
                      {h.connected ? t('connected') : t('disconnected')}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-400">{h.last_success_at ? localTime(h.last_success_at) : '—'}</td>
                  <td className="px-4 py-2 text-gray-400">{h.consecutive_fail}</td>
                  <td className="px-4 py-2 text-gray-400">{h.reconnects_last_min}</td>
                  <td className="px-4 py-2 text-red-400/80 max-w-xs truncate" title={h.last_error ?? ''}>{h.last_error || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2">{t('history')}</h2>
        <div className="text-xs text-gray-500 space-y-1">
          {history.map((i: PlcIncidentRow) => (
            <div key={i.id}>
              {localTime(i.opened_at)} — {i.plc_name || i.plc_ip}: {i.message}
              {i.resolved_at && ` (${t('resolved')}: ${localTime(i.resolved_at)})`}
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
