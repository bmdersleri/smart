import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listBackups,
  createBackup,
  deleteBackup,
  restoreBackup,
  downloadBackup,
  type BackupItem,
} from '../api/client'

const cardCls = 'bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-5 space-y-4'
const btnBase = 'min-h-9 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50'

function fmtSize(n: number | null): string {
  if (!n) return '—'
  const mb = n / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(n / 1024).toFixed(0)} KB`
}

export default function SettingsBackupCard() {
  const { t } = useTranslation('settings')
  const [items, setItems] = useState<BackupItem[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function onCreate() {
    setBusy(true)
    setError(null)
    try {
      await createBackup()
      await refresh()
    } catch {
      setError(t('backup_create_failed'))
    } finally {
      setBusy(false)
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
      await restoreBackup(id)
      await refresh()
    } catch {
      setError(t('backup_restore_failed'))
    } finally {
      setBusy(false)
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

      {items.length === 0 && (
        <p className="text-xs text-gray-500">{t('backup_none')}</p>
      )}

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
                  {new Date(b.created_at).toLocaleString()} · {fmtSize(b.size_bytes)} · {b.status}
                </p>
              </div>
              <div className="flex gap-2 shrink-0 ml-3">
                <button
                  type="button"
                  onClick={() => void onDownload(b.id, b.filename)}
                  disabled={busy}
                  className="text-xs text-blue-400 hover:underline disabled:opacity-50"
                >
                  {t('backup_download')}
                </button>
                <button
                  type="button"
                  onClick={() => void onRestore(b.id)}
                  disabled={busy}
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
