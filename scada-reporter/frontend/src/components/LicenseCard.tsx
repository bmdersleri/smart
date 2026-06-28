import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { getLicenseStatus, revertLicense, uploadLicense } from '../api/client'

function modeLabel(mode: string, t: (k: string) => string) {
  return mode === 'licensed' ? t('mode_licensed') : mode === 'demo' ? t('mode_demo') : t('mode_unlicensed')
}

export default function LicenseCard() {
  const { t } = useTranslation('settings')
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const { data } = useQuery({
    queryKey: ['license'],
    queryFn: () => getLicenseStatus().then((r) => r.data),
  })

  const upload = useMutation({
    mutationFn: (file: File) => uploadLicense(file).then((r) => r.data),
    onSuccess: () => {
      setMsg({ ok: true, text: t('license_applied') })
      qc.invalidateQueries({ queryKey: ['license'] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setMsg({ ok: false, text: e.response?.data?.detail || t('license_apply_failed') }),
  })

  const remove = useMutation({
    mutationFn: () => revertLicense().then((r) => r.data),
    onSuccess: () => {
      setMsg(null)
      qc.invalidateQueries({ queryKey: ['license'] })
    },
  })

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) upload.mutate(file)
    e.target.value = ''
  }

  const expiry =
    data?.expires_at != null
      ? new Date(data.expires_at * 1000).toLocaleDateString()
      : t('license_perpetual')

  return (
    <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 sm:p-5 space-y-4">
      <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{t('license')}</h2>

      {data && (
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[7rem_minmax(0,1fr)]">
          <dt className="text-gray-500">{t('license_mode')}</dt>
          <dd className="min-w-0 break-words text-white">{modeLabel(data.mode, t)}</dd>
          {data.customer && (
            <>
              <dt className="text-gray-500">{t('license_customer')}</dt>
              <dd className="min-w-0 break-words text-white">{data.customer}</dd>
            </>
          )}
          {data.mode === 'licensed' && (
            <>
              <dt className="text-gray-500">{t('license_features')}</dt>
              <dd className="min-w-0 break-words text-white">
                {data.features.length ? data.features.join(', ') : t('mode_unlicensed')}
              </dd>
              <dt className="text-gray-500">{t('license_max_tags')}</dt>
              <dd className="min-w-0 break-words text-white">{data.max_tags ?? t('license_unlimited')}</dd>
              <dt className="text-gray-500">{t('license_expires')}</dt>
              <dd className="min-w-0 break-words text-white">{expiry}</dd>
            </>
          )}
        </dl>
      )}

      {data?.mode === 'demo' && (
        <p className="text-xs text-yellow-300 bg-yellow-900/30 border border-yellow-700/40 rounded-lg px-3 py-2">
          {t('demo_banner')}
        </p>
      )}

      {isAdmin && (
        <div className="pt-1 space-y-2">
          <p className="text-xs text-gray-500">{t('license_upload_hint')}</p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              ref={fileRef}
              type="file"
              accept=".jwt,.json,.txt"
              onChange={onPick}
              className="hidden"
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={upload.isPending}
              className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white transition-colors hover:bg-blue-500 disabled:opacity-50 sm:py-1.5"
            >
              {upload.isPending ? '…' : t('license_apply')}
            </button>
            {data?.mode === 'licensed' && (
              <button
                onClick={() => remove.mutate()}
                disabled={remove.isPending}
                className="rounded-lg px-3 py-2 text-sm text-gray-400 transition-colors hover:bg-white/5 hover:text-red-400 disabled:opacity-50 sm:py-1.5"
              >
                {t('license_remove')}
              </button>
            )}
          </div>
          {msg && (
            <p className={`text-xs ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>{msg.text}</p>
          )}
        </div>
      )}
    </div>
  )
}
