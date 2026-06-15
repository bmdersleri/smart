import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { getWatchlist, removeWatchlist } from '../../api/client'
import type { WatchlistItem } from '../../api/client'

function QualityDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-green-400' : 'bg-red-400'}`} />
}

function formatValue(item: WatchlistItem): string {
  if (item.value === null) return '—'
  return `${item.value.toFixed(2)}${item.unit ? ` ${item.unit}` : ''}`
}

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return format(parseISO(ts + 'Z'), 'HH:mm:ss')
}

export default function WatchlistTab({ active }: { active: boolean }) {
  const qc = useQueryClient()
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => getWatchlist().then((r) => r.data),
    refetchInterval: 5000,
    enabled: active,
  })

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
            <th className="px-4 py-2 text-left">Cihaz</th>
            <th className="px-4 py-2 text-left">Tag</th>
            <th className="px-4 py-2 text-right">Değer</th>
            <th className="px-4 py-2 text-right">Saat</th>
            <th className="px-4 py-2 text-center">Kalite</th>
            <th className="px-4 py-2 text-center">Pin</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.tag_id} className="border-t border-gray-800 hover:bg-gray-800/40 transition-colors">
              <td className="px-4 py-3 text-sm text-gray-400">{item.device || '—'}</td>
              <td className="px-4 py-3 text-sm text-white font-medium">{item.name}</td>
              <td className="px-4 py-3 text-sm text-right font-mono text-cyan-300">{formatValue(item)}</td>
              <td className="px-4 py-3 text-sm text-gray-400 text-right">{formatTs(item.timestamp)}</td>
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
