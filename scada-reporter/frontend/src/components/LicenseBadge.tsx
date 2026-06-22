import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getLicenseStatus, type LicenseMode } from '../api/client'

const STYLE: Record<LicenseMode, string> = {
  licensed: 'bg-green-900/40 text-green-300 border-green-700/50',
  demo: 'bg-yellow-900/40 text-yellow-300 border-yellow-700/50',
  unlicensed: 'bg-gray-800 text-gray-400 border-gray-700',
}

const DOT: Record<LicenseMode, string> = {
  licensed: 'bg-green-400',
  demo: 'bg-yellow-400',
  unlicensed: 'bg-gray-500',
}

export default function LicenseBadge() {
  const { t } = useTranslation('settings')
  const { data } = useQuery({
    queryKey: ['license'],
    queryFn: () => getLicenseStatus().then((r) => r.data),
    staleTime: 60_000,
  })

  if (!data) return null
  const mode = data.mode
  const label =
    mode === 'licensed' ? t('mode_licensed') : mode === 'demo' ? t('mode_demo') : t('mode_unlicensed')

  return (
    <div
      className={`flex items-center gap-2 px-2.5 py-1.5 mb-1 rounded-lg border text-xs ${STYLE[mode]}`}
      title={data.customer ?? undefined}
    >
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${DOT[mode]}`} />
      <span className="font-medium">{label}</span>
      {data.customer && <span className="truncate opacity-80">· {data.customer}</span>}
    </div>
  )
}
