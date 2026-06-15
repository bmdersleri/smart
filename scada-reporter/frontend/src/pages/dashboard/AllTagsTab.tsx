import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { useEffect, useMemo, useRef, useState } from 'react'
import { addWatchlist, getDashboardDevices, getDashboardTags } from '../../api/client'
import type { DashboardTag } from '../../api/client'

function QualityDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-green-400' : 'bg-red-400'}`} />
}

function formatValue(item: DashboardTag): string {
  if (item.value === null) return '—'
  return `${item.value.toFixed(2)}${item.unit ? ` ${item.unit}` : ''}`
}

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return format(parseISO(ts + 'Z'), 'HH:mm:ss')
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function AllTagsTab({ active }: { active: boolean }) {
  const qc = useQueryClient()
  const [device, setDevice] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [quality, setQuality] = useState<'' | 'good' | 'bad' | 'stale'>('')
  const [daily, setDaily] = useState<boolean | undefined>(undefined)
  const [page, setPage] = useState(1)
  const search = useDebounce(searchInput, 300)
  const pinnedIds = useRef<Set<number>>(new Set())

  // Reset to page 1 on filter change
  useEffect(() => { setPage(1) }, [device, search, quality, daily])

  const params = useMemo(() => ({
    ...(device ? { device } : {}),
    ...(search ? { search } : {}),
    ...(quality ? { quality } : {}),
    ...(daily !== undefined ? { daily } : {}),
    page,
    page_size: 50,
  }), [device, search, quality, daily, page])

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-tags', params],
    queryFn: () => getDashboardTags(params).then((r) => r.data),
    refetchInterval: 5000,
    enabled: active,
  })

  const { data: devices = [] } = useQuery({
    queryKey: ['dashboard-devices'],
    queryFn: () => getDashboardDevices().then((r) => r.data),
    staleTime: 60000,
    enabled: active,
  })

  const pin = useMutation({
    mutationFn: (tag_id: number) => addWatchlist(tag_id),
    onSuccess: (_data, tag_id) => {
      pinnedIds.current.add(tag_id)
      qc.invalidateQueries({ queryKey: ['watchlist'] })
      qc.invalidateQueries({ queryKey: ['dashboard-tags'] })
    },
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 items-center bg-gray-900 border border-gray-800 rounded-xl p-3">
        <select
          value={device}
          onChange={(e) => setDevice(e.target.value)}
          className="bg-gray-800 text-gray-300 text-sm rounded-lg px-3 py-1.5 border border-gray-700 focus:outline-none focus:border-cyan-500"
        >
          <option value="">Tüm Cihazlar</option>
          {devices.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>

        <input
          type="text"
          placeholder="Tag ara..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="bg-gray-800 text-gray-300 text-sm rounded-lg px-3 py-1.5 border border-gray-700 focus:outline-none focus:border-cyan-500 min-w-[160px]"
        />

        <select
          value={quality}
          onChange={(e) => setQuality(e.target.value as '' | 'good' | 'bad' | 'stale')}
          className="bg-gray-800 text-gray-300 text-sm rounded-lg px-3 py-1.5 border border-gray-700 focus:outline-none focus:border-cyan-500"
        >
          <option value="">Tüm Kalite</option>
          <option value="good">İyi</option>
          <option value="bad">Hatalı</option>
          <option value="stale">Bayat</option>
        </select>

        <label className="flex items-center gap-1.5 text-sm text-gray-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={daily === true}
            onChange={(e) => setDaily(e.target.checked ? true : undefined)}
            className="accent-cyan-500"
          />
          Günlük Takip
        </label>

        <span className="ml-auto text-xs text-gray-500">{total.toLocaleString('tr')} tag</span>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Yükleniyor...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 bg-gray-900 rounded-xl border border-gray-800">
          <p className="text-gray-400">Eşleşen tag bulunamadı.</p>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-2 text-left">Tag</th>
                <th className="px-4 py-2 text-left">Cihaz</th>
                <th className="px-4 py-2 text-right">Değer</th>
                <th className="px-4 py-2 text-right">Saat</th>
                <th className="px-4 py-2 text-center">Kalite</th>
                <th className="px-4 py-2 text-center">Pin</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const pinned = pinnedIds.current.has(item.tag_id)
                return (
                  <tr key={item.tag_id} className="border-t border-gray-800 hover:bg-gray-800/40 transition-colors">
                    <td className="px-4 py-2.5 text-sm text-white font-medium">{item.name}</td>
                    <td className="px-4 py-2.5 text-sm text-gray-400">{item.device || '—'}</td>
                    <td className="px-4 py-2.5 text-sm text-right font-mono text-cyan-300">{formatValue(item)}</td>
                    <td className="px-4 py-2.5 text-sm text-gray-400 text-right">{formatTs(item.timestamp)}</td>
                    <td className="px-4 py-2.5 text-center"><QualityDot ok={item.quality_ok} /></td>
                    <td className="px-4 py-2.5 text-center">
                      <button
                        onClick={() => pin.mutate(item.tag_id)}
                        disabled={pinned}
                        title={pinned ? 'Pinlendi' : 'Watchlist\'e ekle'}
                        className={`text-base leading-none transition-colors ${pinned ? 'text-yellow-400 cursor-default' : 'text-gray-600 hover:text-yellow-400'}`}
                      >
                        {pinned ? '★' : '☆'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-lg border border-gray-700 disabled:opacity-40 hover:bg-gray-700 transition-colors"
          >
            ← Önceki
          </button>
          <span className="text-sm text-gray-400">Sayfa {page} / {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-lg border border-gray-700 disabled:opacity-40 hover:bg-gray-700 transition-colors"
          >
            Sonraki →
          </button>
        </div>
      )}
    </div>
  )
}
