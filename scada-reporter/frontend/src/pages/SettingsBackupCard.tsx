import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listBackups,
  createBackup,
  deleteBackup,
  restoreBackup,
  downloadBackup,
  getStreamToken,
  backupProgressUrl,
  restoreProgressUrl,
  type BackupItem,
} from '../api/client'
import { parseUtc } from '../utils/time'

const cardCls = 'bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-5 space-y-4'
const btnBase = 'min-h-9 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50'

function fmtSize(n: number | null): string {
  if (!n) return '—'
  const mb = n / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(n / 1024).toFixed(0)} KB`
}

interface Live {
  id: number
  kind: 'backup' | 'restore'
  phase: string
  percent: number
  status: string
}

export default function SettingsBackupCard() {
  const { t } = useTranslation('settings')
  const [items, setItems] = useState<BackupItem[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState<Live | null>(null)
  const esRef = useRef<EventSource | null>(null)

  async function refresh() {
    try {
      const res = await listBackups()
      setItems(res.data)
    } catch {
      setError(t('backup_load_failed'))
    }
  }

  useEffect(() => {
    void refresh()
    return () => esRef.current?.close()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Subscribe to a backup/restore job's SSE progress stream. EventSource can't
  // send auth headers, so we fetch a short-lived stream token first.
  async function watch(id: number, kind: 'backup' | 'restore') {
    let streamToken: string
    try {
      streamToken = (await getStreamToken()).data.stream_token
    } catch {
      setBusy(false)
      setError(t(kind === 'backup' ? 'backup_create_failed' : 'backup_restore_failed'))
      return
    }
    esRef.current?.close()
    const url =
      kind === 'backup' ? backupProgressUrl(id, streamToken) : restoreProgressUrl(id, streamToken)
    const es = new EventSource(url)
    esRef.current = es

    es.onmessage = (e) => {
      let p: { phase: string; percent: number; status: string; error?: string | null }
      try {
        p = JSON.parse(e.data)
      } catch {
        return
      }
      setLive({ id, kind, phase: p.phase, percent: p.percent, status: p.status })
      if (p.status === 'done' || p.status === 'failed') {
        es.close()
        esRef.current = null
        setBusy(false)
        setLive(null)
        if (p.status === 'failed') {
          setError(p.error || t(kind === 'backup' ? 'backup_create_failed' : 'backup_restore_failed'))
        } else if (kind === 'restore') {
          setError(t('backup_restore_done_note'))
        }
        void refresh()
      }
    }
    es.onerror = () => {
      es.close()
      esRef.current = null
      setBusy(false)
      setLive(null)
      setError(t(kind === 'backup' ? 'backup_create_failed' : 'backup_restore_failed'))
    }
  }

  async function onCreate() {
    setBusy(true)
    setError(null)
    try {
      const res = await createBackup()
      await watch(res.data.id, 'backup')
    } catch {
      setBusy(false)
      setError(t('backup_create_failed'))
    }
  }

  async function onDownload(id: number, filename: string) {
    setBusy(true)
    try {
      const res = await downloadBackup(id)
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError(t('backup_load_failed'))
    } finally {
      setBusy(false)
    }
  }

  async function onRestore(id: number) {
    if (!window.confirm(t('backup_confirm_restore'))) return
    setBusy(true)
    setError(null)
    try {
      const res = await restoreBackup(id)
      await watch(res.data.restoring, 'restore')
    } catch {
      setBusy(false)
      setError(t('backup_restore_failed'))
    }
  }

  async function onDelete(id: number) {
    if (!window.confirm(t('backup_confirm_delete'))) return
    setBusy(true)
    try {
      await deleteBackup(id)
      await refresh()
    } catch {
      setError(t('backup_delete_failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={cardCls}>
      <div>
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{t('backup_title')}</h2>
        <p className="text-xs text-gray-500 mt-1">{t('backup_hint')}</p>
      </div>

      <button
        type="button"
        onClick={onCreate}
        disabled={busy}
        className={`${btnBase} bg-blue-600 hover:bg-blue-500 text-white`}
      >
        {t('backup_create')}
      </button>

      {live && (
        <div
          className="space-y-1"
          role="progressbar"
          aria-valuenow={live.percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div className="flex justify-between text-xs text-gray-400">
            <span>
              {live.kind === 'restore' ? t('backup_restoring') : t('backup_creating')} ·{' '}
              {t(`backup_phase_${live.phase}`, live.phase)}
            </span>
            <span>{live.percent.toFixed(0)}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-gray-800 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${live.kind === 'restore' ? 'bg-amber-500' : 'bg-blue-500'}`}
              style={{ width: `${live.percent}%` }}
            />
          </div>
        </div>
      )}

      {items.length === 0 && !live && <p className="text-xs text-gray-500">{t('backup_none')}</p>}

      {items.length > 0 && (
        <ul className="space-y-2">
          {items.map((b) => (
            <li
              key={b.id}
              className="flex items-center justify-between text-sm border-b border-gray-800 pb-2"
            >
              <div className="min-w-0">
                <p className="truncate text-gray-200">{b.filename}</p>
                <p className="text-xs text-gray-500">
                  {parseUtc(b.created_at).toLocaleString()} · {fmtSize(b.size_bytes)} · {b.status}
                </p>
              </div>
              <div className="flex gap-2 shrink-0 ml-3">
                <button
                  type="button"
                  onClick={() => void onDownload(b.id, b.filename)}
                  disabled={busy || b.status !== 'verified'}
                  className="text-xs text-blue-400 hover:underline disabled:opacity-50"
                >
                  {t('backup_download')}
                </button>
                <button
                  type="button"
                  onClick={() => void onRestore(b.id)}
                  disabled={busy || b.status !== 'verified'}
                  className="text-xs text-amber-400 hover:underline disabled:opacity-50"
                >
                  {t('backup_restore')}
                </button>
                <button
                  type="button"
                  onClick={() => void onDelete(b.id)}
                  disabled={busy}
                  className="text-xs text-red-400 hover:underline disabled:opacity-50"
                >
                  {t('backup_delete')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
