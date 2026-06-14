import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTags, getTrend } from '../api/client'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { format, parseISO } from 'date-fns'

const COLORS = ['#60a5fa', '#34d399', '#f59e0b', '#f87171', '#a78bfa', '#fb923c']

const HOURS = [{ v: 1, l: 'Son 1 saat' }, { v: 6, l: 'Son 6 saat' }, { v: 24, l: 'Son 24 saat' }, { v: 168, l: 'Son 7 gün' }]

export default function Trend() {
  const [selected, setSelected] = useState<number[]>([])
  const [hours, setHours] = useState(24)

  const { data: tags = [] } = useQuery({ queryKey: ['tags'], queryFn: () => getTags().then((r) => r.data) })
  const { data: series = [], isLoading } = useQuery({
    queryKey: ['trend', selected, hours],
    queryFn: () => selected.length ? getTrend(selected, hours).then((r) => r.data) : Promise.resolve([]),
    enabled: selected.length > 0,
    refetchInterval: 30000,
  })

  // Merge all series into one timeline
  const timeline: Record<string, Record<string, number | string>> = {}
  series.forEach((s) => {
    s.data.forEach(({ t, v }) => {
      const key = format(parseISO(t), 'dd.MM HH:mm')
      timeline[key] ??= { t: key }
      timeline[key][s.name] = v
    })
  })
  const chartData = Object.values(timeline).sort((a, b) => String(a.t).localeCompare(String(b.t)))

  const toggle = (id: number) =>
    setSelected((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id])

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Trend Grafik</h1>
        <div className="flex gap-2">
          {HOURS.map(({ v, l }) => (
            <button
              key={v} onClick={() => setHours(v)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${hours === v ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-4">
        {/* Tag seçici */}
        <div className="w-52 bg-gray-900 border border-gray-800 rounded-xl p-3 space-y-1 flex-shrink-0">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-2 px-1">Tag Seç</p>
          {tags.length === 0 && <p className="text-gray-500 text-xs px-1">Tag bulunamadı.</p>}
          {tags.map((t, i) => (
            <button
              key={t.id} onClick={() => toggle(t.id)}
              className={`w-full text-left px-2 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                selected.includes(t.id) ? 'bg-blue-600/20 text-blue-300' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`}
            >
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
              <span className="truncate">{t.name}</span>
            </button>
          ))}
        </div>

        {/* Grafik */}
        <div className="flex-1 bg-gray-900 border border-gray-800 rounded-xl p-4">
          {selected.length === 0 ? (
            <div className="h-80 flex items-center justify-center text-gray-500 text-sm">
              Sol panelden tag seçin
            </div>
          ) : isLoading ? (
            <div className="h-80 flex items-center justify-center text-gray-500 text-sm">Yükleniyor...</div>
          ) : chartData.length === 0 ? (
            <div className="h-80 flex items-center justify-center text-gray-500 text-sm">Bu aralıkta veri yok.</div>
          ) : (
            <ResponsiveContainer width="100%" height={380}>
              <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#9ca3af' }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} width={50} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#e5e7eb', fontSize: 12 }}
                  itemStyle={{ fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
                {series.map((s, i) => (
                  <Line
                    key={s.tag_id} type="monotone" dataKey={s.name}
                    stroke={COLORS[i % COLORS.length]} strokeWidth={2}
                    dot={false} connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  )
}
