import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import SingleSampleTab from './lab/SingleSampleTab'

type TabKey = 'single' | 'batch' | 'import' | 'records'

export default function LabEntry() {
  const { t } = useTranslation('lab')
  const [tab, setTab] = useState<TabKey>('single')
  const tabs: { key: TabKey; label: string }[] = [
    { key: 'single', label: t('tab_single') },
    { key: 'batch', label: t('tab_batch') },
    { key: 'import', label: t('tab_import') },
    { key: 'records', label: t('tab_records') },
  ]
  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">{t('title')}</h1>
        <p className="text-sm text-gray-500">{t('subtitle')}</p>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-gray-800 pb-3">
        {tabs.map((tb) => (
          <button
            key={tb.key}
            onClick={() => setTab(tb.key)}
            className={`rounded-lg px-4 py-2 text-sm transition-colors ${tab === tb.key ? 'bg-blue-600 text-white' : 'bg-gray-900 text-gray-400 hover:bg-gray-800'}`}
          >
            {tb.label}
          </button>
        ))}
      </div>
      {tab === 'single' && <SingleSampleTab />}
      {tab !== 'single' && <p className="text-sm text-gray-500">…</p>}
    </div>
  )
}
