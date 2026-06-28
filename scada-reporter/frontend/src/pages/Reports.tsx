import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getTags, generateReport, getReportHistory, downloadHistoryReport } from '../api/client'
import type { ReportHistoryEntry } from '../api/client'
import { format, subDays, startOfDay, endOfDay } from 'date-fns'
import { enUS, tr, ru, de } from 'date-fns/locale'
import { parseUtc } from '../utils/time'

const DATE_LOCALES: Record<string, typeof tr> = { en: enUS, tr, ru, de }

const fmt = (d: Date) => format(d, "yyyy-MM-dd'T'HH:mm")

// Stable preset identifiers; labels are resolved at render time via i18n.
const PRESETS = [
  { id: 'today', start: () => startOfDay(new Date()), end: () => new Date() },
  { id: 'yesterday', start: () => startOfDay(subDays(new Date(), 1)), end: () => endOfDay(subDays(new Date(), 1)) },
  { id: 'last_7d', start: () => startOfDay(subDays(new Date(), 7)), end: () => new Date() },
  { id: 'last_30d', start: () => startOfDay(subDays(new Date(), 30)), end: () => new Date() },
]

const PRESET_LABEL_KEY: Record<string, string> = {
  today: 'preset_today',
  yesterday: 'preset_yesterday',
  last_7d: 'preset_last_7d',
  last_30d: 'preset_last_30d',
}

const REPORT_PRESET_KEY = 'report_presets'

interface ReportPreset {
  name: string
  tag_ids: number[]
  interval: string
  time_preset?: string
}

function loadReportPresets(): ReportPreset[] {
  try { return JSON.parse(localStorage.getItem(REPORT_PRESET_KEY) ?? '[]') } catch { return [] }
}

function HistoryRow({ entry }: { entry: ReportHistoryEntry }) {
  const { t, i18n } = useTranslation('reports')
  const [downloading, setDownloading] = useState(false)
  const dateLocale = DATE_LOCALES[i18n.language] ?? enUS

  const reDownload = async () => {
    setDownloading(true)
    try {
      const r = await downloadHistoryReport(entry.id)
      const ext = entry.format === 'excel' ? 'xlsx' : 'json'
      const url = URL.createObjectURL(new Blob([r.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `scada_rapor_${entry.id}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setDownloading(false)
    }
  }

  const dateStr = format(parseUtc(entry.created_at), 'dd.MM.yyyy HH:mm', { locale: dateLocale })
  const tagCount = entry.tag_ids.length
  const rangeStart = format(parseUtc(entry.start), 'dd.MM', { locale: dateLocale })
  const rangeEnd = format(parseUtc(entry.end), 'dd.MM', { locale: dateLocale })

  return (
    <div className="flex items-center justify-between py-2.5 border-t border-edge">
      <div className="flex items-center gap-3">
        <span className="text-gray-500 text-sm">📄</span>
        <div>
          <span className="text-sm text-gray-300">{dateStr}</span>
          <span className="text-gray-600 mx-2">·</span>
          <span className="text-xs text-gray-500">{t('tag_count', { value: tagCount })}</span>
          <span className="text-gray-600 mx-2">·</span>
          <span className="text-xs text-gray-500">{rangeStart}–{rangeEnd}</span>
          <span className="text-gray-600 mx-2">·</span>
          <span className="text-xs text-gray-500 uppercase">{entry.format}</span>
        </div>
      </div>
      <button
        onClick={reDownload}
        disabled={downloading}
        className="text-xs text-cyan-400 hover:text-blue-300 disabled:opacity-50 transition-colors"
      >
        {downloading ? '...' : t('download')}
      </button>
    </div>
  )
}

export default function Reports() {
  const { t } = useTranslation(['reports', 'common'])
  const { data: tags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
  })
  const { data: history = [], refetch: refetchHistory } = useQuery({
    queryKey: ['report-history'],
    queryFn: () => getReportHistory().then((r) => r.data),
  })

  const [selectedTags, setSelectedTags] = useState<number[]>([])
  const [start, setStart] = useState(fmt(startOfDay(new Date())))
  const [end, setEnd] = useState(fmt(new Date()))
  const [interval, setIntervalVal] = useState('hourly')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeTimePreset, setActiveTimePreset] = useState<string>('today')
  const [presets, setPresets] = useState<ReportPreset[]>(loadReportPresets)
  const [savingName, setSavingName] = useState<string | null>(null)

  const toggleTag = (id: number) =>
    setSelectedTags((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id])

  const selectPreset = (p: typeof PRESETS[0]) => {
    setStart(fmt(p.start()))
    setEnd(fmt(p.end()))
    setActiveTimePreset(p.id)
  }

  const saveReportPreset = () => {
    const name = (savingName ?? '').trim()
    if (!name) return
    const updated: ReportPreset[] = [
      { name, tag_ids: selectedTags, interval, time_preset: activeTimePreset },
      ...presets.filter((p) => p.name !== name),
    ]
    localStorage.setItem(REPORT_PRESET_KEY, JSON.stringify(updated))
    setPresets(updated)
    setSavingName(null)
  }

  const loadReportPreset = (p: ReportPreset) => {
    setSelectedTags(p.tag_ids.filter((id) => tags.some((t) => t.id === id)))
    setIntervalVal(p.interval)
    if (p.time_preset) {
      const tp = PRESETS.find((x) => x.id === p.time_preset)
      if (tp) { setStart(fmt(tp.start())); setEnd(fmt(tp.end())); setActiveTimePreset(tp.id) }
    }
  }

  const deleteReportPreset = (name: string) => {
    const updated = presets.filter((p) => p.name !== name)
    localStorage.setItem(REPORT_PRESET_KEY, JSON.stringify(updated))
    setPresets(updated)
  }

  // Group tags by device
  const groups = tags.reduce<Record<string, typeof tags>>((acc, tag) => {
    const key = tag.device || t('other_device');
    (acc[key] ??= []).push(tag)
    return acc
  }, {})

  const toggleGroup = (groupTags: typeof tags) => {
    const ids = groupTags.map((t) => t.id)
    const allSelected = ids.every((id) => selectedTags.includes(id))
    if (allSelected) {
      setSelectedTags((s) => s.filter((id) => !ids.includes(id)))
    } else {
      setSelectedTags((s) => [...new Set([...s, ...ids])])
    }
  }

  const download = async (outputFormat: 'excel' | 'json') => {
    if (!selectedTags.length) { setError(t('error_select_tag')); return }
    setError(''); setLoading(true)
    try {
      const r = await generateReport({
        tag_ids: selectedTags, start, end, interval: interval, format: outputFormat,
      })
      if (outputFormat === 'excel') {
        const url = URL.createObjectURL(new Blob([r.data]))
        const a = document.createElement('a')
        a.href = url
        a.download = `scada_rapor_${start.slice(0, 10)}_${end.slice(0, 10)}.xlsx`
        a.click()
        URL.revokeObjectURL(url)
      }
      refetchHistory()
    } catch {
      setError(t('error_report_failed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <h1 className="text-xl font-bold text-white">{t('title')}</h1>

      {/* Saved presets */}
      {(presets.length > 0 || selectedTags.length > 0) && (
        <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-gray-300">{t('saved_selections')}</p>
            {selectedTags.length > 0 && savingName === null && (
              <div className="flex gap-1.5">
                <button
                  onClick={() => setSavingName('')}
                  className="px-2.5 py-1 text-xs bg-blue-700/40 hover:bg-blue-700/60 text-blue-300 rounded-lg transition-colors"
                >
                  {t('common:save')}
                </button>
                <button
                  onClick={() => setSelectedTags([])}
                  className="px-2.5 py-1 text-xs bg-surface-sunken hover:bg-gray-700 text-gray-400 hover:text-red-400 rounded-lg transition-colors"
                >
                  {t('clear_all')}
                </button>
              </div>
            )}
          </div>

          {savingName !== null && (
            <div className="flex gap-2 items-center">
              <input
                autoFocus
                value={savingName}
                onChange={(e) => setSavingName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') saveReportPreset(); if (e.key === 'Escape') setSavingName(null) }}
                placeholder={t('selection_name_placeholder')}
                className="flex-1 bg-black/20 border border-white/10 rounded-xl px-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-hidden focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all"
              />
              <button
                onClick={saveReportPreset}
                disabled={!savingName.trim()}
                className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-lg transition-colors"
              >
                {t('common:save')}
              </button>
              <button
                onClick={() => setSavingName(null)}
                className="px-3 py-1.5 text-xs bg-surface-sunken hover:bg-gray-700 text-gray-400 rounded-lg transition-colors"
              >
                {t('common:cancel')}
              </button>
            </div>
          )}

          {presets.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {presets.map((p) => (
                <div key={p.name} className="group flex items-center gap-1 bg-surface-sunken border border-edge-strong rounded-lg px-3 py-1.5">
                  <button
                    onClick={() => loadReportPreset(p)}
                    className="text-sm text-gray-300 hover:text-white transition-colors"
                    title={t('preset_title', {
                      tags: p.tag_ids.length,
                      interval: p.interval,
                      preset: p.time_preset ? t(PRESET_LABEL_KEY[p.time_preset] ?? 'preset_custom') : t('preset_custom'),
                    })}
                  >
                    {p.name}
                    <span className="ms-1.5 text-xs text-gray-500">{t('tag_count', { value: p.tag_ids.length })}</span>
                  </button>
                  <button
                    onClick={() => deleteReportPreset(p.name)}
                    className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 text-xs transition-all ms-1"
                    title={t('delete_title')}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-600">{t('no_saved_selections')}</p>
          )}
        </div>
      )}

      {/* Grouped tag selection */}
      <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-gray-300">{t('tag_selection')}</p>
          <span className="text-xs text-gray-500">{t('tags_selected', { value: selectedTags.length })}</span>
        </div>
        {Object.entries(groups).map(([device, groupTags]) => {
          const allSelected = groupTags.every((t) => selectedTags.includes(t.id))
          return (
            <div key={device}>
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{device}</span>
                <button
                  onClick={() => toggleGroup(groupTags)}
                  className="text-xs text-cyan-400 hover:text-blue-300 transition-colors"
                >
                  {allSelected ? t('deselect_all') : t('select_all')}
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {groupTags.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => toggleTag(t.id)}
                    className={`px-3 py-1.5 text-sm rounded-xl border transition-all duration-200 ${
                      selectedTags.includes(t.id)
                        ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300 shadow-[inset_0_0_12px_rgba(6,182,212,0.1)]'
                        : 'bg-black/20 border-white/5 text-gray-400 hover:border-white/20 hover:text-gray-200'
                    }`}
                  >
                    {t.name}{t.unit ? ` (${t.unit})` : ''}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* Time range */}
      <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 space-y-3">
        <p className="text-sm font-medium text-gray-300">{t('time_range')}</p>
        <div className="flex gap-2 flex-wrap">
          {PRESETS.map((p) => (
              <button key={p.id} onClick={() => selectPreset(p)}
                className={`px-3 py-1.5 text-xs rounded-xl border transition-all duration-200 ${
                  activeTimePreset === p.id
                    ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300 shadow-[inset_0_0_12px_rgba(6,182,212,0.1)]'
                    : 'bg-black/20 border-white/5 text-gray-400 hover:border-white/20 hover:text-gray-200'
                }`}>
              {t(PRESET_LABEL_KEY[p.id])}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">{t('start')}</label>
            <input type="datetime-local" value={start} onChange={(e) => { setStart(e.target.value); setActiveTimePreset('') }}
              className="w-full bg-black/20 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-hidden focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">{t('end')}</label>
            <input type="datetime-local" value={end} onChange={(e) => { setEnd(e.target.value); setActiveTimePreset('') }}
              className="w-full bg-black/20 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-hidden focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all" />
          </div>
        </div>
      </div>

      {/* Grouping */}
      <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 space-y-3">
        <p className="text-sm font-medium text-gray-300">{t('grouping')}</p>
        <div className="flex gap-2">
          {[{ v: 'hourly', l: t('hourly') }, { v: 'daily', l: t('daily') }].map(({ v, l }) => (
              <button key={v} onClick={() => setIntervalVal(v)}
                className={`px-4 py-2 text-sm rounded-xl border transition-all duration-200 ${
                  interval === v
                    ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300 shadow-[inset_0_0_12px_rgba(6,182,212,0.1)]'
                    : 'bg-black/20 border-white/5 text-gray-400 hover:border-white/20 hover:text-gray-200'
                }`}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Download buttons */}
      <div className="flex gap-3">
        <button onClick={() => download('excel')} disabled={loading}
          className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-emerald-500 to-green-600 hover:from-emerald-400 hover:to-green-500 disabled:opacity-50 text-white rounded-xl font-bold tracking-wide text-sm transition-all shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/40 active:scale-95">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          {loading ? t('preparing') : t('excel_download')}
        </button>
        <button onClick={() => download('json')} disabled={loading}
          className="flex items-center gap-2 px-6 py-3 bg-black/30 hover:bg-white/10 disabled:opacity-50 text-gray-300 rounded-xl font-semibold text-sm border border-white/10 transition-all hover:border-white/20 active:scale-95">
          JSON
        </button>
      </div>

      {/* Report history */}
      <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4">
        <p className="text-sm font-medium text-gray-300 mb-1">{t('recent_reports')}</p>
        {history.length === 0 ? (
          <p className="text-gray-500 text-sm py-4">{t('no_reports_yet')}</p>
        ) : (
          history.map((entry) => <HistoryRow key={entry.id} entry={entry} />)
        )}
      </div>
    </div>
  )
}
