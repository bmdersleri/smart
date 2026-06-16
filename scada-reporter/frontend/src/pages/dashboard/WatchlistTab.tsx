import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { getWatchlist, removeWatchlist } from '../../api/client'
import type { WatchlistItem } from '../../api/client'
import { useLatestStream } from '../../hooks/useLatestStream'
import { useSortable } from '../../hooks/useSortable'
import SortHeader from '../../components/SortHeader'

function QualityDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-green-400' : 'bg-red-400'}`} />
}

function FlipCell({ value, className }: { value: string; className?: string }) {
  return (
    <span className="inline-block overflow-hidden align-bottom" style={{ height: '1.25rem', lineHeight: '1.25rem' }}>
      <span
        key={value}
        className={`block animate-[flipIn_0.5s_linear] ${className ?? ''}`}
      >
        {value}
      </span>
    </span>
  )
}

function formatValue(item: WatchlistItem): string {
  if (item.value === null) return '—'
  return `${item.value.toFixed(2)}${item.unit ? ` ${item.unit}` : ''}`
}

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  // REST naive (tz'siz) ts -> 'Z' ekle; SSE ts zaten tz taşır (+00:00/Z)
  const iso = ts.endsWith('Z') || ts.includes('+') ? ts : ts + 'Z'
  return format(parseISO(iso), 'HH:mm:ss')
}

export default function WatchlistTab({ active }: { active: boolean }) {
  const qc = useQueryClient()
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => getWatchlist().then((r) => r.data),
    // SSE push canlı değerleri taşır; REST sadece yapı (pin/unpin) için fallback
    refetchInterval: 30000,
    enabled: active,
  })

  const live = useLatestStream(
    items.map((i) => i.tag_id),
    active
  )

  // Canlı SSE değerlerini watchlist satırlarına bindir
  const merged: WatchlistItem[] = items.map((it) => {
    const lv = live[it.tag_id]
    if (!lv) return it
    return { ...it, value: lv.v, timestamp: lv.t, quality_ok: lv.q === 192 }
  })
  const { sorted: rows, sort, toggle } = useSortable(merged)

  const unpin = useMutation({
    mutationFn: (tag_id: number) => removeWatchlist(tag_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })

  if (isLoading) return <div className="text-center py-16 text-gray-500">Yükleniyor...</div>

  if (items.length === 0) {
    return (
      <div className="text-center py-16 bg-gray-900 rounded-xl border border-gray-800">
        <p className="text-gray-400">İzleme listesi boş.</p>
        <p className="text-gray-500 text-sm mt-1">Tüm Tag'ler sekmesinden ★ ile tag pinleyin.</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="text-xs text-gray-500 uppercase tracking-wide">
            <SortHeader label="Cihaz" sortKey="device" sort={sort} onToggle={toggle} />
            <SortHeader label="Tag" sortKey="name" sort={sort} onToggle={toggle} />
            <SortHeader label="Değer" sortKey="value" sort={sort} onToggle={toggle} align="right" />
            <SortHeader label="Saat" sortKey="timestamp" sort={sort} onToggle={toggle} align="right" />
            <SortHeader label="Kalite" sortKey="quality_ok" sort={sort} onToggle={toggle} align="center" />
            <th className="px-4 py-2 text-center">Pin</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => (
            <tr key={item.tag_id} className="border-t border-gray-800 hover:bg-gray-800/40 transition-colors">
              <td className="px-4 py-3 text-sm text-gray-400">{item.device || '—'}</td>
              <td className="px-4 py-3 text-sm text-white font-medium">{item.name}</td>
              <td className="px-4 py-3 text-sm text-right font-mono">
                <FlipCell value={formatValue(item)} className="text-cyan-300" />
              </td>
              <td className="px-4 py-3 text-sm text-right">
                <FlipCell value={formatTs(item.timestamp)} className="text-gray-400" />
              </td>
              <td className="px-4 py-3 text-center"><QualityDot ok={item.quality_ok} /></td>
              <td className="px-4 py-3 text-center">
                <button
                  onClick={() => unpin.mutate(item.tag_id)}
                  title="Pin'i kaldır"
                  className="text-yellow-400 hover:text-yellow-200 text-base leading-none transition-colors"
                >
                  ★
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
