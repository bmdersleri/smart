import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getDatabaseStats } from '../../api/client'
import { formatBytes } from '../metricsDb.helper'
import { StatCard } from './metricsShared'

export default function DatabaseTab({ active }: { active: boolean }) {
  const { t, i18n } = useTranslation(['metrics', 'common'])
  const { data: dbStats, isFetching: dbFetching, refetch: refetchDb } = useQuery({
    queryKey: ['database-stats'],
    queryFn: () => getDatabaseStats().then((r) => r.data),
    enabled: active,
    refetchInterval: false,
  })

  return (
    <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl overflow-hidden">
      <div className="px-4 py-3 border-b border-edge flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-white">{t('db_title')}</h2>
        </div>
        <button
          onClick={() => refetchDb()}
          disabled={dbFetching}
          className="px-2 py-1 text-xs rounded border border-edge-strong text-gray-200 hover:bg-white/5 disabled:opacity-50"
        >
          {t('db_refresh')}
        </button>
      </div>
      {dbStats && (
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label={t('db_size')} value={formatBytes(dbStats.size_bytes)} accent="text-blue-300" />
            <StatCard label={t('db_total')} value={`${dbStats.total_is_estimate ? '~' : ''}${dbStats.total_readings.toLocaleString(i18n.language)}`} accent="text-cyan-300" />
            <StatCard label={t('db_earliest')} value={dbStats.earliest ? new Date(dbStats.earliest).toLocaleDateString(i18n.language) : '—'} />
            <StatCard label={t('db_tags')} value={dbStats.tag_count.toLocaleString(i18n.language)} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label={t('db_last_day')} value={dbStats.last_day.toLocaleString(i18n.language)} accent="text-gray-300" />
            <StatCard label={t('db_last_week')} value={dbStats.last_week.toLocaleString(i18n.language)} accent="text-gray-300" />
            <StatCard label={t('db_last_month')} value={dbStats.last_month.toLocaleString(i18n.language)} accent="text-gray-300" />
            <StatCard label={t('db_daily')} value={dbStats.daily_rows.toLocaleString(i18n.language)} accent="text-gray-300" />
          </div>
          <StatCard label={t('db_growth')} value={formatBytes(dbStats.est_monthly_growth_bytes)} accent="text-emerald-300" />
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">{t('db_tables')}</p>
            <ul className="space-y-1">
              {dbStats.tables.map((tbl) => (
                <li key={tbl.name} className="flex items-center justify-between text-xs font-mono">
                  <span className="text-gray-400">{tbl.name}</span>
                  <span className="text-gray-200">{tbl.rows.toLocaleString(i18n.language)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}
