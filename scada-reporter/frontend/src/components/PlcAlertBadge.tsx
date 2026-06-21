// src/components/PlcAlertBadge.tsx
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getIncidentSummary } from '../api/client'

export default function PlcAlertBadge() {
  const { t } = useTranslation('plcHealth')
  const { data } = useQuery({
    queryKey: ['plc-incident-summary'],
    queryFn: () => getIncidentSummary().then((r) => r.data),
    refetchInterval: 10000,
  })
  const open = data?.open_total ?? 0
  if (open === 0) return null
  const critical = data?.critical ?? 0
  return (
    <Link
      to="/plc-health"
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium ${critical > 0 ? 'bg-red-900/40 text-red-300' : 'bg-yellow-900/40 text-yellow-300'}`}
      title={t('open_problems', { count: open })}
    >
      <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
      {t('alerts', { count: open })}
    </Link>
  )
}
