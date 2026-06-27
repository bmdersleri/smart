import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  type RuntimeStatus,
  getRuntimeStatus,
  startCollector,
  startScheduler,
  stopCollector,
  stopScheduler,
} from '../api/client'

type RuntimeTarget = 'collector' | 'scheduler'

const cardCls = 'bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4 mb-4'
const btnBase = 'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50'

function fmtUptime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return '-'
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function statusDot(running: boolean) {
  return running ? 'bg-emerald-400' : 'bg-gray-600'
}

export default function SettingsRuntimeCard() {
  const { t, i18n } = useTranslation('settings')
  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<RuntimeTarget | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    const res = await getRuntimeStatus()
    setStatus(res.data)
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    getRuntimeStatus()
      .then((res) => {
        if (active) setStatus(res.data)
      })
      .catch(() => {
        if (active) setError(t('runtime_load_failed'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [t])

  async function toggleCollector() {
    if (!status) return
    setBusy('collector')
    setError(null)
    try {
      const res = status.collector.running ? await stopCollector() : await startCollector()
      setStatus(res.data)
      await refresh()
    } catch {
      setError(t('runtime_action_failed'))
    } finally {
      setBusy(null)
    }
  }

  async function toggleScheduler() {
    if (!status) return
    setBusy('scheduler')
    setError(null)
    try {
      const res = status.scheduler.running ? await stopScheduler() : await startScheduler()
      setStatus(res.data)
      await refresh()
    } catch {
      setError(t('runtime_action_failed'))
    } finally {
      setBusy(null)
    }
  }

  const startedAt = status?.backend.started_at
    ? new Date(status.backend.started_at).toLocaleString(i18n.language)
    : '-'

  return (
    <div className={cardCls}>
      <div>
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{t('runtime_title')}</h2>
        <p className="text-xs text-gray-500 mt-1">{t('runtime_hint')}</p>
      </div>

      {loading && <p className="text-sm text-gray-500">{t('runtime_loading')}</p>}

      {status && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-xs text-gray-500">{t('runtime_backend')}</p>
              <p className="text-white font-medium">{status.backend.status}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">{t('runtime_uptime')}</p>
              <p className="text-white font-medium">{fmtUptime(status.backend.uptime_seconds)}</p>
            </div>
            <div className="col-span-2">
              <p className="text-xs text-gray-500">{t('runtime_started_at')}</p>
              <p className="text-gray-300 text-xs">{startedAt}</p>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`h-2.5 w-2.5 rounded-full ${statusDot(status.collector.running)}`} />
                  <span className="text-sm text-white">{t('runtime_collector')}</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {t(status.collector.running ? 'runtime_running' : 'runtime_stopped')}
                </p>
              </div>
              <button
                type="button"
                onClick={toggleCollector}
                disabled={busy !== null || !status.controls_enabled}
                className={`${btnBase} ${
                  status.collector.running
                    ? 'bg-red-900/40 text-red-300 hover:bg-red-900/70'
                    : 'bg-emerald-900/40 text-emerald-300 hover:bg-emerald-900/70'
                }`}
              >
                {status.collector.running ? t('runtime_stop') : t('runtime_start')}
              </button>
            </div>

            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`h-2.5 w-2.5 rounded-full ${statusDot(status.scheduler.running)}`} />
                  <span className="text-sm text-white">{t('runtime_scheduler')}</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {t(status.scheduler.running ? 'runtime_running' : 'runtime_stopped')}
                </p>
              </div>
              <button
                type="button"
                onClick={toggleScheduler}
                disabled={busy !== null || !status.controls_enabled}
                className={`${btnBase} ${
                  status.scheduler.running
                    ? 'bg-red-900/40 text-red-300 hover:bg-red-900/70'
                    : 'bg-emerald-900/40 text-emerald-300 hover:bg-emerald-900/70'
                }`}
              >
                {status.scheduler.running ? t('runtime_stop') : t('runtime_start')}
              </button>
            </div>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
