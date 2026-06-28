import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLiveDashboard } from '../hooks/useLiveDashboard'
import AllTagsTab from './dashboard/AllTagsTab'
import OverviewTab from './dashboard/OverviewTab'
import WatchlistTab from './dashboard/WatchlistTab'
import SmartReportIcon from '../components/SmartReportIcon'

type Tab = 'overview' | 'watchlist' | 'tags'

const TABS: { id: Tab; labelKey: string }[] = [
  { id: 'overview', labelKey: 'tab_overview' },
  { id: 'watchlist', labelKey: 'tab_watchlist' },
  { id: 'tags', labelKey: 'tab_tags' },
]

export default function Dashboard() {
  const { t } = useTranslation('dashboard')
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  // Enable live websocket streaming globally for the dashboard
  const { status: wsStatus } = useLiveDashboard()

  return (
    <div className="p-6 md:p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-4 text-2xl font-bold text-white tracking-tight">
          <span className="w-12 h-12 flex items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/10 border border-cyan-500/20 shadow-lg shadow-cyan-500/10">
            <SmartReportIcon className="w-7 h-7 text-cyan-400" />
          </span>
          {t('title')}
        </h1>

        <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
          wsStatus === 'connected' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
          wsStatus === 'connecting' ? 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400' :
          'bg-red-500/10 border-red-500/20 text-red-400'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${
            wsStatus === 'connected' ? 'bg-emerald-400 animate-pulse' :
            wsStatus === 'connecting' ? 'bg-yellow-400' : 'bg-red-400'
          }`} />
          {wsStatus === 'connected' ? 'Live' : wsStatus === 'connecting' ? 'Connecting...' : 'Disconnected'}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-2 p-1 bg-surface-raised/50 backdrop-blur-sm border border-white/5 rounded-xl w-fit">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-5 py-2 text-sm font-medium rounded-lg transition-all duration-200 ${
              activeTab === tab.id
                ? 'bg-cyan-500/15 text-cyan-300 shadow-xs border border-cyan-500/30'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'overview' && <OverviewTab active={activeTab === 'overview'} />}
      {activeTab === 'watchlist' && <WatchlistTab active={activeTab === 'watchlist'} />}
      {activeTab === 'tags' && <AllTagsTab active={activeTab === 'tags'} />}
    </div>
  )
}
