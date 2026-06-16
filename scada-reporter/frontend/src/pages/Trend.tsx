import { useState, useRef, useEffect } from 'react'
import { useSettings } from '../context/SettingsContext'
import { useQuery } from '@tanstack/react-query'
import { getTags, getTrend, generateReport } from '../api/client'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Brush, ResponsiveContainer,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import { toPng } from 'html-to-image'

const COLORS = ['#f87171', '#34d399', '#facc15', '#60a5fa', '#a78bfa', '#fb923c', '#f472b6', '#38bdf8']
const HOURS = [
  { v: 1, l: 'Son 1 saat' },
  { v: 6, l: 'Son 6 saat' },
  { v: 24, l: 'Son 24 saat' },
  { v: 168, l: 'Son 7 gün' },
]
const PRESET_KEY = 'trend_presets'

interface Preset { name: string; tag_ids: number[]; hours: number }

function loadPresets(): Preset[] {
  try { return JSON.parse(localStorage.getItem(PRESET_KEY) ?? '[]') } catch { return [] }
}

function ChartCursor({ x, y, height }: { x?: number; y?: number; width?: number; height?: number }) {
  if (x == null || y == null || height == null) return null
  return (
    <line
      x1={x}
      y1={y}
      x2={x}
      y2={y + height}
      stroke="#f59e0b"
      strokeWidth={1}
      strokeDasharray="4 2"
    />
  )
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="fixed bottom-4 right-4 bg-gray-800 border border-gray-600 text-gray-200 text-sm px-4 py-3 rounded-xl shadow-xl z-50 flex items-center gap-3">
      <span>{message}</span>
      <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
    </div>
  )
}

export default function Trend() {
  const { trendChartHeight } = useSettings()
  const [selected, setSelected] = useState<number[]>([])
  const [hours, setHours] = useState(24)
  const [tagSearch, setTagSearch] = useState('')
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

  const { data: tags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
  })
  const { data: series = [], isLoading } = useQuery({
    queryKey: ['trend', selected, hours],
    queryFn: () =>
      selected.length ? getTrend(selected, hours).then((r) => r.data) : Promise.resolve([]),
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
    setToast(`"${name}" kaydedildi`)
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
    s.data.forEach(({ t, v }) => {
      const key = format(parseISO(t + 'Z'), 'dd.MM HH:mm')
      timeline[key] ??= { t: key }
      timeline[key][s.name] = v
    })
  })
  const chartData = Object.values(timeline).sort((a, b) =>
    String(a.t).localeCompare(String(b.t))
  )

  // Reset brush when selection or time range changes
  useEffect(() => {
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
      setToast('Excel raporu indirildi')
      setTimeout(() => setToast(''), 3000)
    } catch (err) {
      console.error('Report export failed:', err)
      setToast('Rapor oluşturulamadı')
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
      backgroundColor: '#111827',
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
    const isActive = Boolean(state.isTooltipActive)
    const payload = state.activePayload as Array<{ name: string; value: number; color: string }> | undefined
    if (isActive && payload && payload.length) {
      const mapped = payload.map((p) => {
        const s = series.find((x) => x.name === p.name)
        return { name: p.name, value: Number(p.value), color: p.color, unit: s?.unit ?? '' }
      })
      setActivePayload(mapped)
    } else {
      setActivePayload([])
    }
  }

  const handleMouseLeave = () => {
    setActivePayload([])
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Trend Grafik</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setPanelOpen((v) => !v)}
            className="px-2 py-1 text-xs rounded-lg bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
            title={panelOpen ? 'Paneli kapat' : 'Paneli aç'}
          >
            {panelOpen ? '⟨ Gizle' : '⟩ Taglar'}
          </button>
          {HOURS.map(({ v, l }) => (
            <button
              key={v}
              onClick={() => setHours(v)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                hours === v ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {l}
            </button>
          ))}
          {selected.length > 0 && (
            <button
              onClick={exportPNG}
              className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
              title="Grafiği PNG olarak indir"
            >
              ↓ PNG
            </button>
          )}
          {selected.length > 0 && (
            <button
              onClick={exportReport}
              disabled={exporting}
              className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white disabled:opacity-50 transition-colors"
              title="Seçili tag'leri Excel raporuna aktar"
            >
              {exporting ? '...' : '↓ Excel'}
            </button>
          )}
          {brushIndices !== null && chartData.length > 0 && (
            <button
              onClick={() => setBrushIndices(null)}
              className="px-3 py-1.5 text-xs rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
              title="Zoom sıfırla"
            >
              ↺ Sıfırla
            </button>
          )}
        </div>
      </div>

      <div className="flex gap-4 min-h-0">
        {/* Tag selector */}
        <div className={`bg-gray-900 border border-gray-800 rounded-xl flex-shrink-0 space-y-2 overflow-hidden transition-all duration-200 ${panelOpen ? 'w-52 p-3' : 'w-0 p-0'}`}>
          <input
            value={tagSearch}
            onChange={(e) => setTagSearch(e.target.value)}
            placeholder="Ara..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />

          {/* Save / clear actions */}
          {selected.length > 0 && savingName === null && (
            <div className="flex gap-1.5">
              <button
                onClick={() => setSavingName('')}
                className="flex-1 px-2 py-1 text-xs bg-blue-700/40 hover:bg-blue-700/60 text-blue-300 rounded-lg transition-colors"
              >
                Kaydet
              </button>
              <button
                onClick={() => setSelected([])}
                className="flex-1 px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-red-400 rounded-lg transition-colors"
              >
                Tümünü Kaldır
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
                placeholder="Seçim adı..."
                className="w-full bg-gray-800 border border-blue-600 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none"
              />
              <div className="flex gap-1">
                <button
                  onClick={savePreset}
                  disabled={!savingName.trim()}
                  className="flex-1 px-2 py-1 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-lg transition-colors"
                >
                  Kaydet
                </button>
                <button
                  onClick={() => setSavingName(null)}
                  className="px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg transition-colors"
                >
                  İptal
                </button>
              </div>
            </div>
          )}

          {/* Saved presets */}
          {presets.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-gray-500 uppercase tracking-wide px-1">Kayıtlı</p>
              {presets.map((p) => (
                <div key={p.name} className="flex items-center gap-1 group">
                  <button
                    onClick={() => loadPreset(p)}
                    className="flex-1 text-left px-2 py-1 rounded-lg text-xs text-gray-300 hover:bg-gray-800 hover:text-white transition-colors truncate"
                    title={`${p.tag_ids.length} tag · ${HOURS.find((h) => h.v === p.hours)?.l ?? p.hours + 'h'}`}
                  >
                    {p.name}
                  </button>
                  <button
                    onClick={() => deletePreset(p.name)}
                    className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 text-xs transition-all px-1"
                    title="Sil"
                  >
                    ✕
                  </button>
                </div>
              ))}
              <div className="border-t border-gray-800 pt-1" />
            </div>
          )}

          <p className="text-xs text-gray-500 uppercase tracking-wide px-1">Tag Seç</p>
          <div className="space-y-1">
            {filteredTags.length === 0 && (
              <p className="text-gray-500 text-xs px-1">Eşleşme yok.</p>
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
        </div>

        {/* Chart */}
        <div
          ref={chartContainerRef}
          className="flex-1 bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col"
          style={{ userSelect: 'none', minHeight: trendChartHeight }}
        >
          {selected.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
              Sol panelden tag seçin
            </div>
          ) : isLoading ? (
            <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
              Yükleniyor...
            </div>
          ) : chartData.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
              Bu aralıkta veri yok.
            </div>
          ) : (
            <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={chartData}
                margin={{ top: 4, right: 16, left: axisLeftMargin, bottom: 4 }}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
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
                  cursor={<ChartCursor />}
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
                  stroke="#374151"
                  fill="#1f2937"
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
              </LineChart>
            </ResponsiveContainer>
            {activePayload.length > 0 && (
              <div className="mt-2 border-t border-gray-700 pt-2">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500">
                      <th className="text-left pb-1 font-normal">Tag</th>
                      <th className="text-right pb-1 font-normal pr-4">Değer</th>
                      <th className="text-left pb-1 font-normal">Birim</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activePayload.map((row) => (
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
            </div>
          )}
        </div>
      </div>

      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}
