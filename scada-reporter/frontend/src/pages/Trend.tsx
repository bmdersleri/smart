import { useState, useRef, useEffect, type MouseEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettings } from '../context/SettingsContext'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getTags, getTrendAgg, getTrendRange, generateReport,
  getAnnotations, createAnnotation, deleteAnnotation,
} from '../api/client'
import { useSortable } from '../hooks/useSortable'
import SortHeader from '../components/SortHeader'
import { format } from 'date-fns'
import { toPng } from 'html-to-image'
import { parseUtc } from '../utils/time'
import {
  COLORS,
  HOURS,
  type ActivePayloadRow,
  type ChartDataPoint,
  type Preset,
  type TrendSeries,
} from './trend/constants'
import { loadPresets, storePresets } from './trend/presets'
import { Toast } from './trend/Toast'
import { TrendChart } from './trend/TrendChart'
import { TrendTagSelector } from './trend/TrendTagSelector'

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
  const chartDataRef = useRef<ChartDataPoint[]>([])
  const [activePayload, setActivePayload] = useState<ActivePayloadRow[]>([])
  const { sorted: payloadRows, sort: pSort, toggle: pToggle } = useSortable(activePayload)
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null)

  const { data: tags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
  })
  const { data: series = [], isLoading } = useQuery<TrendSeries[]>({
    queryKey: ['trend', selected, hours],
    queryFn: () =>
      selected.length ? getTrendAgg(selected, hours).then((r) => r.data) : Promise.resolve([]),
    enabled: selected.length > 0,
    refetchInterval: 30000,
  })

  // F10: previous equal-length window (period comparison). Overlaid by shifting the time axis by +hours.
  const { data: prevSeries = [] } = useQuery<TrendSeries[]>({
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
    storePresets(updated)
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
    storePresets(updated)
    setPresets(updated)
  }

  const timeline: Record<string, ChartDataPoint> = {}
  series.forEach((s) => {
    s.data.forEach(({ t: ts, v }) => {
      const key = format(parseUtc(ts), 'dd.MM HH:mm')
      timeline[key] ??= { t: key, _iso: ts }
      timeline[key][s.name] = v
    })
  })
  // F10: shift the previous window by +hours and overlay it on the same axis
  if (compareMode) {
    const shiftMs = hours * 3600_000
    prevSeries.forEach((s) => {
      s.data.forEach(({ t: ts, v }) => {
        const shifted = new Date(parseUtc(ts).getTime() + shiftMs)
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

  const handleContextMenu = (e: MouseEvent) => {
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
    .map((a) => ({ ...a, key: format(parseUtc(a.ts), 'dd.MM HH:mm') }))
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
        <TrendTagSelector
          panelOpen={panelOpen}
          tagSearch={tagSearch}
          setTagSearch={setTagSearch}
          selectorMode={selectorMode}
          setSelectorMode={setSelectorMode}
          selected={selected}
          setSelected={setSelected}
          tags={tags}
          filteredTags={filteredTags}
          presets={presets}
          savingName={savingName}
          setSavingName={setSavingName}
          savePreset={savePreset}
          loadPreset={loadPreset}
          deletePreset={deletePreset}
          toggleTag={toggle}
        />

        <TrendChart
          chartContainerRef={chartContainerRef}
          selectedCount={selected.length}
          isLoading={isLoading}
          chartData={chartData}
          series={series}
          compareMode={compareMode}
          annotateMode={annotateMode}
          axisLeftMargin={axisLeftMargin}
          gridStroke={gridStroke}
          brushStroke={brushStroke}
          brushFill={brushFill}
          brushIndices={brushIndices}
          setBrushIndices={setBrushIndices}
          annotationLines={annotationLines}
          handleMouseMove={handleMouseMove}
          handleMouseLeave={handleMouseLeave}
          handleChartClick={handleChartClick}
          handleContextMenu={handleContextMenu}
        />
      </div>

      {activePayload.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500">
                <SortHeader label={t('col_tag')} sortKey="name" sort={pSort} onToggle={pToggle} className="pb-1 font-normal" />
                <SortHeader label={t('col_value')} sortKey="value" sort={pSort} onToggle={pToggle} align="right" className="pb-1 font-normal pe-4" />
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
                  <td className="py-0.5 text-end pe-4 font-mono text-white">{row.value.toFixed(2)}</td>
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
                  {format(parseUtc(a.ts), 'dd.MM HH:mm')}
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
            className="w-full text-start px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <span className="text-gray-500">↓</span> {t('ctx_save_png')}
          </button>
          <button
            onClick={() => { exportReport(); setCtxMenu(null) }}
            disabled={selected.length === 0 || exporting}
            className="w-full text-start px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <span className="text-gray-500">↓</span> {t('ctx_excel_report')}
          </button>
          <div className="border-t border-gray-800 my-1" />
          <button
            onClick={() => { setBrushIndices(null); setCtxMenu(null) }}
            disabled={brushIndices === null}
            className="w-full text-start px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <span className="text-gray-500">↺</span> {t('ctx_reset_zoom')}
          </button>
          <button
            onClick={() => { setSelected([]); setCtxMenu(null) }}
            disabled={selected.length === 0}
            className="w-full text-start px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-red-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <span className="text-gray-500">✕</span> {t('ctx_clear_selection')}
          </button>
        </div>
      )}

      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}
