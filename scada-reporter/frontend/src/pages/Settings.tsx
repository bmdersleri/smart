import { useTranslation } from 'react-i18next'
import { useSettings } from '../context/SettingsContext'
import { useAuth } from '../context/AuthContext'
import LanguageSelector from '../components/LanguageSelector'
import LicenseCard from '../components/LicenseCard'
import LabCatalogCard from './lab/LabCatalogCard'
import SettingsTimezoneCard from './SettingsTimezoneCard'
import SettingsRuntimeCard from './SettingsRuntimeCard'
import SettingsBackupCard from './SettingsBackupCard'

const MIN_H = 300
const MAX_H = 2000
const STEP = 50

export default function Settings() {
  const { t } = useTranslation(['settings', 'common'])
  const { trendChartHeight, theme, set, reset } = useSettings()
  const { user } = useAuth()

  return (
    <div className="w-full max-w-6xl space-y-5 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-xl font-semibold text-white">{t('title')}</h1>
        <p className="mt-1 text-sm text-gray-500">{t('theme_hint')}</p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,0.75fr)]">
        <div className="space-y-5">
          <div className="bg-gray-900/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 sm:p-5 space-y-5">
            <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{t('appearance')}</h2>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
              <div className="min-w-0">
                <label className="text-sm text-white block">{t('theme')}</label>
                <p className="text-xs text-gray-500 mt-0.5">{t('theme_hint')}</p>
              </div>
              <div className="grid grid-cols-2 rounded-lg border border-gray-700 bg-gray-800 p-0.5 sm:flex">
                {([['dark', t('theme_dark')], ['light', t('theme_light')]] as const).map(([val, label]) => (
                  <button
                    key={val}
                    onClick={() => set('theme', val)}
                    className={`min-h-9 rounded-md px-3 py-1.5 text-sm transition-colors ${
                      theme === val ? 'bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/30' : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
              <div className="min-w-0">
                <label className="text-sm text-white block">{t('language')}</label>
                <p className="text-xs text-gray-500 mt-0.5">{t('language_hint')}</p>
              </div>
              <LanguageSelector />
            </div>
          </div>

          <LicenseCard />

          {user?.role === 'admin' && <SettingsRuntimeCard />}
          {user?.role === 'admin' && <SettingsBackupCard />}
          {user?.role === 'admin' && <LabCatalogCard />}
        </div>

        <div className="space-y-5">
          {user?.role === 'admin' && <SettingsTimezoneCard />}

          <div className="bg-gray-900/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 sm:p-5 space-y-6">
            <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{t('trend_chart')}</h2>

            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <label className="text-sm text-white">{t('chart_height')}</label>
                <div className="flex items-center gap-2 sm:justify-end">
                  <input
                    type="number"
                    min={MIN_H}
                    max={MAX_H}
                    step={STEP}
                    value={trendChartHeight}
                    onChange={e => {
                      const v = Number(e.target.value)
                      if (v >= MIN_H && v <= MAX_H) set('trendChartHeight', v)
                    }}
                    className="w-full min-w-0 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white text-end focus:outline-hidden focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 sm:w-24"
                  />
                  <span className="text-sm text-gray-400">px</span>
                </div>
              </div>

              <input
                type="range"
                min={MIN_H}
                max={MAX_H}
                step={STEP}
                value={trendChartHeight}
                onChange={e => set('trendChartHeight', Number(e.target.value))}
                className="w-full accent-blue-500"
              />

              <div className="grid grid-cols-3 items-center gap-2 text-xs text-gray-500">
                <span>{MIN_H}px</span>
                <span className="text-center text-gray-400">{t('selected')}: <span className="text-white font-medium">{trendChartHeight}px</span></span>
                <span className="text-end">{MAX_H}px</span>
              </div>
            </div>
          </div>

          <button
            onClick={reset}
            className="w-full rounded-lg border border-gray-800 px-4 py-2 text-sm text-gray-400 transition-colors hover:bg-white/5 hover:text-white sm:w-auto"
          >
            {t('common:reset')}
          </button>
        </div>
      </div>
    </div>
  )
}
