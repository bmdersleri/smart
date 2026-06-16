import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettings } from '../context/SettingsContext'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getTags, getTrendAgg, getTrendRange, generateReport,
  getGroupTree, getAnnotations, createAnnotation, deleteAnnotation,
} from '../api/client'
import type { GroupNode, Tag } from '../api/client'
import { useSortable } from '../hooks/useSortable'
import SortHeader from '../components/SortHeader'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Brush, ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import { toPng } from 'html-to-image'

const COLORS = ['#f87171', '#34d399', '#facc15', '#60a5fa', '#a78bfa', '#fb923c', '#f472b6', '#38bdf8']
const HOURS = [
  { v: 1, key: 'hours_1' },
  { v: 6, key: 'hours_6' },
  { v: 24, key: 'hours_24' },
  { v: 168, key: 'hours_168' },
]
const PRESET_KEY = 'trend_presets'

interface Preset { name: string; tag_ids: number[]; hours: number }

function loadPresets(): Preset[] {
  try { return JSON.parse(localStorage.getItem(PRESET_KEY) ?? '[]') } catch { return [] }
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="fixed bottom-4 right-4 bg-gray-800 border border-gray-600 text-gray-200 text-sm px-4 py-3 rounded-xl shadow-xl z-50 flex items-center gap-3">
      <span>{message}</span>
      <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
    </div>
  )
}

function TreeNode({
  node, tagMap, selected, onToggle, depth,
}: {
  node: GroupNode; tagMap: Map<number, Tag>; selected: number[]
  onToggle: (id: number) => void; depth: number
}) {
  const [open, setOpen] = useState(depth < 1)
  const leafTags = node.tag_ids.map((id) => tagMap.get(id)).filter(Boolean) as Tag[]
  const hasContent = leafTags.length > 0 || node.children.length > 0
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1 px-1 py-1 text-xs text-gray-300 hover:text-white"
        style={{ paddingLeft: depth * 10 + 4 }}
      >
        <span className="text-gray-500 w-3">{hasContent ? (open ? '▾' : '▸') : '·'}</span>
        <span className="truncate font-medium">{node.name}</span>
        <span className="text-gray-600 ml-auto">{node.tag_ids.length || ''}</span>
      </button>
      {open && (
        <div>
          {node.children.map((c, i) => (
            <TreeNode key={c.id ?? `${node.name}-${i}`} node={c} tagMap={tagMap} selected={selected} onToggle={onToggle} depth={depth + 1} />
          ))}
          {leafTags.map((t) => {
            const sel = selected.includes(t.id)
            const idx = selected.indexOf(t.id)
            const color = sel ? COLORS[idx % COLORS.length] : '#6b7280'
            return (
              <button
                key={t.id}
                onClick={() => onToggle(t.id)}
                className={`w-full text-left py-1 rounded-lg text-sm flex items-center gap-2 ${sel ? 'bg-gray-800/60 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}
                style={{ paddingLeft: (depth + 1) * 10 + 8 }}
              >
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                <span className="truncate">{t.name}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function GroupTree({
  mode, tags, selected, onToggle,
}: {
  mode: 'auto' | 'manual'; tags: Tag[]; selected: number[]; onToggle: (id: number) => void
}) {
  const { t } = useTranslation('trend')
  const { data: tree = [] } = useQuery({
    queryKey: ['groupTree', mode],
    queryFn: () => getGroupTree(mode).then((r) => r.data),
  })
  const tagMap = new Map(tags.map((tg) => [tg.id, tg]))
  if (tree.length === 0) return <p className="text-gray-500 text-xs px-1">{t('no_group')}</p>
  return (
    <div className="space-y-0.5">
      {tree.map((n, i) => (
        <TreeNode key={n.id ?? `root-${i}`} node={n} tagMap={tagMap} selected={selected} onToggle={onToggle} depth={0} />
      ))}
    </div>
  )
}

export default function Trend() {
  const { t } = useTranslation(['trend', 'common'])
  const { trendChartHeight, theme } = useSettings()
  const isLight = theme === 'light'
  const gridStroke = isLight ? '#e2e8f0' : '#1f2937'
  const brushStroke = isLight ? '#cbd5e1' : '#374151'
  const brushFill = isLight ? '#f1f5f9' : '#1f2937'
  const qc = useQueryClient()
  const [selected, setSelected] = useState<number[]>([])
  const [hours, setHours] = useState(24)
  const [tagSearch, setTagSearch] = useState('')
  const [selectorMode, setSelectorMode] = useState<'flat' | 'auto' | 'manual'>('flat')
  const [compareMode, setCompareMode] = useState(false)
  const [annotateMode, setAnnotateMode] = useState(false)
  const [toast, setToast] = useState('')
  const [exporting, setExporting] = useState(false)
  const [presets, setPresets] = useState<Preset[]>(loadPresets)
  const [savingName, setSavingName] = useState<string | null>(null)
  const [brushIndices, setBrushIndices] = useState<[number, number] | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const brushIndicesRef = useRef<[number, number] | null>(null)
  const chartDataRef = useRef<typeof chartData>([])
  const [activePayload, setActivePayload] = useState<Array<{ name: string; value: number; color: string; unit: string }>>([])
  const { sorted: payloadRows, sort: pSort, toggle: pToggle } = useSortable(activePayload)
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null)

  const { data: tags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
  })
  const { data: series = [], isLoading } = useQuery({
    queryKey: ['trend', selected, hours],
    queryFn: () =>
      selected.length ? getTrendAgg(selected, hours).then((r) => r.data) : Promise.resolve([]),
    enabled: selected.length > 0,
    refetchInterval: 30000,
  })

  // F10: previous equal-length window (period comparison). Overlaid by shifting the time axis by +hours.
  const { data: prevSeries = [] } = useQuery({
    queryKey: ['trendPrev', selected, hours],
    queryFn: () => {
      const now = Date.now()
      const prevEnd = new Date(now - hours * 3600_000).toISOString()
      const prevStart = new Date(now - 2 * hours * 3600_000).toISOString()
      return getTrendRange(selected, prevStart, prevEnd).then((r) => r.data)
    },
    enabled: compareMode && selected.length > 0,
    refetchInterval: 30000,
  })

  // F9: shared annotations (selected tags + chart-level)
  const { data: annotations = [] } = useQuery({
    queryKey: ['annotations', selected, hours],
    queryFn: () => {
      const start = new Date(Date.now() - hours * 3600_000).toISOString()
      return getAnnotations({ tag_ids: selected, start }).then((r) => r.data)
    },
    enabled: selected.length > 0,
    refetchInterval: 30000,
  })

  const filteredTags = tagSearch
    ? tags.filter(
        (t) =>
          t.name.toLowerCase().includes(tagSearch.toLowerCase()) ||
          t.device.toLowerCase().includes(tagSearch.toLowerCase())
      )
    : tags

  const toggle = (id: number) => {
    if (selected.includes(id)) {
      setSelected((s) => s.filter((x) => x !== id))
    } else {
      setSelected((s) => [...s, id])
    }
  }

  const savePreset = () => {
    const name = (savingName ?? '').trim()
    if (!name) return
    const updated = [
      { name, tag_ids: selected, hours },
      ...presets.filter((p) => p.name !== name),
    ]
    localStorage.setItem(PRESET_KEY, JSON.stringify(updated))
    setPresets(updated)
    setSavingName(null)
    setToast(t('toast_preset_saved', { name }))
    setTimeout(() => setToast(''), 3000)
  }

  const loadPreset = (p: Preset) => {
    setSelected(p.tag_ids.filter((id) => tags.some((t) => t.id === id)))
    setHours(p.hours)
  }

  const deletePreset = (name: string) => {
    const updated = presets.filter((p) => p.name !== name)
    localStorage.setItem(PRESET_KEY, JSON.stringify(updated))
    setPresets(updated)
  }

  const timeline: Record<string, Record<string, number | string>> = {}
  series.forEach((s) => {
    s.data.forEach(({ t: ts, v }) => {
      const key = format(parseISO(ts + 'Z'), 'dd.MM HH:mm')
      timeline[key] ??= { t: key, _iso: ts }
      timeline[key][s.name] = v
    })
  })
  // F10: shift the previous window by +hours and overlay it on the same axis
  if (compareMode) {
    const shiftMs = hours * 3600_000
    prevSeries.forEach((s) => {
      s.data.forEach(({ t: ts, v }) => {
        const shifted = new Date(parseISO(ts + 'Z').getTime() + shiftMs)
        const key = format(shifted, 'dd.MM HH:mm')
        timeline[key] ??= { t: key, _iso: shifted.toISOString() }
        timeline[key][`${s.name} ${t('previous_suffix')}`] = v
      })
    })
  }
  const chartData = Object.values(timeline).sort((a, b) =>
    String(a.t).localeCompare(String(b.t))
  )

  // Reset brush when selection or time range changes
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setBrushIndices(null)
  }, [selected, hours])

  useEffect(() => { brushIndicesRef.current = brushIndices }, [brushIndices])
  useEffect(() => { chartDataRef.current = chartData })

  const axisLeftMargin = Math.max(55, series.length * 52)

  useEffect(() => {
    const el = chartContainerRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const data = chartDataRef.current
      if (data.length < 2) return
      const len = data.length
      const [s, en] = brushIndicesRef.current ?? [0, len - 1]
      const windowSize = en - s
      const zoomDir = e.deltaY > 0 ? 1 : -1
      const step = Math.max(1, Math.round(windowSize * 0.15))
      const newWindow = Math.max(2, Math.min(len - 1, windowSize + zoomDir * step * 2))
      const center = Math.round((s + en) / 2)
      const newStart = Math.max(0, center - Math.floor(newWindow / 2))
      const newEnd = Math.min(len - 1, newStart + newWindow)
      setBrushIndices([newStart, newEnd])
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  const exportReport = async () => {
    if (!selected.length || exporting) return
    setExporting(true)
    try {
      const now = new Date()
      const end = now.toISOString()
      const start = new Date(now.getTime() - hours * 60 * 60 * 1000).toISOString()
      const res = await generateReport({
        tag_ids: selected,
        start,
        end,
        interval: 'hourly',
        format: 'excel',
      })
      const blob = new Blob([res.data as unknown as BlobPart], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `trend-rapor-${format(new Date(), 'yyyyMMdd-HHmm')}.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setToast(t('toast_excel_downloaded'))
      setTimeout(() => setToast(''), 3000)
    } catch (err) {
      console.error('Report export failed:', err)
      setToast(t('toast_report_failed'))
      setTimeout(() => setToast(''), 3000)
    } finally {
      setExporting(false)
    }
  }

  const exportPNG = () => {
    const container = chartContainerRef.current
    if (!container) return

    const rect = container.getBoundingClientRect()
    toPng(container, {
      backgroundColor: isLight ? '#ffffff' : '#111827',
      pixelRatio: 2,
      width: rect.width,
      height: rect.height,
    }).then((dataUrl) => {
      const a = document.createElement('a')
      a.download = `trend-${format(new Date(), 'yyyyMMdd-HHmm')}.png`
      a.href = dataUrl
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }).catch((err) => {
      console.error('PNG export failed:', err)
    })
  }

  const handleMouseMove = (state: Record<string, unknown>) => {
    const activeIndex = state.activeIndex as number | undefined
    if (activeIndex != null && activeIndex >= 0) {
      const point = chartDataRef.current[activeIndex] as Record<string, unknown> | undefined
      if (point) {
        const mapped = series.map((s, i) => ({
          name: s.name,
          value: Number(point[s.name] ?? NaN),
          color: COLORS[i % COLORS.length],
          unit: s.unit ?? '',
        })).filter((r) => !isNaN(r.value))
        setActivePayload(mapped)
        return
      }
    }
    setActivePayload([])
  }

  const handleMouseLeave = () => {
    setActivePayload([])
  }

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    setCtxMenu({ x: e.clientX, y: e.clientY })
  }

  const refreshAnnotations = () => qc.invalidateQueries({ queryKey: ['annotations'] })

  const handleChartClick = (state: Record<string, unknown>) => {
    if (!annotateMode) return
    const idx = state.activeTooltipIndex as number | undefined
    if (idx == null || idx < 0) return
    const point = chartDataRef.current[idx] as Record<string, unknown> | undefined
    const iso = point?._iso as string | undefined
    if (!iso) return
    const text = window.prompt(t('prompt_note'))?.trim()
    if (!text) return
    createAnnotation({ tag_id: null, ts: iso, text })
      .then(() => { refreshAnnotations(); setToast(t('toast_note_added')); setTimeout(() => setToast(''), 2500) })
      .catch(() => { setToast(t('toast_note_failed')); setTimeout(() => setToast(''), 3000) })
  }

  const removeAnnotation = (id: number) => {
    deleteAnnotation(id)
      .then(refreshAnnotations)
      .catch(() => { setToast(t('toast_note_deleted_failed')); setTimeout(() => setToast(''), 3000) })
  }

  // bucket keys of annotations on the chart (for ReferenceLine)
  const chartKeys = new Set(chartData.map((d) => String(d.t)))
  const annotationLines = annotations
    .map((a) => ({ ...a, key: format(parseISO(a.ts + 'Z'), 'dd.MM HH:mm') }))
    .filter((a) => chartKeys.has(a.key))

  useEffect(() => {
    if (!ctxMenu) return
    const close = () => setCtxMenu(null)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('click', close)
    window.addEventListener('keydown', onKey)
    window.addEventListener('scroll', close, true)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', close, true)
    }
  }, [ctxMenu])

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">{t('title')}</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setPanelOpen((v) => !v)}
            className="px-2 py-1 text-xs rounded-lg bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
            title={panelOpen ? t('panel_hide_title') : t('panel_show_title')}
          >
            {panelOpen ? t('panel_hide') : t('panel_show')}
          </button>
          {HOURS.map(({ v, key }) => (
            <button
              key={v}
              onClick={() => setHours(v)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                hours === v ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {t(key)}
            </button>
          ))}
          {selected.length > 0 && (
            <button
              onClick={() => setCompareMode((v) => !v)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${compareMode ? 'bg-amber-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'}`}
              title={t('compare_title')}
            >
              {t('compare')}
            </button>
          )}
          {selected.length > 0 && (
            <button
              onClick={() => setAnnotateMode((v) => !v)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${annotateMode ? 'bg-yellow-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'}`}
              title={t('annotate_title')}
            >
              {t('annotate')}
            </button>
          )}
          {selected.length > 0 && (
            <button
              onClick={exportPNG}
              className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
              title={t('export_png_title')}
            >
              {t('export_png')}
            </button>
          )}
          {selected.length > 0 && (
            <button
              onClick={exportReport}
              disabled={exporting}
              className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white disabled:opacity-50 transition-colors"
              title={t('export_excel_title')}
            >
              {exporting ? '...' : t('export_excel')}
            </button>
          )}
          {brushIndices !== null && chartData.length > 0 && (
            <button
              onClick={() => setBrushIndices(null)}
              className="px-3 py-1.5 text-xs rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
              title={t('reset_zoom_title')}
            >
              {t('reset_zoom')}
            </button>
          )}
        </div>
      </div>

      <div className="flex gap-4" style={{ height: trendChartHeight }}>
        {/* Tag selector */}
        <div className={`bg-gray-900 border border-gray-800 rounded-xl flex-shrink-0 space-y-2 overflow-y-auto transition-all duration-200 ${panelOpen ? 'w-52 p-3' : 'w-0 p-0'}`}>
          <input
            value={tagSearch}
            onChange={(e) => setTagSearch(e.target.value)}
            placeholder={t('search_placeholder')}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />

          {/* F4: view mode — flat list / automatic (PLC→device) / manual hierarchy */}
          <div className="flex gap-1 bg-gray-800 rounded-lg p-0.5">
            {([['flat', t('mode_flat')], ['auto', t('mode_auto')], ['manual', t('mode_manual')]] as const).map(([m, l]) => (
              <button
                key={m}
                onClick={() => setSelectorMode(m)}
                className={`flex-1 px-1 py-1 text-[11px] rounded-md transition-colors ${selectorMode === m ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
              >
                {l}
              </button>
            ))}
          </div>

          {/* Save / clear actions */}
          {selected.length > 0 && savingName === null && (
            <div className="flex gap-1.5">
              <button
                onClick={() => setSavingName('')}
                className="flex-1 px-2 py-1 text-xs bg-blue-700/40 hover:bg-blue-700/60 text-blue-300 rounded-lg transition-colors"
              >
                {t('save')}
              </button>
              <button
                onClick={() => setSelected([])}
                className="flex-1 px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-red-400 rounded-lg transition-colors"
              >
                {t('clear_all')}
              </button>
            </div>
          )}

          {/* Save name input */}
          {savingName !== null && (
            <div className="space-y-1">
              <input
                autoFocus
                value={savingName}
                onChange={(e) => setSavingName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') savePreset(); if (e.key === 'Escape') setSavingName(null) }}
                placeholder={t('preset_name_placeholder')}
                className="w-full bg-gray-800 border border-blue-600 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none"
              />
              <div className="flex gap-1">
                <button
                  onClick={savePreset}
                  disabled={!savingName.trim()}
                  className="flex-1 px-2 py-1 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-lg transition-colors"
                >
                  {t('save')}
                </button>
                <button
                  onClick={() => setSavingName(null)}
                  className="px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg transition-colors"
                >
                  {t('common:cancel')}
                </button>
              </div>
            </div>
          )}

          {/* Saved presets */}
          {presets.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-gray-500 uppercase tracking-wide px-1">{t('saved_presets')}</p>
              {presets.map((p) => {
                const hk = HOURS.find((h) => h.v === p.hours)?.key
                return (
                <div key={p.name} className="flex items-center gap-1 group">
                  <button
                    onClick={() => loadPreset(p)}
                    className="flex-1 text-left px-2 py-1 rounded-lg text-xs text-gray-300 hover:bg-gray-800 hover:text-white transition-colors truncate"
                    title={`${p.tag_ids.length} tag · ${hk ? t(hk) : p.hours + 'h'}`}
                  >
                    {p.name}
                  </button>
                  <button
                    onClick={() => deletePreset(p.name)}
                    className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 text-xs transition-all px-1"
                    title={t('common:delete')}
                  >
                    ✕
                  </button>
                </div>
                )
              })}
              <div className="border-t border-gray-800 pt-1" />
            </div>
          )}

          <p className="text-xs text-gray-500 uppercase tracking-wide px-1">{t('select_tags')}</p>
          {selectorMode === 'flat' ? (
            <div className="space-y-1">
              {filteredTags.length === 0 && (
                <p className="text-gray-500 text-xs px-1">{t('no_match')}</p>
              )}
              {filteredTags.map((t) => {
                const selIdx = selected.indexOf(t.id)
                const color = selIdx >= 0 ? COLORS[selIdx % COLORS.length] : '#6b7280'
                return (
                  <button
                    key={t.id}
                    onClick={() => toggle(t.id)}
                    className={`w-full text-left px-2 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                      selIdx >= 0
                        ? 'bg-gray-800/60 text-white'
                        : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                    }`}
                  >
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0 transition-colors"
                      style={{ backgroundColor: color }}
                    />
                    <span className="truncate">{t.name}</span>
                  </button>
                )
              })}
            </div>
          ) : (
            <GroupTree mode={selectorMode} tags={tags} selected={selected} onToggle={toggle} />
          )}
        </div>

        {/* Chart */}
        <div
          ref={chartContainerRef}
          className="flex-1 bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col"
          style={{ userSelect: 'none' }}
          onContextMenu={handleContextMenu}
        >
          {selected.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
              {t('select_from_panel')}
            </div>
          ) : isLoading ? (
            <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
              {t('loading')}
            </div>
          ) : chartData.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
              {t('no_data_range')}
            </div>
          ) : (
            <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={chartData}
                margin={{ top: 4, right: 16, left: axisLeftMargin, bottom: 4 }}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
                onClick={handleChartClick}
                style={{ cursor: annotateMode ? 'crosshair' : undefined }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
                <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#6b7280' }} interval="preserveStartEnd" />
                {series.map((s, i) => {
                  const color = COLORS[i % COLORS.length]
                  return (
                    <YAxis
                      key={s.tag_id}
                      yAxisId={`y_${s.tag_id}`}
                      orientation="left"
                      width={50}
                      tick={{ fontSize: 10, fill: color }}
                      tickLine={{ stroke: color }}
                      axisLine={{ stroke: color }}
                      label={{
                        value: s.unit,
                        angle: -90,
                        position: 'insideLeft',
                        fill: color,
                        fontSize: 10,
                        dx: -8,
                      }}
                    />
                  )
                })}
                <Tooltip
                  cursor={{ stroke: '#f59e0b', strokeWidth: 1, strokeDasharray: '4 2' }}
                  contentStyle={{ display: 'none' }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
                <Brush
                  dataKey="t"
                  height={24}
                  startIndex={brushIndices ? brushIndices[0] : 0}
                  endIndex={brushIndices ? brushIndices[1] : Math.max(0, chartData.length - 1)}
                  onChange={(range) => {
                    if (
                      range &&
                      typeof range.startIndex === 'number' &&
                      typeof range.endIndex === 'number'
                    ) {
                      setBrushIndices([range.startIndex, range.endIndex])
                    }
                  }}
                  stroke={brushStroke}
                  fill={brushFill}
                  travellerWidth={8}
                />
                {series.map((s, i) => (
                  <Line
                    key={s.tag_id}
                    type="monotone"
                    dataKey={s.name}
                    stroke={COLORS[i % COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                    yAxisId={`y_${s.tag_id}`}
                  />
                ))}
                {/* F10: previous period (dashed) */}
                {compareMode && series.map((s, i) => (
                  <Line
                    key={`prev_${s.tag_id}`}
                    type="monotone"
                    dataKey={`${s.name} ${t('previous_suffix')}`}
                    stroke={COLORS[i % COLORS.length]}
                    strokeWidth={1.5}
                    strokeDasharray="5 4"
                    strokeOpacity={0.6}
                    dot={false}
                    connectNulls
                    yAxisId={`y_${s.tag_id}`}
                  />
                ))}
                {/* F9: annotation vertical lines */}
                {series.length > 0 && annotationLines.map((a) => (
                  <ReferenceLine
                    key={a.id}
                    x={a.key}
                    yAxisId={`y_${series[0].tag_id}`}
                    stroke="#fbbf24"
                    strokeDasharray="2 2"
                    label={{ value: '📌', position: 'top', fontSize: 12 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {activePayload.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500">
                <SortHeader label={t('col_tag')} sortKey="name" sort={pSort} onToggle={pToggle} className="pb-1 font-normal" />
                <SortHeader label={t('col_value')} sortKey="value" sort={pSort} onToggle={pToggle} align="right" className="pb-1 font-normal pr-4" />
                <SortHeader label={t('col_unit')} sortKey="unit" sort={pSort} onToggle={pToggle} className="pb-1 font-normal" />
              </tr>
            </thead>
            <tbody>
              {payloadRows.map((row) => (
                <tr key={row.name}>
                  <td className="py-0.5">
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: row.color }} />
                      <span className="truncate max-w-[200px]" style={{ color: row.color }}>{row.name}</span>
                    </span>
                  </td>
                  <td className="py-0.5 text-right pr-4 font-mono text-white">{row.value.toFixed(2)}</td>
                  <td className="py-0.5 text-gray-400">{row.unit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected.length > 0 && annotations.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">{t('notes_title', { value: annotations.length })}</p>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {annotations.map((a) => (
              <div key={a.id} className="flex items-center gap-2 text-xs group">
                <span className="text-gray-500 font-mono w-28 flex-shrink-0">
                  {format(parseISO(a.ts + 'Z'), 'dd.MM HH:mm')}
                </span>
                <span className="text-gray-200 flex-1">{a.text}</span>
                <span className="text-gray-600">{a.username}</span>
                <button
                  onClick={() => removeAnnotation(a.id)}
                  className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 transition-all px-1"
                  title={t('delete_note_title')}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {annotateMode && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-yellow-600 text-white text-xs px-4 py-2 rounded-xl shadow-xl z-40">
          {t('annotate_banner')}
        </div>
      )}

      {ctxMenu && (
        <div
          className="fixed z-50 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl py-1 min-w-[180px]"
          style={{ top: ctxMenu.y, left: ctxMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => { exportPNG(); setCtxMenu(null) }}
            disabled={selected.length === 0 || chartData.length === 0}
            className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <span className="text-gray-500">↓</span> {t('ctx_save_png')}
          </button>
          <button
            onClick={() => { exportReport(); setCtxMenu(null) }}
            disabled={selected.length === 0 || exporting}
            className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <span className="text-gray-500">↓</span> {t('ctx_excel_report')}
          </button>
          <div className="border-t border-gray-800 my-1" />
          <button
            onClick={() => { setBrushIndices(null); setCtxMenu(null) }}
            disabled={brushIndices === null}
            className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <span className="text-gray-500">↺</span> {t('ctx_reset_zoom')}
          </button>
          <button
            onClick={() => { setSelected([]); setCtxMenu(null) }}
            disabled={selected.length === 0}
            className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-red-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <span className="text-gray-500">✕</span> {t('ctx_clear_selection')}
          </button>
        </div>
      )}

      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}
