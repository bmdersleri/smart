import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import { getWatchlist, removeWatchlist } from '../../api/client'
import { parseUtc } from '../../utils/time'
import type { WatchlistItem } from '../../api/client'
import { useLatestStream } from '../../hooks/useLatestStream'
import { useSortable } from '../../hooks/useSortable'
import SortHeader from '../../components/SortHeader'
import WatchlistGroups from './WatchlistGroups'

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
  // parseUtc handles both offset-aware (REST/SSE) and legacy offset-less strings.
  return format(parseUtc(ts), 'HH:mm:ss')
}

export default function WatchlistTab({ active }: { active: boolean }) {
  const { t } = useTranslation(['dashboard', 'common'])
  const qc = useQueryClient()
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => getWatchlist().then((r) => r.data),
    // SSE push carries live values; REST is only a fallback for structure (pin/unpin)
    refetchInterval: 30000,
    enabled: active,
  })

  const live = useLatestStream(
    items.map((i) => i.tag_id),
    active
  )

  // Bind live SSE values onto watchlist rows
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

  if (isLoading) return <div className="text-center py-16 text-gray-500">{t('common:loading')}</div>

  return (
    <>
    <WatchlistGroups />
    {items.length === 0 ? (
      <div className="text-center py-16 bg-gray-900 rounded-xl border border-gray-800">
        <p className="text-gray-400">{t('watchlist_empty')}</p>
        <p className="text-gray-500 text-sm mt-1">{t('watchlist_empty_hint')}</p>
      </div>
    ) : (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="text-xs text-gray-500 uppercase tracking-wide">
            <SortHeader label={t('col_device')} sortKey="device" sort={sort} onToggle={toggle} />
            <SortHeader label={t('col_tag')} sortKey="name" sort={sort} onToggle={toggle} />
            <SortHeader label={t('col_value')} sortKey="value" sort={sort} onToggle={toggle} align="right" />
            <SortHeader label={t('col_time')} sortKey="timestamp" sort={sort} onToggle={toggle} align="right" />
            <SortHeader label={t('col_quality')} sortKey="quality_ok" sort={sort} onToggle={toggle} align="center" />
            <th className="px-4 py-2 text-center">{t('col_pin')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => (
            <tr key={item.tag_id} className="border-t border-gray-800 hover:bg-gray-800/40 transition-colors">
              <td className="px-4 py-3 text-sm text-gray-400">{item.device || '—'}</td>
              <td className="px-4 py-3 text-sm text-white font-medium">{item.name}</td>
              <td className="px-4 py-3 text-sm text-end font-mono">
                <FlipCell value={formatValue(item)} className="text-cyan-300" />
              </td>
              <td className="px-4 py-3 text-sm text-end">
                <FlipCell value={formatTs(item.timestamp)} className="text-gray-400" />
              </td>
              <td className="px-4 py-3 text-center"><QualityDot ok={item.quality_ok} /></td>
              <td className="px-4 py-3 text-center">
                <button
                  onClick={() => unpin.mutate(item.tag_id)}
                  title={t('unpin')}
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
    )}
    </>
  )
}
