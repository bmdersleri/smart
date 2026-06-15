import { useState } from 'react'
import AllTagsTab from './dashboard/AllTagsTab'
import OverviewTab from './dashboard/OverviewTab'
import WatchlistTab from './dashboard/WatchlistTab'

type Tab = 'overview' | 'watchlist' | 'tags'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Özet' },
  { id: 'watchlist', label: 'İzleme Listesi' },
  { id: 'tags', label: 'Tüm Tag\'ler' },
]

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Dashboard</h1>
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
            {tab.label}
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
