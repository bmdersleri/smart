import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getAppSettings, updateTimezone } from '../api/client'

const TIMEZONES = [
  'Europe/Istanbul',
  'UTC',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Moscow',
  'Asia/Dubai',
]

export default function SettingsTimezoneCard() {
  const { t } = useTranslation('lab')
  const queryClient = useQueryClient()
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['app-settings'],
    queryFn: () => getAppSettings(),
    staleTime: 5 * 60 * 1000,
  })

  const current = data?.data?.timezone ?? 'Europe/Istanbul'

  const handleChange = async (tz: string) => {
    setSaved(false)
    setError(null)
    try {
      await updateTimezone(tz)
      await queryClient.invalidateQueries({ queryKey: ['app-settings'] })
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-5 space-y-3">
      <div>
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">
          {t('tz_title')}
        </h2>
        <p className="text-xs text-gray-500 mt-0.5">{t('tz_subtitle')}</p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <select
          value={current}
          onChange={(e) => handleChange(e.target.value)}
          className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 sm:w-auto"
        >
          {TIMEZONES.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
        {saved && <span className="text-sm text-green-400">{t('tz_saved')}</span>}
        {error && <span className="text-sm text-red-400">{error}</span>}
      </div>
    </div>
  )
}
