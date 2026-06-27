import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  generateGrafanaDashboard,
  getTags,
  listGrafanaTemplates,
  type GrafanaDashboardGenerated,
  type GrafanaTemplate,
  type Tag,
} from '../api/client'
import { useSettings } from '../context/SettingsContext'
import SmartReportIcon from '../components/SmartReportIcon'

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

function buildGrafanaPath(path: string, theme: 'dark' | 'light') {
  const url = new URL(path, GRAFANA_URL)
  url.searchParams.set('orgId', '1')
  url.searchParams.set('theme', theme)
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
  const [templates, setTemplates] = useState<GrafanaTemplate[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [templateKey, setTemplateKey] = useState<GrafanaTemplate['key']>('facility_overview')
  const [title, setTitle] = useState(t('template_facility_default_title'))
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([])
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)
  const [generated, setGenerated] = useState<GrafanaDashboardGenerated | null>(null)

  const loadDashboards = useCallback((signal?: AbortSignal) => {
    fetch('/grafana-api/api/search?type=dash-db')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<Array<{ uid: string; title: string; url: string }>>
      })
      .then((rows) => {
        if (signal?.aborted) return
        const list = rows
          .filter((d) => d.uid && d.url)
          .map((d) => ({ uid: d.uid, title: d.title, url: d.url }))
        setDashboards(list)
        setActiveUid((prev) => prev || list[0]?.uid || '')
        setLoading(false)
      })
      .catch((e: unknown) => {
        if (signal?.aborted) return
        setError(e instanceof Error ? e.message : String(e))
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadDashboards(controller.signal)
    return () => {
      controller.abort()
    }
  }, [loadDashboards])

  useEffect(() => {
    let cancelled = false
    Promise.all([listGrafanaTemplates(), getTags()])
      .then(([templateResponse, tagResponse]) => {
        if (cancelled) return
        setTemplates(templateResponse.data.templates)
        setTags(tagResponse.data)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setGenerateError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [])

  const active = useMemo(
    () => dashboards.find((d) => d.uid === activeUid),
    [dashboards, activeUid],
  )
  const selectedTemplate = useMemo(
    () => templates.find((template) => template.key === templateKey),
    [templates, templateKey],
  )
  const canGenerate = title.trim().length > 0 && (!selectedTemplate?.requires_tags || selectedTagIds.length > 0)

  const handleGenerate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canGenerate) return
    setGenerating(true)
    setGenerateError(null)
    setGenerated(null)
    try {
      const response = await generateGrafanaDashboard({
        template: templateKey,
        title: title.trim(),
        tag_ids: selectedTagIds,
      })
      setGenerated(response.data)
      setActiveUid(response.data.uid)
      loadDashboards()
    } catch (e) {
      setGenerateError(e instanceof Error ? e.message : String(e))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="p-6 space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-3">
          <span className="w-9 h-9 flex items-center justify-center flex-shrink-0">
            <SmartReportIcon className="w-8 h-8" />
          </span>
          <div>
            <h1 className="text-xl font-semibold text-white">{t('title')}</h1>
            <p className="text-sm text-gray-500">{t('subtitle')}</p>
          </div>
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

      <form
        onSubmit={handleGenerate}
        className="grid gap-3 rounded-lg border border-gray-800 bg-gray-950/40 p-4 md:grid-cols-[1fr_1fr_auto]"
      >
        <div className="space-y-2">
          <label
            htmlFor="grafana-template"
            className="block text-xs font-medium uppercase tracking-wide text-gray-500"
          >
            {t('template_label')}
          </label>
          <select
            id="grafana-template"
            value={templateKey}
            onChange={(event) => {
              const next = event.target.value as GrafanaTemplate['key']
              setTemplateKey(next)
              setTitle(
                next === 'water_quality'
                  ? t('template_water_default_title')
                  : t('template_facility_default_title'),
              )
              setSelectedTagIds([])
            }}
            className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100"
          >
            {templates.map((template) => (
              <option key={template.key} value={template.key}>
                {template.name}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500">{selectedTemplate?.description ?? t('template_loading')}</p>
        </div>

        <div className="space-y-2">
          <label
            htmlFor="grafana-title"
            className="block text-xs font-medium uppercase tracking-wide text-gray-500"
          >
            {t('dashboard_title_label')}
          </label>
          <input
            id="grafana-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100"
          />
          {selectedTemplate?.requires_tags && (
            <select
              aria-label={t('template_label')}
              multiple
              value={selectedTagIds.map(String)}
              onChange={(event) => {
                const ids = Array.from(event.target.selectedOptions, (option) => Number(option.value))
                setSelectedTagIds(ids)
              }}
              className="h-24 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100"
            >
              {tags.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name} {tag.unit ? `(${tag.unit})` : ''}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="flex flex-col justify-end gap-2">
          <button
            type="submit"
            disabled={!canGenerate || generating}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-700"
          >
            {generating ? t('generating') : t('generate_dashboard')}
          </button>
          {generated && (
            <a
              href={buildGrafanaPath(generated.url, theme)}
              target="_blank"
              rel="noreferrer"
              className="text-center text-xs text-cyan-400 hover:underline"
            >
              {t('open_generated')}
            </a>
          )}
        </div>
        {generateError && <p className="text-sm text-red-400 md:col-span-3">{generateError}</p>}
      </form>

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
