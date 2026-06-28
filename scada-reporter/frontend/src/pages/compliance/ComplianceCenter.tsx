import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ComplianceTab } from './constants'
import OverviewTab from './OverviewTab'
import PermitsTab from './PermitsTab'
import EventsTab from './EventsTab'
import ReportPacksTab from './ReportPacksTab'

export default function ComplianceCenter() {
  const { t } = useTranslation(['compliance', 'common'])
  const [tab, setTab] = useState<ComplianceTab>('overview')

  const tabs: { key: ComplianceTab; label: string }[] = [
    { key: 'overview', label: t('tab_overview') },
    { key: 'permits', label: t('tab_permits') },
    { key: 'events', label: t('tab_events') },
    { key: 'reportpacks', label: t('tab_report_packs') },
  ]

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-white">{t('title')}</h1>
        <p className="text-sm text-gray-500">{t('subtitle')}</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-edge">
        {tabs.map((tabItem) => (
          <button
            key={tabItem.key}
            onClick={() => setTab(tabItem.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === tabItem.key
                ? 'border-cyan-400 text-cyan-400'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            {tabItem.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <OverviewTab onOpenEvents={() => setTab('events')} />}
      {/* PermitsTab hides every write control when role !== 'admin'. */}
      {tab === 'permits' && <PermitsTab />}
      {tab === 'events' && <EventsTab />}
      {/* ReportPacksTab hides approve for non-admin and write controls for viewers. */}
      {tab === 'reportpacks' && <ReportPacksTab />}
    </div>
  )
}
