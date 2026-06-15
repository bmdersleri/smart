import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTags, getTrend } from '../api/client'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { format, parseISO } from 'date-fns'

const COLORS = ['#60a5fa', '#34d399', '#f59e0b', '#f87171', '#a78bfa', '#fb923c']
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

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="fixed bottom-4 right-4 bg-gray-800 border border-gray-600 text-gray-200 text-sm px-4 py-3 rounded-xl shadow-xl z-50 flex items-center gap-3">
      <span>{message}</span>
      <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
    </div>
  )
}

export default function Trend() {
  const [selected, setSelected] = useState<number[]>([])
  const [hours, setHours] = useState(24)
  const [tagSearch, setTagSearch] = useState('')
  const [toast, setToast] = useState('')
  const [presets, setPresets] = useState<Preset[]>(loadPresets)
  const [savingName, setSavingName] = useState<string | null>(null)

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

  const selectedUnits: string[] = []
  const unitToAxis: Record<string, 'left' | 'right'> = {}
  series.forEach((s) => {
    if (!unitToAxis[s.unit]) {
      if (selectedUnits.length === 0) {
        unitToAxis[s.unit] = 'left'
        selectedUnits.push(s.unit)
      } else if (selectedUnits.length === 1 && !selectedUnits.includes(s.unit)) {
        unitToAxis[s.unit] = 'right'
        selectedUnits.push(s.unit)
      } else if (!selectedUnits.includes(s.unit)) {
        unitToAxis[s.unit] = 'left'
      }
    }
  })

  const leftUnit = selectedUnits[0] ?? ''
  const rightUnit = selectedUnits[1] ?? ''

  const toggle = (id: number) => {
    if (selected.includes(id)) {
      setSelected((s) => s.filter((x) => x !== id))
      return
    }
    const tag = tags.find((t) => t.id === id)
    if (!tag) return
    const existingUnits = [...new Set(
      tags.filter((t) => selected.includes(t.id)).map((t) => t.unit)
    )]
    if (!existingUnits.includes(tag.unit) && existingUnits.length >= 2) {
      setToast('Maksimum 2 farklı birim. Önce mevcut bir birimi kaldır.')
      setTimeout(() => setToast(''), 4000)
      return
    }
    setSelected((s) => [...s, id])
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

  const hasRightAxis = selectedUnits.length === 2

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Trend Grafik</h1>
        <div className="flex gap-2">
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
        </div>
      </div>

      <div className="flex gap-4">
        {/* Tag selector */}
        <div className="w-52 bg-gray-900 border border-gray-800 rounded-xl p-3 flex-shrink-0 space-y-2">
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
              const colorIdx = tags.findIndex((x) => x.id === t.id)
              return (
                <button
                  key={t.id}
                  onClick={() => toggle(t.id)}
                  className={`w-full text-left px-2 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                    selected.includes(t.id)
                      ? 'bg-blue-600/20 text-blue-300'
                      : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                  }`}
                >
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: COLORS[colorIdx % COLORS.length] }}
                  />
                  <span className="truncate">{t.name}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Chart */}
        <div className="flex-1 bg-gray-900 border border-gray-800 rounded-xl p-4">
          {selected.length === 0 ? (
            <div className="h-80 flex items-center justify-center text-gray-500 text-sm">
              Sol panelden tag seçin
            </div>
          ) : isLoading ? (
            <div className="h-80 flex items-center justify-center text-gray-500 text-sm">
              Yükleniyor...
            </div>
          ) : chartData.length === 0 ? (
            <div className="h-80 flex items-center justify-center text-gray-500 text-sm">
              Bu aralıkta veri yok.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={380}>
              <LineChart data={chartData} margin={{ top: 4, right: hasRightAxis ? 60 : 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#9ca3af' }} interval="preserveStartEnd" />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  width={55}
                  label={leftUnit ? { value: leftUnit, angle: -90, position: 'insideLeft', fill: '#6b7280', fontSize: 11, offset: 10 } : undefined}
                />
                {hasRightAxis && (
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    width={55}
                    label={rightUnit ? { value: rightUnit, angle: 90, position: 'insideRight', fill: '#6b7280', fontSize: 11, offset: 10 } : undefined}
                  />
                )}
                <Tooltip
                  contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#e5e7eb', fontSize: 12 }}
                  itemStyle={{ fontSize: 12 }}
                  formatter={(value, name) => {
                    const s = series.find((x) => x.name === name)
                    return [`${value} ${s?.unit ?? ''}`, name]
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
                {series.map((s, i) => (
                  <Line
                    key={s.tag_id}
                    type="monotone"
                    dataKey={s.name}
                    stroke={COLORS[i % COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                    yAxisId={unitToAxis[s.unit] ?? 'left'}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}
