import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  listWatchlistGroups, createWatchlistGroup, renameWatchlistGroup,
  deleteWatchlistGroup, syncGrafana,
} from '../../api/client'

const GRAFANA = (import.meta.env.VITE_GRAFANA_URL as string) ?? 'http://localhost:3000'

export default function WatchlistGroups() {
  const { t } = useTranslation('watchlistGroups')
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')
  const [msg, setMsg] = useState('')
  const { data } = useQuery({ queryKey: ['watchlist-groups'], queryFn: () => listWatchlistGroups().then((r) => r.data) })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['watchlist-groups'] })
  const create = useMutation({ mutationFn: () => createWatchlistGroup(newName), onSuccess: () => { setNewName(''); invalidate() } })
  const del = useMutation({ mutationFn: (id: number) => deleteWatchlistGroup(id), onSuccess: invalidate })
  const rename = useMutation({ mutationFn: (v: { id: number; name: string }) => renameWatchlistGroup(v.id, v.name), onSuccess: invalidate })
  const sync = useMutation({
    mutationFn: () => syncGrafana(),
    onSuccess: (r) => setMsg(t('synced', { written: r.data.written, deleted: r.data.deleted })),
    onError: () => setMsg(t('sync_failed')),
  })

  return (
    <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">{t('title')}</h2>
        <div className="flex items-center gap-2">
          <a href={`${GRAFANA}/d/scada-watchlist-groups`} target="_blank" rel="noreferrer"
             className="text-xs text-cyan-400 hover:underline">{t('open_dashboard')}</a>
          <button onClick={() => sync.mutate()} disabled={sync.isPending}
                  className="text-xs px-2 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
            {t('sync_grafana')}
          </button>
        </div>
      </div>
      {msg && <p className="text-xs text-gray-400">{msg}</p>}
      <div className="flex gap-2">
        <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder={t('group_name')}
               className="flex-1 bg-surface-sunken border border-edge-strong rounded px-2 py-1 text-sm text-white" />
        <button onClick={() => newName.trim() && create.mutate()}
                className="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-white">{t('new_group')}</button>
      </div>
      <ul className="space-y-1">
        {(data?.groups ?? []).map((g) => (
          <li key={g.id} className="flex items-center justify-between text-sm text-gray-200 px-2 py-1 rounded bg-surface">
            <span>{g.name} <span className="text-gray-500">({g.tag_count})</span></span>
            <span className="flex gap-2">
              <button onClick={() => { const n = prompt(t('rename'), g.name); if (n) rename.mutate({ id: g.id, name: n }) }}
                      className="text-xs text-gray-400 hover:text-white">{t('rename')}</button>
              <button onClick={() => del.mutate(g.id)} className="text-xs text-red-400 hover:text-red-300">{t('delete')}</button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
