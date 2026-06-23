import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettings } from '../context/SettingsContext'

// iframe'ler dogrudan Grafana'ya gider (embedding acik). Dashboard LISTESI ise
// same-origin /grafana-api proxy'sinden gelir (CORS yok) — bkz. vite.config.ts.
const GRAFANA_URL = (import.meta.env.VITE_GRAFANA_URL as string | undefined) ?? 'http://localhost:3000'

interface GrafanaDashboard {
  uid: string
  title: string
  url: string // Grafana search API'sinin verdigi yol, orn. /d/<uid>/<slug>
}

function buildUrl(dash: GrafanaDashboard, kiosk: boolean, theme: 'dark' | 'light') {
  const url = new URL(dash.url, GRAFANA_URL)
  url.searchParams.set('orgId', '1')
  url.searchParams.set('theme', theme)
  url.searchParams.set('refresh', '30s')
  if (kiosk) url.searchParams.set('kiosk', '')
  return url.toString()
}

export default function Grafana() {
  const { t } = useTranslation('grafana')
  const { theme: appTheme } = useSettings()
  const theme = appTheme === 'light' ? 'light' : 'dark'
  const [dashboards, setDashboards] = useState<GrafanaDashboard[]>([])
  const [activeUid, setActiveUid] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/grafana-api/api/search?type=dash-db')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<Array<{ uid: string; title: string; url: string }>>
      })
      .then((rows) => {
        if (cancelled) return
        const list = rows
          .filter((d) => d.uid && d.url)
          .map((d) => ({ uid: d.uid, title: d.title, url: d.url }))
        setDashboards(list)
        setActiveUid((prev) => prev || list[0]?.uid || '')
        setLoading(false)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setError(e instanceof Error ? e.message : String(e))
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const active = useMemo(
    () => dashboards.find((d) => d.uid === activeUid),
    [dashboards, activeUid],
  )

  return (
    <div className="p-6 space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">{t('title')}</h1>
          <p className="text-sm text-gray-500">{t('subtitle')}</p>
        </div>
        {active && (
          <a
            href={buildUrl(active, false, theme)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-200 hover:bg-gray-800"
          >
            {t('open_grafana')}
          </a>
        )}
      </div>

      {loading && <p className="text-sm text-gray-400">{t('loading')}</p>}
      {error && (
        <p className="text-sm text-red-400">
          {t('load_error')}: {error}
        </p>
      )}
      {!loading && !error && dashboards.length === 0 && (
        <p className="text-sm text-gray-400">{t('empty')}</p>
      )}

      {dashboards.length > 0 && (
        <>
          <div className="flex flex-wrap gap-2 border-b border-gray-800 pb-3">
            {dashboards.map((dash) => (
              <button
                key={dash.uid}
                onClick={() => setActiveUid(dash.uid)}
                className={`rounded-lg px-4 py-2 text-sm transition-colors ${
                  activeUid === dash.uid
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-900 text-gray-400 hover:bg-gray-800 hover:text-white'
                }`}
              >
                {dash.title}
              </button>
            ))}
          </div>

          {active && (
            <iframe
              key={`${active.uid}-${theme}`}
              title={active.title}
              src={buildUrl(active, true, theme)}
              className="w-full rounded-lg border border-gray-800 bg-gray-950"
              style={{ height: 'calc(100vh - 220px)', minHeight: '600px' }}
            />
          )}
        </>
      )}
    </div>
  )
}
