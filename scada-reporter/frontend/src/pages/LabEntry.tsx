import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import SingleSampleTab from './lab/SingleSampleTab'
import BatchTab from './lab/BatchTab'
import ImportTab from './lab/ImportTab'
import RecordsTab from './lab/RecordsTab'
import LabCatalogCard from './lab/LabCatalogCard'

type TabKey = 'single' | 'batch' | 'import' | 'records' | 'catalog'

export default function LabEntry() {
  const { t } = useTranslation('lab')
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [tab, setTab] = useState<TabKey>('single')
  const tabs: { key: TabKey; label: string }[] = [
    { key: 'single', label: t('tab_single') },
    { key: 'batch', label: t('tab_batch') },
    { key: 'import', label: t('tab_import') },
    { key: 'records', label: t('tab_records') },
    ...(isAdmin ? [{ key: 'catalog' as const, label: t('tab_catalog') }] : []),
  ]
  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">{t('title')}</h1>
        <p className="text-sm text-gray-500">{t('subtitle')}</p>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-edge pb-3">
        {tabs.map((tb) => (
          <button
            key={tb.key}
            onClick={() => setTab(tb.key)}
            className={`rounded-lg px-4 py-2 text-sm transition-colors ${tab === tb.key ? 'bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/30' : 'bg-surface-raised/40 backdrop-blur-xl text-gray-400 hover:bg-white/5'}`}
          >
            {tb.label}
          </button>
        ))}
      </div>
      {tab === 'single' && <SingleSampleTab />}
      {tab === 'batch' && <BatchTab />}
      {tab === 'import' && <ImportTab />}
      {tab === 'records' && <RecordsTab />}
      {tab === 'catalog' && isAdmin && <LabCatalogCard />}
    </div>
  )
}
