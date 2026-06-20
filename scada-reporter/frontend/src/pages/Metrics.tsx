import { useRef, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getMetrics, getDeadbandSavings } from '../api/client'
import type { MetricsSummary } from '../api/client'
import { useSortable } from '../hooks/useSortable'
import SortHeader from '../components/SortHeader'
import { useLogStream } from '../hooks/useLogStream'
import type { LogLine } from '../hooks/useLogStream'

function StatCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-semibold mt-1 font-mono ${accent ?? 'text-white'}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function fmtMs(s: number | null): string {
  if (s === null) return '—'
  return `${(s * 1000).toFixed(1)} ms`
}

function fmtPct(r: number | null): string {
  if (r === null) return '—'
  return `${(r * 100).toFixed(2)} %`
}

const LEVEL_COLOR: Record<string, string> = {
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-400',
  WARNING: 'text-amber-400',
  INFO: 'text-gray-400',
  DEBUG: 'text-gray-600',
}

function LiveConsole() {
  const { t, i18n } = useTranslation(['metrics', 'common'])
  const [level, setLevel] = useState('INFO')
  const [paused, setPaused] = useState(false)
  const { lines, clear } = useLogStream(level, !paused)
  const bodyRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new lines unless paused.
  useEffect(() => {
    if (!paused && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [lines, paused])

  const fmtTime = (ts: string) => {
    const d = new Date(ts)
    return isNaN(d.getTime()) ? ts : d.toLocaleTimeString(i18n.language)
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-white">{t('console_title')}</h2>
          <p className="text-xs text-gray-500">{t('console_sub')}</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
          >
            <option value="INFO">{t('filter_all')}</option>
            <option value="WARNING">{t('filter_warning')}</option>
            <option value="ERROR">{t('filter_error')}</option>
          </select>
          <button
            onClick={() => setPaused((p) => !p)}
            className="px-2 py-1 text-xs rounded border border-gray-700 text-gray-200 hover:bg-gray-800"
          >
            {paused ? t('btn_resume') : t('btn_pause')}
          </button>
          <button
            onClick={clear}
            className="px-2 py-1 text-xs rounded border border-gray-700 text-gray-200 hover:bg-gray-800"
          >
            {t('btn_clear')}
          </button>
        </div>
      </div>
      <div ref={bodyRef} className="h-72 overflow-y-auto font-mono text-xs p-3 space-y-0.5">
        {lines.length === 0 && (
          <p className="text-gray-600 text-center py-8">{t('console_empty')}</p>
        )}
        {lines.map((l: LogLine) => (
          <div key={l.seq} className="flex gap-2 whitespace-pre-wrap break-all">
            <span className="text-gray-600 shrink-0">{fmtTime(l.ts)}</span>
            <span className={`shrink-0 w-16 ${LEVEL_COLOR[l.level] ?? 'text-gray-400'}`}>{l.level}</span>
            <span className="text-gray-500 shrink-0">{l.name}</span>
            <span className={LEVEL_COLOR[l.level] ?? 'text-gray-300'}>{l.msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Metrics() {
  const { t, i18n } = useTranslation(['metrics', 'common'])
  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['metrics'],
    queryFn: () => getMetrics().then((r) => r.data),
    refetchInterval: 2000,
  })

  const { data: savings } = useQuery({
    queryKey: ['deadbandSavings'],
    queryFn: () => getDeadbandSavings(24).then((r) => r.data),
    refetchInterval: 10000,
  })

  const m: MetricsSummary | undefined = data
  const maxAvg = m?.plcs.reduce((acc, p) => Math.max(acc, p.avg_seconds ?? 0), 0) || 0
  const badAccent =
    m?.bad_ratio == null ? 'text-white' : m.bad_ratio > 0.05 ? 'text-red-400' : 'text-green-400'

  // default: slowest PLC on top; clicking a header re-sorts
  const byAvg = [...(m?.plcs ?? [])].sort((a, b) => (b.avg_seconds ?? 0) - (a.avg_seconds ?? 0))
  const { sorted: plcRows, sort, toggle } = useSortable(byAvg)

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">{t('title')}</h1>
          <p className="text-sm text-gray-500">{t('subtitle')}</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          {dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString(i18n.language) : t('connecting')}
        </div>
      </div>

      {isLoading && <div className="text-center py-16 text-gray-500">{t('common:loading')}</div>}
      {isError && <div className="text-center py-16 text-red-400">{t('load_error')}</div>}

      {m && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label={t('rows_written')} value={m.rows_written_total.toLocaleString(i18n.language)} sub={t('rows_written_sub')} accent="text-cyan-300" />
            <StatCard label={t('bad_quality')} value={m.bad_quality_total.toLocaleString(i18n.language)} sub={t('bad_quality_sub')} accent={badAccent} />
            <StatCard label={t('bad_ratio')} value={fmtPct(m.bad_ratio)} sub={t('bad_ratio_sub')} accent={badAccent} />
            <StatCard label={t('avg_tick')} value={fmtMs(m.tick_avg_seconds)} sub={t('avg_tick_sub', { value: m.tick_count.toLocaleString(i18n.language) })} accent="text-blue-300" />
          </div>

          {/* Deadband (report-by-exception) data savings — last 24 hours, dynamic */}
          {savings && (
            <div className="bg-gradient-to-br from-emerald-950/40 to-gray-900 border border-emerald-800/40 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-medium text-white flex items-center gap-2">
                    <span className="text-emerald-400">♻</span> {t('deadband_title')}
                  </h2>
                  <p className="text-xs text-gray-500">
                    {t('deadband_sub', { hours: savings.window_hours, tags: savings.deadband_tags.toLocaleString(i18n.language) })}
                  </p>
                </div>
                <div className="text-end">
                  <p className="text-4xl font-bold font-mono text-emerald-400">
                    {savings.savings_pct === null ? '—' : `${savings.savings_pct}%`}
                  </p>
                  <p className="text-xs text-gray-500">{t('write_savings')}</p>
                </div>
              </div>

              {/* savings bar: written (actual) vs prevented (savings) */}
              <div className="h-3 bg-gray-800 rounded-full overflow-hidden flex mb-2">
                <div
                  className="h-full bg-emerald-500"
                  style={{ width: `${savings.savings_pct ?? 0}%` }}
                  title={t('rows_prevented_bar', { value: savings.saved_rows.toLocaleString(i18n.language) })}
                />
                <div className="h-full bg-cyan-600/70 flex-1" title={t('rows_written_bar', { value: savings.actual_rows.toLocaleString(i18n.language) })} />
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                <StatCard label={t('rows_prevented')} value={savings.saved_rows.toLocaleString(i18n.language)} sub={t('rows_prevented_sub', { hours: savings.window_hours })} accent="text-emerald-400" />
                <StatCard label={t('rows_written_db')} value={savings.actual_rows.toLocaleString(i18n.language)} sub={t('rows_written_db_sub')} accent="text-cyan-300" />
                <StatCard label={t('without_deadband')} value={savings.expected_rows.toLocaleString(i18n.language)} sub={t('without_deadband_sub')} accent="text-gray-300" />
                <StatCard label={t('daily_savings')} value={`~${savings.saved_rows_per_day.toLocaleString(i18n.language)}`} sub={t('daily_savings_sub')} accent="text-emerald-300" />
              </div>
            </div>
          )}

          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800">
              <h2 className="text-sm font-medium text-white">{t('read_latency_title')}</h2>
              <p className="text-xs text-gray-500">{t('read_latency_sub', { value: m.plcs.length })}</p>
            </div>
            <table className="w-full">
              <thead>
                <tr className="text-xs text-gray-500 uppercase tracking-wide">
                  <SortHeader label={t('col_name')} sortKey="name" sort={sort} onToggle={toggle} />
                  <SortHeader label={t('col_ip')} sortKey="plc" sort={sort} onToggle={toggle} />
                  <SortHeader label={t('col_tag_count')} sortKey="tag_count" sort={sort} onToggle={toggle} align="right" />
                  <SortHeader label={t('col_read_count')} sortKey="count" sort={sort} onToggle={toggle} align="right" />
                  <SortHeader label={t('col_avg_time')} sortKey="avg_seconds" sort={sort} onToggle={toggle} align="right" />
                  <th className="px-4 py-2 text-start w-1/4">{t('col_latency')}</th>
                </tr>
              </thead>
              <tbody>
                {plcRows
                  .map((p) => {
                    const pct = maxAvg > 0 ? ((p.avg_seconds ?? 0) / maxAvg) * 100 : 0
                    const slow = (p.avg_seconds ?? 0) > 0.5
                    return (
                      <tr key={p.plc} className="border-t border-gray-800 hover:bg-gray-800/40">
                        <td className="px-4 py-2 text-sm text-white">{p.name || '—'}</td>
                        <td className="px-4 py-2 text-sm font-mono text-gray-400">{p.plc}</td>
                        <td className="px-4 py-2 text-sm text-end text-gray-300 font-mono">{p.tag_count.toLocaleString(i18n.language)}</td>
                        <td className="px-4 py-2 text-sm text-end text-gray-400 font-mono">{p.count.toLocaleString(i18n.language)}</td>
                        <td className={`px-4 py-2 text-sm text-end font-mono ${slow ? 'text-red-400' : 'text-gray-200'}`}>{fmtMs(p.avg_seconds)}</td>
                        <td className="px-4 py-2">
                          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${slow ? 'bg-red-500' : 'bg-blue-500'}`} style={{ width: `${pct}%` }} />
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                {m.plcs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-500 text-sm">
                      {t('empty_plcs')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <LiveConsole />
        </>
      )}
    </div>
  )
}
