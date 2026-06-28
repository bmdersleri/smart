import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import { getWatchlist, removeWatchlist, listWatchlistGroups, addTagToGroup, removeTagFromGroup } from '../../api/client'
import { parseUtc } from '../../utils/time'
import type { WatchlistItem } from '../../api/client'
import { useLatestStream } from '../../hooks/useLatestStream'
import { useSortable } from '../../hooks/useSortable'
import SortHeader from '../../components/SortHeader'
import TagDescriptionCell from '../../components/TagDescriptionCell'
import WatchlistGroups from './WatchlistGroups'
import { tagInGroup } from '../../utils/watchlistGroups'

function QualityDot({ ok }: { ok: boolean }) {
  return (
    <span className="relative flex h-2 w-2 mx-auto">
      {!ok && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>}
      <span className={`relative inline-flex rounded-full h-2 w-2 ${ok ? 'bg-green-400' : 'bg-red-500 animate-pulse'}`}></span>
    </span>
  )
}

function FlipCell({ value, className }: { value: string; className?: string }) {
  return (
    <span className="inline-block overflow-hidden align-bottom" style={{ height: '1.25rem', lineHeight: '1.25rem' }}>
      <span
        key={value}
        className={`block animate-flip-in ${className ?? ''}`}
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
    staleTime: 60000, // WebSocket handles live updates
    enabled: active,
  })

  useLatestStream(
    items.map((i) => i.tag_id),
    (data) => {
      qc.setQueryData(['watchlist'], (old: WatchlistItem[] | undefined) => {
        if (!old) return old
        let changed = false
        const next = old.map((it) => {
          const lv = data[it.tag_id]
          if (!lv) return it
          changed = true
          return { ...it, value: lv.v, timestamp: lv.t, quality_ok: lv.q === 192 }
        })
        return changed ? next : old
      })
    },
    active
  )

  const { sorted: rows, sort, toggle } = useSortable(items)

  const { data: wg } = useQuery({
    queryKey: ['watchlist-groups'],
    queryFn: () => listWatchlistGroups().then((r) => r.data),
  })

  const toggleGroup = useMutation({
    mutationFn: ({ gid, tagId, on }: { gid: number; tagId: number; on: boolean }) =>
      on ? removeTagFromGroup(gid, tagId) : addTagToGroup(gid, tagId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist-groups'] }),
  })

  const unpin = useMutation({
    mutationFn: (tag_id: number) => removeWatchlist(tag_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })

  if (isLoading) return <div className="text-center py-16 text-gray-500">{t('common:loading')}</div>

  return (
    <>
    <WatchlistGroups />
    {items.length === 0 ? (
      <div className="text-center py-16 bg-surface-raised/80 backdrop-blur-md rounded-xl border border-edge/50 shadow-xl">
        <p className="text-gray-400">{t('watchlist_empty')}</p>
        <p className="text-gray-500 text-sm mt-1">{t('watchlist_empty_hint')}</p>
      </div>
    ) : (
    <div className="bg-surface-raised/80 backdrop-blur-md border border-edge/50 rounded-xl overflow-hidden shadow-xl">
      <table className="w-full">
        <thead>
          <tr className="text-xs text-gray-500 uppercase tracking-wide">
            <SortHeader label={t('col_device')} sortKey="device" sort={sort} onToggle={toggle} />
            <SortHeader label={t('col_tag')} sortKey="name" sort={sort} onToggle={toggle} />
            <SortHeader label={t('col_value')} sortKey="value" sort={sort} onToggle={toggle} align="right" />
            <SortHeader label={t('col_time')} sortKey="timestamp" sort={sort} onToggle={toggle} align="right" />
            <SortHeader label={t('col_quality')} sortKey="quality_ok" sort={sort} onToggle={toggle} align="center" />
            <th className="px-4 py-2 text-start">{t('col_groups')}</th>
            <th className="px-4 py-2 text-center">{t('col_pin')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => (
            <tr key={item.tag_id} className="border-t border-edge hover:bg-white/5/40 transition-colors">
              <td className="px-4 py-3 text-sm text-gray-400">{item.device || '—'}</td>
              <td className="px-4 py-3 text-sm text-white font-medium">
                <TagDescriptionCell name={item.name} description={item.description} />
              </td>
              <td className="px-4 py-3 text-sm text-end font-mono">
                <FlipCell value={formatValue(item)} className="text-cyan-300" />
              </td>
              <td className="px-4 py-3 text-sm text-end">
                <FlipCell value={formatTs(item.timestamp)} className="text-gray-400" />
              </td>
              <td className="px-4 py-3 text-center"><QualityDot ok={item.quality_ok} /></td>
              <td className="px-4 py-3">
                <div className="flex gap-1 flex-wrap">
                  {(wg?.groups ?? []).map((g) => {
                    const on = tagInGroup(g, item.tag_id)
                    return (
                      <button
                        key={g.id}
                        onClick={() => toggleGroup.mutate({ gid: g.id, tagId: item.tag_id, on })}
                        className={`text-[10px] px-1.5 py-0.5 rounded-full border ${on ? 'bg-cyan-900/50 border-cyan-600 text-cyan-300' : 'border-edge-strong text-gray-500'}`}
                      >
                        {g.name}
                      </button>
                    )
                  })}
                </div>
              </td>
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
