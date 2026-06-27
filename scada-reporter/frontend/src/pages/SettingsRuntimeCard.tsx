import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import axios from 'axios'
import {
  type RuntimeStatus,
  getRuntimeStatus,
  startCollector,
  startScheduler,
  stopCollector,
  stopScheduler,
} from '../api/client'

type RuntimeTarget = 'collector' | 'scheduler'

const REFRESH_MS = 10_000
const cardCls = 'bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-5 space-y-4'
const btnBase = 'min-h-9 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50'

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

function responseDetail(data: unknown) {
  if (!data) return null
  if (typeof data === 'string') return data
  if (typeof data === 'object') {
    const record = data as Record<string, unknown>
    const detail = record.detail ?? record.message ?? record.error
    if (typeof detail === 'string') return detail
    if (detail) return JSON.stringify(detail)
  }
  return null
}

function errorMessage(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error) || !error.response) return fallback
  const status = error.response.status
  const detail = responseDetail(error.response.data)
  if (status && detail) return `${fallback} (${status}: ${detail})`
  if (status) return `${fallback} (${status})`
  if (detail) return `${fallback} (${detail})`
  return fallback
}

export default function SettingsRuntimeCard() {
  const { t, i18n } = useTranslation('settings')
  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<RuntimeTarget | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  async function refresh() {
    const res = await getRuntimeStatus()
    setStatus(res.data)
    setLastUpdated(new Date())
    setError(null)
  }

  useEffect(() => {
    let active = true
    async function load(initial = false) {
      if (initial) setLoading(true)
      try {
        const res = await getRuntimeStatus()
        if (!active) return
        setStatus(res.data)
        setLastUpdated(new Date())
        setError(null)
      } catch (err) {
        if (active) setError(errorMessage(err, t('runtime_load_failed')))
      } finally {
        if (active && initial) setLoading(false)
      }
    }

    void load(true)
    const timer = window.setInterval(() => {
      void load()
    }, REFRESH_MS)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [t])

  async function toggleCollector() {
    if (!status) return
    if (status.collector.running && !window.confirm(t('runtime_confirm_stop_collector'))) return
    setBusy('collector')
    setError(null)
    setMessage(null)
    try {
      const wasRunning = status.collector.running
      const res = status.collector.running ? await stopCollector() : await startCollector()
      setStatus(res.data)
      setLastUpdated(new Date())
      setMessage(t(wasRunning ? 'runtime_collector_stopped' : 'runtime_collector_started'))
      try {
        await refresh()
      } catch (err) {
        setError(errorMessage(err, t('runtime_load_failed')))
      }
    } catch (err) {
      setError(errorMessage(err, t('runtime_action_failed')))
    } finally {
      setBusy(null)
    }
  }

  async function toggleScheduler() {
    if (!status) return
    if (status.scheduler.running && !window.confirm(t('runtime_confirm_stop_scheduler'))) return
    setBusy('scheduler')
    setError(null)
    setMessage(null)
    try {
      const wasRunning = status.scheduler.running
      const res = status.scheduler.running ? await stopScheduler() : await startScheduler()
      setStatus(res.data)
      setLastUpdated(new Date())
      setMessage(t(wasRunning ? 'runtime_scheduler_stopped' : 'runtime_scheduler_started'))
      try {
        await refresh()
      } catch (err) {
        setError(errorMessage(err, t('runtime_load_failed')))
      }
    } catch (err) {
      setError(errorMessage(err, t('runtime_action_failed')))
    } finally {
      setBusy(null)
    }
  }

  const startedAt = status?.backend.started_at
    ? new Date(status.backend.started_at).toLocaleString(i18n.language)
    : '-'
  const lastUpdatedAt = lastUpdated ? lastUpdated.toLocaleTimeString(i18n.language) : null

  return (
    <div className={cardCls}>
      <div>
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{t('runtime_title')}</h2>
        <p className="text-xs text-gray-500 mt-1">{t('runtime_hint')}</p>
      </div>

      {loading && <p className="text-sm text-gray-500">{t('runtime_loading')}</p>}

      {status && (
        <div className="space-y-4">
          <div className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <p className="text-xs text-gray-500">{t('runtime_backend')}</p>
              <p className="text-white font-medium">{status.backend.status}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">{t('runtime_uptime')}</p>
              <p className="text-white font-medium">{fmtUptime(status.backend.uptime_seconds)}</p>
            </div>
            <div className="sm:col-span-2">
              <p className="text-xs text-gray-500">{t('runtime_started_at')}</p>
              <p className="text-gray-300 text-xs">{startedAt}</p>
            </div>
          </div>

          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
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

            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
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

      {(message || lastUpdatedAt) && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          {message && <p className="text-emerald-300">{message}</p>}
          {lastUpdatedAt && <p className="text-gray-500">{t('runtime_last_updated', { time: lastUpdatedAt })}</p>}
        </div>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
