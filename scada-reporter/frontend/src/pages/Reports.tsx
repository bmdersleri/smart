import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTags, generateReport, getReportHistory, downloadHistoryReport } from '../api/client'
import type { ReportHistoryEntry } from '../api/client'
import { format, subDays, startOfDay, endOfDay, parseISO } from 'date-fns'
import { tr } from 'date-fns/locale'

const fmt = (d: Date) => format(d, "yyyy-MM-dd'T'HH:mm")

const PRESETS = [
  { label: 'Bugün', start: () => startOfDay(new Date()), end: () => new Date() },
  { label: 'Dün', start: () => startOfDay(subDays(new Date(), 1)), end: () => endOfDay(subDays(new Date(), 1)) },
  { label: 'Son 7 Gün', start: () => startOfDay(subDays(new Date(), 7)), end: () => new Date() },
  { label: 'Son 30 Gün', start: () => startOfDay(subDays(new Date(), 30)), end: () => new Date() },
]

function HistoryRow({ entry }: { entry: ReportHistoryEntry }) {
  const [downloading, setDownloading] = useState(false)

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

  const dateStr = format(parseISO(entry.created_at + 'Z'), 'dd.MM.yyyy HH:mm', { locale: tr })
  const tagCount = entry.tag_ids.length
  const rangeStart = format(parseISO(entry.start + 'Z'), 'dd.MM', { locale: tr })
  const rangeEnd = format(parseISO(entry.end + 'Z'), 'dd.MM', { locale: tr })

  return (
    <div className="flex items-center justify-between py-2.5 border-t border-gray-800">
      <div className="flex items-center gap-3">
        <span className="text-gray-500 text-sm">📄</span>
        <div>
          <span className="text-sm text-gray-300">{dateStr}</span>
          <span className="text-gray-600 mx-2">·</span>
          <span className="text-xs text-gray-500">{tagCount} tag</span>
          <span className="text-gray-600 mx-2">·</span>
          <span className="text-xs text-gray-500">{rangeStart}–{rangeEnd}</span>
          <span className="text-gray-600 mx-2">·</span>
          <span className="text-xs text-gray-500 uppercase">{entry.format}</span>
        </div>
      </div>
      <button
        onClick={reDownload}
        disabled={downloading}
        className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50 transition-colors"
      >
        {downloading ? '...' : '↓ İndir'}
      </button>
    </div>
  )
}

export default function Reports() {
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

  const toggleTag = (id: number) =>
    setSelectedTags((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id])

  const selectPreset = (p: typeof PRESETS[0]) => {
    setStart(fmt(p.start()))
    setEnd(fmt(p.end()))
  }

  // Group tags by device
  const groups = tags.reduce<Record<string, typeof tags>>((acc, t) => {
    const key = t.device || 'Diğer';
    (acc[key] ??= []).push(t)
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
    if (!selectedTags.length) { setError('En az bir tag seçin'); return }
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
      setError('Rapor oluşturulamadı.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <h1 className="text-xl font-bold text-white">Rapor Oluştur</h1>

      {/* Grouped tag selection */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-gray-300">Tag Seçimi</p>
          <span className="text-xs text-gray-500">{selectedTags.length} tag seçili</span>
        </div>
        {Object.entries(groups).map(([device, groupTags]) => {
          const allSelected = groupTags.every((t) => selectedTags.includes(t.id))
          return (
            <div key={device}>
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{device}</span>
                <button
                  onClick={() => toggleGroup(groupTags)}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  {allSelected ? 'Tümünü Kaldır' : 'Tümünü Seç'}
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {groupTags.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => toggleTag(t.id)}
                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                      selectedTags.includes(t.id)
                        ? 'bg-blue-600/20 border-blue-500 text-blue-300'
                        : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
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
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
        <p className="text-sm font-medium text-gray-300">Zaman Aralığı</p>
        <div className="flex gap-2 flex-wrap">
          {PRESETS.map((p) => (
            <button key={p.label} onClick={() => selectPreset(p)}
              className="px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors">
              {p.label}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Başlangıç</label>
            <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Bitiş</label>
            <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      </div>

      {/* Grouping */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
        <p className="text-sm font-medium text-gray-300">Gruplama</p>
        <div className="flex gap-2">
          {[{ v: 'hourly', l: 'Saatlik' }, { v: 'daily', l: 'Günlük' }].map(({ v, l }) => (
            <button key={v} onClick={() => setIntervalVal(v)}
              className={`px-4 py-2 text-sm rounded-lg border transition-colors ${
                interval === v
                  ? 'bg-blue-600/20 border-blue-500 text-blue-300'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
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
          className="flex items-center gap-2 px-5 py-2.5 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white rounded-lg font-medium text-sm transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          {loading ? 'Hazırlanıyor...' : 'Excel İndir'}
        </button>
        <button onClick={() => download('json')} disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded-lg font-medium text-sm border border-gray-700 transition-colors">
          JSON
        </button>
      </div>

      {/* Report history */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <p className="text-sm font-medium text-gray-300 mb-1">Son Raporlar</p>
        {history.length === 0 ? (
          <p className="text-gray-500 text-sm py-4">Henüz rapor oluşturulmadı.</p>
        ) : (
          history.map((entry) => <HistoryRow key={entry.id} entry={entry} />)
        )}
      </div>
    </div>
  )
}
