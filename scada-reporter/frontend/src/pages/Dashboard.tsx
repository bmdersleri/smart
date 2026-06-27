import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-3 text-xl font-bold text-white">
          <span className="w-9 h-9 flex items-center justify-center">
            <SmartReportIcon className="w-8 h-8" />
          </span>
          {t('title')}
        </h1>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-gray-800">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-cyan-500 text-cyan-400'
                : 'border-transparent text-gray-500 hover:text-gray-300'
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
