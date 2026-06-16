import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { format, parseISO } from 'date-fns'
import { useEffect, useMemo, useState } from 'react'
import { addWatchlist, getDashboardDevices, getDashboardTags } from '../../api/client'
import type { DashboardTag } from '../../api/client'
import { useSortable } from '../../hooks/useSortable'
import SortHeader from '../../components/SortHeader'

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
  const { t, i18n } = useTranslation(['dashboard', 'common'])
  const qc = useQueryClient()
  const [device, setDevice] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [quality, setQuality] = useState<'' | 'good' | 'bad' | 'stale'>('')
  const [daily, setDaily] = useState<boolean | undefined>(undefined)
  const [page, setPage] = useState(1)
  const search = useDebounce(searchInput, 300)
  const [pinnedIds, setPinnedIds] = useState<Set<number>>(new Set())

  // Reset to page 1 on filter change
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPage(1)
  }, [device, search, quality, daily])

  const params = useMemo(() => ({
    ...(device ? { device } : {}),
    ...(search ? { search } : {}),
    ...(quality ? { quality } : {}),
    ...(daily !== undefined ? { daily } : {}),
    page,
    page_size: 50,
  }), [device, search, quality, daily, page])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['dashboard-tags', params],
    queryFn: () => getDashboardTags(params).then((r) => r.data),
    refetchInterval: 5000,
    enabled: active,
    retry: 1,
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
      setPinnedIds((prev) => new Set(prev).add(tag_id))
      qc.invalidateQueries({ queryKey: ['watchlist'] })
      qc.invalidateQueries({ queryKey: ['dashboard-tags'] })
    },
  })

  const pageItems = data?.items ?? []
  const { sorted: items, sort, toggle } = useSortable(pageItems)
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
          <option value="">{t('filter_all_devices')}</option>
          {devices.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>

        <input
          type="text"
          placeholder={t('search_placeholder')}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="bg-gray-800 text-gray-300 text-sm rounded-lg px-3 py-1.5 border border-gray-700 focus:outline-none focus:border-cyan-500 min-w-[160px]"
        />

        <select
          value={quality}
          onChange={(e) => setQuality(e.target.value as '' | 'good' | 'bad' | 'stale')}
          className="bg-gray-800 text-gray-300 text-sm rounded-lg px-3 py-1.5 border border-gray-700 focus:outline-none focus:border-cyan-500"
        >
          <option value="">{t('filter_all_quality')}</option>
          <option value="good">{t('quality_good')}</option>
          <option value="bad">{t('quality_bad')}</option>
          <option value="stale">{t('quality_stale')}</option>
        </select>

        <label className="flex items-center gap-1.5 text-sm text-gray-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={daily === true}
            onChange={(e) => setDaily(e.target.checked ? true : undefined)}
            className="accent-cyan-500"
          />
          {t('daily_tracking')}
        </label>

        <span className="ml-auto text-xs text-gray-500">{t('tag_count', { value: total.toLocaleString(i18n.language) })}</span>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="text-center py-16 text-gray-500">{t('common:loading')}</div>
      ) : isError ? (
        <div className="text-center py-16 bg-gray-900 rounded-xl border border-red-900">
          <p className="text-red-400 font-medium">{t('load_failed')}</p>
          <p className="text-gray-500 text-sm mt-1">{String(error)}</p>
          <p className="text-gray-600 text-xs mt-2">{t('backend_hint')}</p>
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 bg-gray-900 rounded-xl border border-gray-800">
          <p className="text-gray-400">{t('no_tags_found')}</p>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wide">
                <SortHeader label={t('col_tag')} sortKey="name" sort={sort} onToggle={toggle} />
                <SortHeader label={t('col_device')} sortKey="device" sort={sort} onToggle={toggle} />
                <SortHeader label={t('col_value')} sortKey="value" sort={sort} onToggle={toggle} align="right" />
                <SortHeader label={t('col_time')} sortKey="timestamp" sort={sort} onToggle={toggle} align="right" />
                <SortHeader label={t('col_quality')} sortKey="quality_ok" sort={sort} onToggle={toggle} align="center" />
                <th className="px-4 py-2 text-center">{t('col_pin')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const pinned = pinnedIds.has(item.tag_id)
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
                        title={pinned ? t('pinned') : t('add_to_watchlist')}
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
            {t('prev')}
          </button>
          <span className="text-sm text-gray-400">{t('page_of', { page, total: totalPages })}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-lg border border-gray-700 disabled:opacity-40 hover:bg-gray-700 transition-colors"
          >
            {t('next')}
          </button>
        </div>
      )}
    </div>
  )
}
