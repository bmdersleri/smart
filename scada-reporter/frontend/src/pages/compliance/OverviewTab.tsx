import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  getComplianceOverview,
  listPermits,
  listEvents,
  runEvaluation,
  type CompliancePermit,
} from '../../api/client'
import { StatCard, Card } from './helpers'
import { startOfMonthISO, nowISO } from './format'

interface OverviewTabProps {
  onOpenEvents: () => void
}

// Group the last-30-day open events into per-day buckets for the trend chart.
function buildTrend(
  dates: string[],
  locale: string,
): { day: string; count: number }[] {
  const buckets = new Map<string, number>()
  const days: string[] = []
  const today = new Date()
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i)
    const key = d.toISOString().slice(0, 10)
    buckets.set(key, 0)
    days.push(key)
  }
  for (const iso of dates) {
    const key = iso.slice(0, 10)
    if (buckets.has(key)) buckets.set(key, (buckets.get(key) ?? 0) + 1)
  }
  return days.map((key) => ({
    day: new Date(key).toLocaleDateString(locale, { month: 'short', day: 'numeric' }),
    count: buckets.get(key) ?? 0,
  }))
}

export default function OverviewTab({ onOpenEvents }: OverviewTabProps) {
  const { t, i18n } = useTranslation(['compliance', 'common'])
  const qc = useQueryClient()
  const locale = i18n.language

  const { data: overview, isLoading, isError } = useQuery({
    queryKey: ['compliance-overview'],
    queryFn: () => getComplianceOverview().then((r) => r.data),
  })

  const { data: permits = [] } = useQuery({
    queryKey: ['compliance-permits'],
    queryFn: () => listPermits().then((r) => r.data),
  })

  // Pull recent events (last 30 days) just to drive the trend chart.
  const thirtyDaysAgo = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - 30)
    return d.toISOString()
  }, [])
  const { data: recentEvents } = useQuery({
    queryKey: ['compliance-events-trend', thirtyDaysAgo],
    queryFn: () => listEvents({ start: thirtyDaysAgo, limit: 500 }).then((r) => r.data),
  })

  const trend = useMemo(
    () => buildTrend((recentEvents?.items ?? []).map((e) => e.created_at), locale),
    [recentEvents, locale],
  )

  // ── Run-evaluation form ──
  const [showEval, setShowEval] = useState(false)
  const [evalPermit, setEvalPermit] = useState<number | ''>('')
  const [evalStart, setEvalStart] = useState(startOfMonthISO())
  const [evalEnd, setEvalEnd] = useState(nowISO())
  const [evalMsg, setEvalMsg] = useState('')

  const evalMut = useMutation({
    mutationFn: () =>
      runEvaluation({
        permit_id: Number(evalPermit),
        start: new Date(evalStart).toISOString(),
        end: new Date(evalEnd).toISOString(),
      }).then((r) => r.data),
    onSuccess: (res) => {
      setEvalMsg(
        t('eval_done', { created: res.created ?? 0, updated: res.updated ?? 0 }),
      )
      qc.invalidateQueries({ queryKey: ['compliance-overview'] })
      qc.invalidateQueries({ queryKey: ['compliance-events'] })
      qc.invalidateQueries({ queryKey: ['compliance-events-trend'] })
    },
    onError: (e: unknown) => {
      const ax = e as { response?: { data?: { detail?: string } } }
      setEvalMsg(ax.response?.data?.detail || t('eval_error'))
    },
  })

  const activePermits = permits.filter((p: CompliancePermit) => p.is_active)

  if (isLoading) return <div className="text-center py-16 text-gray-500">{t('common:loading')}</div>
  if (isError) return <div className="text-center py-16 text-red-400">{t('load_error')}</div>

  const byType = overview?.by_event_type ?? {}
  const openByType = Object.entries(byType)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${t(`event_type_${k}`)}: ${n}`)
    .join(' · ')

  return (
    <div className="space-y-6">
      {/* Counter cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label={t('active_permits')} value={overview?.active_permits ?? 0} accent="text-cyan-300" />
        <StatCard
          label={t('open_events')}
          value={overview?.open_events ?? 0}
          accent={(overview?.open_events ?? 0) > 0 ? 'text-red-400' : 'text-green-400'}
          onClick={onOpenEvents}
        />
        <StatCard label={t('missing_samples')} value={overview?.missing_samples ?? 0} accent="text-amber-400" />
        <StatCard
          label={t('needs_explanation')}
          value={overview?.unresolved_explanations ?? 0}
          accent="text-amber-400"
        />
        <StatCard label={t('packs_waiting')} value={overview?.packs_waiting ?? 0} />
      </div>

      {/* Open-by-type breakdown */}
      <Card className="p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t('open_by_type')}</p>
        <p className="text-sm text-gray-300">{openByType || t('no_open_events')}</p>
      </Card>

      {/* Primary actions */}
      <div className="flex flex-wrap gap-2">
        <button
          className="bg-blue-600 hover:bg-blue-500 px-3 py-1.5 rounded text-sm text-white"
          onClick={() => setShowEval((v) => !v)}
        >
          {t('run_evaluation')}
        </button>
        <button
          className="bg-surface-sunken hover:bg-white/5 border border-edge-strong px-3 py-1.5 rounded text-sm text-gray-200"
          onClick={onOpenEvents}
        >
          {t('open_events_btn')}
        </button>
      </div>

      {showEval && (
        <Card className="p-4 grid gap-2 max-w-xl">
          <h3 className="font-medium text-white text-sm">{t('run_evaluation')}</h3>
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200"
            value={evalPermit}
            onChange={(e) => setEvalPermit(e.target.value ? Number(e.target.value) : '')}
            aria-label={t('permit')}
          >
            <option value="">{t('select_permit')}</option>
            {activePermits.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <label className="text-xs text-gray-400">{t('period_start')}</label>
          <input
            type="datetime-local"
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200"
            value={evalStart}
            onChange={(e) => setEvalStart(e.target.value)}
          />
          <label className="text-xs text-gray-400">{t('period_end')}</label>
          <input
            type="datetime-local"
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200"
            value={evalEnd}
            onChange={(e) => setEvalEnd(e.target.value)}
          />
          <button
            className="bg-blue-600 hover:bg-blue-500 px-3 py-1.5 rounded text-sm text-white mt-1 disabled:opacity-50"
            disabled={!evalPermit || evalMut.isPending}
            onClick={() => {
              setEvalMsg('')
              evalMut.mutate()
            }}
          >
            {evalMut.isPending ? t('common:loading') : t('run')}
          </button>
          {evalMsg && <p className="text-xs text-gray-400">{evalMsg}</p>}
        </Card>
      )}

      {/* 30-day trend */}
      <Card className="p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">{t('event_trend_30d')}</p>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={trend} margin={{ top: 4, right: 8, left: -16, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" />
              <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #1f2937', fontSize: 12 }}
              />
              <Bar dataKey="count" fill="#06b6d4" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  )
}
