import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  deleteGrafanaDashboard,
  generateGrafanaDashboard,
  generateLabDashboard,
  getTags,
  listGrafanaTemplates,
  listLabParameters,
  listLabSamplePoints,
  refreshManagedDashboards,
  type GrafanaDashboardGenerated,
  type GrafanaTemplate,
  type LabParameterOut,
  type LabSamplePointOut,
  type Tag,
} from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useSettings } from '../context/SettingsContext'
import SmartReportIcon from '../components/SmartReportIcon'
import { canGenerateLab } from './labDashboard.helper'
import { canDeleteDashboard } from './grafanaDelete.helper'

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
  const { user } = useAuth()
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
  const [labPoints, setLabPoints] = useState<LabSamplePointOut[]>([])
  const [labParams, setLabParams] = useState<LabParameterOut[]>([])
  const [labPointId, setLabPointId] = useState<number | ''>('')
  const [labParamIds, setLabParamIds] = useState<number[]>([])
  const [labGenerating, setLabGenerating] = useState(false)
  const [labResult, setLabResult] = useState<{ uid: string; title: string; url: string; status: string } | null>(null)
  const [labError, setLabError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshResult, setRefreshResult] = useState<string | null>(null)

  const loadDashboards = useCallback((signal?: AbortSignal) => {
    // credentials:'omit' KRİTİK: bayat bir grafana_session cookie'si proxy üzerinden
    // Grafana'ya giderse Grafana session-auth'a düşüp 401 verir (proxy'nin enjekte
    // ettiği Basic auth'u kullanmaz). Cookie'yi hiç göndermeyerek her zaman proxy
    // Basic auth (veya anonymous) ile kimlik doğrulanır — bayat cookie'den bağımsız.
    fetch('/grafana-api/api/search?type=dash-db', { cache: 'no-store', credentials: 'omit' })
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

  useEffect(() => {
    let cancelled = false
    Promise.all([listLabSamplePoints({ approved: true }), listLabParameters({ approved: true })])
      .then(([pointsRes, paramsRes]) => {
        if (cancelled) return
        setLabPoints(pointsRes.data)
        setLabParams(paramsRes.data)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setLabError(e instanceof Error ? e.message : String(e))
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

  const handleLabGenerate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canGenerateLab(labPointId, labParamIds)) return
    setLabGenerating(true)
    setLabError(null)
    setLabResult(null)
    try {
      const res = await generateLabDashboard({ sample_point_id: Number(labPointId), parameter_ids: labParamIds })
      setLabResult(res.data)
      loadDashboards()
    } catch (e) {
      setLabError(e instanceof Error ? e.message : String(e))
    } finally {
      setLabGenerating(false)
    }
  }

  const handleDelete = async (uid: string, dashTitle: string) => {
    if (!window.confirm(t('confirm_delete', { title: dashTitle }))) return
    setDeleteError(null)
    try {
      await deleteGrafanaDashboard(uid)
      setActiveUid((prev) => (prev === uid ? '' : prev))
      loadDashboards()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setDeleteError(detail ?? t('delete_error'))
    }
  }

  const handleRefreshManaged = async () => {
    setRefreshing(true)
    setRefreshResult(null)
    try {
      const r = await refreshManagedDashboards()
      setRefreshResult(t('refresh_result', { updated: r.data.updated, skipped: r.data.skipped.length }))
      loadDashboards()
    } catch (e) {
      setRefreshResult(e instanceof Error ? e.message : String(e))
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="p-6 space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-3">
          <span className="w-9 h-9 flex items-center justify-center shrink-0">
            <SmartReportIcon className="w-8 h-8" />
          </span>
          <div>
            <h1 className="text-xl font-semibold text-white">{t('title')}</h1>
            <p className="text-sm text-gray-500">{t('subtitle')}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {user?.role === 'admin' && (
            <button
              onClick={() => { void handleRefreshManaged() }}
              disabled={refreshing}
              className="px-3 py-1.5 text-sm rounded-lg bg-surface-sunken hover:bg-surface-sunken/80 border border-edge text-gray-300 disabled:opacity-50"
            >
              {refreshing ? t('refresh_managed_busy') : t('refresh_managed')}
            </button>
          )}
          {active && (
            <a
              href={buildUrl(active, false, theme)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center rounded-lg border border-edge-strong px-3 py-2 text-sm text-gray-200 hover:bg-white/5"
            >
              {t('open_grafana')}
            </a>
          )}
        </div>
        {refreshResult && (
          <p className="text-xs text-gray-400 mt-1">{refreshResult}</p>
        )}
      </div>

      <form
        onSubmit={handleGenerate}
        className="grid gap-3 rounded-lg border border-edge bg-surface/40 p-4 md:grid-cols-[1fr_1fr_auto]"
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
            className="w-full rounded-lg border border-edge-strong bg-surface-raised/40 backdrop-blur-xl px-3 py-2 text-sm text-gray-100"
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
            className="w-full rounded-lg border border-edge-strong bg-surface-raised/40 backdrop-blur-xl px-3 py-2 text-sm text-gray-100"
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
              className="h-24 w-full rounded-lg border border-edge-strong bg-surface-raised/40 backdrop-blur-xl px-3 py-2 text-sm text-gray-100"
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

      <div className="rounded-lg border border-edge bg-surface/40 p-4 space-y-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-200">{t('lab_gen_title')}</h2>
          <p className="text-xs text-gray-500">{t('lab_gen_subtitle')}</p>
        </div>
        <form onSubmit={handleLabGenerate} className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <div className="space-y-2">
            <label htmlFor="lab-point" className="block text-xs font-medium uppercase tracking-wide text-gray-500">
              {t('lab_gen_point')}
            </label>
            <select
              id="lab-point"
              value={labPointId === '' ? '' : String(labPointId)}
              onChange={(event) => setLabPointId(event.target.value === '' ? '' : Number(event.target.value))}
              className="w-full rounded-lg border border-edge-strong bg-surface-raised/40 backdrop-blur-xl px-3 py-2 text-sm text-gray-100"
            >
              <option value="">—</option>
              {labPoints.map((pt) => (
                <option key={pt.id} value={pt.id}>{pt.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <label htmlFor="lab-params" className="block text-xs font-medium uppercase tracking-wide text-gray-500">
              {t('lab_gen_params')}
            </label>
            <select
              id="lab-params"
              multiple
              value={labParamIds.map(String)}
              onChange={(event) => {
                const ids = Array.from(event.target.selectedOptions, (option) => Number(option.value))
                setLabParamIds(ids)
              }}
              className="h-24 w-full rounded-lg border border-edge-strong bg-surface-raised/40 backdrop-blur-xl px-3 py-2 text-sm text-gray-100"
            >
              {labParams.map((param) => (
                <option key={param.id} value={param.id}>{param.name}{param.unit ? ` (${param.unit})` : ''}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col justify-end gap-2">
            <button
              type="submit"
              disabled={!canGenerateLab(labPointId, labParamIds) || labGenerating}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-700"
            >
              {labGenerating ? t('lab_gen_generating') : t('lab_gen_button')}
            </button>
            {labResult && (
              <a
                href={buildGrafanaPath(labResult.url, theme)}
                target="_blank"
                rel="noreferrer"
                className="text-center text-xs text-cyan-400 hover:underline"
              >
                {t('lab_gen_open')}
              </a>
            )}
          </div>
          {labError && <p className="text-sm text-red-400 md:col-span-3">{labError}</p>}
        </form>
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
          <div className="flex flex-wrap gap-2 border-b border-edge pb-3">
            {dashboards.map((dash) => (
              <div key={dash.uid} className="flex items-center gap-1">
                <button
                  onClick={() => setActiveUid(dash.uid)}
                  className={`rounded-lg px-4 py-2 text-sm transition-colors ${
                    activeUid === dash.uid
                      ? 'bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/30'
                      : 'bg-surface-raised/40 backdrop-blur-xl text-gray-400 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  {dash.title}
                </button>
                {canDeleteDashboard(user?.role) && (
                  <button
                    onClick={(e) => { e.stopPropagation(); void handleDelete(dash.uid, dash.title) }}
                    title={t('delete')}
                    className="rounded px-1.5 py-1 text-xs text-gray-500 hover:bg-white/5 hover:text-red-400"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
          {deleteError && <p className="text-sm text-red-400">{deleteError}</p>}

          {active && (
            <iframe
              key={`${active.uid}-${theme}`}
              title={active.title}
              src={buildUrl(active, true, theme)}
              className="w-full rounded-lg border border-edge bg-surface"
              style={{ height: 'calc(100vh - 220px)', minHeight: '600px' }}
            />
          )}
        </>
      )}
    </div>
  )
}
