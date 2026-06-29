// src/pages/Plc.tsx — merged PLC management + health, one page with two tabs.
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { getIncidentSummary } from '../api/client'
import PlcConfig from './PlcConfig'
import PlcHealth from './PlcHealth'

export default function Plc() {
  const { t } = useTranslation('plc')
  const { pathname } = useLocation()
  const navigate = useNavigate()
  // /plc-health (e.g. the alert-badge deep link) opens the health tab; /plc the config tab.
  const tab: 'config' | 'health' = pathname.includes('plc-health') ? 'health' : 'config'

  const { data: summary } = useQuery({
    queryKey: ['plc-incident-summary'],
    queryFn: () => getIncidentSummary().then((r) => r.data),
    refetchInterval: 10000,
  })
  const open = summary?.open_total ?? 0
  const critical = (summary?.critical ?? 0) > 0

  const tabCls = (active: boolean) =>
    `flex items-center px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
      active ? 'border-cyan-500 text-cyan-400' : 'border-transparent text-gray-400 hover:text-gray-200'
    }`

  return (
    <div className="p-6">
      <div className="flex items-center gap-1 border-b border-edge mb-6">
        <button className={tabCls(tab === 'config')} onClick={() => navigate('/plc')}>
          {t('tab_config')}
        </button>
        <button className={tabCls(tab === 'health')} onClick={() => navigate('/plc-health')}>
          {t('tab_health')}
          {open > 0 && (
            <span
              className={`ms-2 inline-flex items-center justify-center min-w-5 px-1.5 py-0.5 rounded-full text-xs font-semibold ${
                critical ? 'bg-red-900/50 text-red-300' : 'bg-yellow-900/50 text-yellow-300'
              }`}
            >
              {open}
            </span>
          )}
        </button>
      </div>
      {tab === 'config' ? <PlcConfig /> : <PlcHealth />}
    </div>
  )
}
