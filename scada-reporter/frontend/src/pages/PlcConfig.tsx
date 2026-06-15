import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { createPlc, deletePlc, listPlcs, updatePlc } from '../api/client'
import type { PlcEntry } from '../api/client'

function ConnBadge({ connected }: { connected: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${
        connected ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
      {connected ? 'Bağlı' : 'Bağlantı Yok'}
    </span>
  )
}

function EditRow({
  plc,
  onSave,
  onCancel,
}: {
  plc: PlcEntry
  onSave: (ip: string, rack: number, slot: number) => void
  onCancel: () => void
}) {
  const [ip, setIp] = useState(plc.ip)
  const [rack, setRack] = useState(plc.rack)
  const [slot, setSlot] = useState(plc.slot)

  return (
    <tr className="border-t border-gray-800 bg-gray-800/60">
      <td className="px-4 py-2.5 text-sm text-white font-medium">{plc.name}</td>
      <td className="px-4 py-2.5">
        <input
          value={ip}
          onChange={(e) => setIp(e.target.value)}
          placeholder="192.168.x.x"
          className="bg-gray-700 text-gray-100 text-sm rounded px-2 py-1 border border-cyan-600 focus:outline-none w-36 font-mono"
        />
      </td>
      <td className="px-4 py-2.5">
        <input
          type="number"
          value={rack}
          onChange={(e) => setRack(Number(e.target.value))}
          className="bg-gray-700 text-gray-100 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none w-16"
          min={0}
          max={7}
        />
      </td>
      <td className="px-4 py-2.5">
        <input
          type="number"
          value={slot}
          onChange={(e) => setSlot(Number(e.target.value))}
          className="bg-gray-700 text-gray-100 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none w-16"
          min={0}
          max={31}
        />
      </td>
      <td className="px-4 py-2.5 text-sm text-gray-400">{plc.tag_count.toLocaleString('tr')}</td>
      <td className="px-4 py-2.5"><ConnBadge connected={plc.connected} /></td>
      <td className="px-4 py-2.5 text-right">
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={() => onSave(ip, rack, slot)}
            className="px-3 py-1 text-xs bg-cyan-600 hover:bg-cyan-500 text-white rounded transition-colors"
          >
            Kaydet
          </button>
          <button
            onClick={onCancel}
            className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
          >
            İptal
          </button>
        </div>
      </td>
    </tr>
  )
}

function AddRow({
  onSave,
  onCancel,
}: {
  onSave: (name: string, ip: string, rack: number, slot: number) => void
  onCancel: () => void
}) {
  const [name, setName] = useState('')
  const [ip, setIp] = useState('')
  const [rack, setRack] = useState(0)
  const [slot, setSlot] = useState(1)

  return (
    <tr className="border-t-2 border-cyan-700 bg-cyan-950/20">
      <td className="px-4 py-2.5">
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="PLC adı"
          className="bg-gray-700 text-gray-100 text-sm rounded px-2 py-1 border border-cyan-600 focus:outline-none w-32"
        />
      </td>
      <td className="px-4 py-2.5">
        <input
          value={ip}
          onChange={(e) => setIp(e.target.value)}
          placeholder="192.168.x.x"
          className="bg-gray-700 text-gray-100 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none w-36 font-mono"
        />
      </td>
      <td className="px-4 py-2.5">
        <input
          type="number"
          value={rack}
          onChange={(e) => setRack(Number(e.target.value))}
          className="bg-gray-700 text-gray-100 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none w-16"
          min={0} max={7}
        />
      </td>
      <td className="px-4 py-2.5">
        <input
          type="number"
          value={slot}
          onChange={(e) => setSlot(Number(e.target.value))}
          className="bg-gray-700 text-gray-100 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none w-16"
          min={0} max={31}
        />
      </td>
      <td className="px-4 py-2.5 text-sm text-gray-600">—</td>
      <td className="px-4 py-2.5 text-sm text-gray-600">—</td>
      <td className="px-4 py-2.5 text-right">
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={() => name.trim() && onSave(name.trim(), ip, rack, slot)}
            disabled={!name.trim()}
            className="px-3 py-1 text-xs bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white rounded transition-colors"
          >
            Ekle
          </button>
          <button
            onClick={onCancel}
            className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
          >
            İptal
          </button>
        </div>
      </td>
    </tr>
  )
}

function PlcRow({
  plc,
  onEdit,
  onDelete,
}: {
  plc: PlcEntry
  onEdit: () => void
  onDelete: () => void
}) {
  const [confirming, setConfirming] = useState(false)

  return (
    <tr className="border-t border-gray-800 hover:bg-gray-800/40 transition-colors">
      <td className="px-4 py-3 text-sm text-white font-medium">{plc.name}</td>
      <td className="px-4 py-3 text-sm text-gray-300 font-mono">{plc.ip || <span className="text-gray-600 italic">—</span>}</td>
      <td className="px-4 py-3 text-sm text-gray-400">{plc.rack}</td>
      <td className="px-4 py-3 text-sm text-gray-400">{plc.slot}</td>
      <td className="px-4 py-3 text-sm text-gray-400">{plc.tag_count.toLocaleString('tr')}</td>
      <td className="px-4 py-3"><ConnBadge connected={plc.connected} /></td>
      <td className="px-4 py-3 text-right">
        {confirming ? (
          <div className="flex items-center justify-end gap-2">
            <span className="text-xs text-red-400">
              {plc.tag_count > 0 ? `${plc.tag_count} tag silinecek!` : 'Emin misin?'}
            </span>
            <button
              onClick={() => { onDelete(); setConfirming(false) }}
              className="px-3 py-1 text-xs bg-red-700 hover:bg-red-600 text-white rounded transition-colors"
            >
              Sil
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
            >
              İptal
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={onEdit}
              className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
            >
              Düzenle
            </button>
            <button
              onClick={() => setConfirming(true)}
              className="px-3 py-1 text-xs bg-red-900/40 hover:bg-red-800/60 text-red-400 rounded transition-colors"
            >
              Sil
            </button>
          </div>
        )}
      </td>
    </tr>
  )
}

export default function PlcConfig() {
  const qc = useQueryClient()
  const [editingName, setEditingName] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')

  const { data: plcs = [], isLoading, isError } = useQuery({
    queryKey: ['plcs'],
    queryFn: () => listPlcs().then((r) => r.data),
    refetchInterval: 15000,
  })

  const save = useMutation({
    mutationFn: ({ name, ip, rack, slot }: { name: string; ip: string; rack: number; slot: number }) =>
      updatePlc(name, { ip, rack, slot }),
    onSuccess: () => {
      setEditingName(null)
      qc.invalidateQueries({ queryKey: ['plcs'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    },
  })

  const add = useMutation({
    mutationFn: ({ name, ip, rack, slot }: { name: string; ip: string; rack: number; slot: number }) =>
      createPlc({ name, ip, rack, slot }),
    onSuccess: () => {
      setAdding(false)
      setError('')
      qc.invalidateQueries({ queryKey: ['plcs'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Eklenemedi')
    },
  })

  const remove = useMutation({
    mutationFn: (name: string) => deletePlc(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plcs'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      qc.invalidateQueries({ queryKey: ['dashboard-tags'] })
      qc.invalidateQueries({ queryKey: ['overview'] })
    },
  })

  const connected = plcs.filter((p) => p.connected).length
  const total = plcs.length

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">PLC Yönetimi</h1>
          <p className="text-sm text-gray-500 mt-0.5">IP adresi ve bağlantı noktası yapılandırması</p>
        </div>
        <div className="flex items-center gap-3">
          {total > 0 && (
            <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium ${connected === total ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'}`}>
              <span className="w-2 h-2 rounded-full bg-current" />
              {connected}/{total} Bağlı
            </span>
          )}
          {!adding && (
            <button
              onClick={() => { setAdding(true); setError('') }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-cyan-700 hover:bg-cyan-600 text-white rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Yeni PLC Ekle
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm px-4 py-2.5 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-red-400 hover:text-red-200">✕</button>
        </div>
      )}

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Yükleniyor...</div>
      ) : isError ? (
        <div className="text-center py-16 bg-gray-900 rounded-xl border border-red-900">
          <p className="text-red-400">PLC listesi yüklenemedi</p>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-2 text-left">PLC Adı</th>
                <th className="px-4 py-2 text-left">IP Adresi</th>
                <th className="px-4 py-2 text-left">Rack</th>
                <th className="px-4 py-2 text-left">Slot</th>
                <th className="px-4 py-2 text-left">Tag Sayısı</th>
                <th className="px-4 py-2 text-left">Durum</th>
                <th className="px-4 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {adding && (
                <AddRow
                  onSave={(name, ip, rack, slot) => add.mutate({ name, ip, rack, slot })}
                  onCancel={() => { setAdding(false); setError('') }}
                />
              )}
              {plcs.length === 0 && !adding ? (
                <tr>
                  <td colSpan={7} className="px-4 py-16 text-center text-gray-500">
                    Henüz PLC kaydı yok. "Yeni PLC Ekle" ile başlayın.
                  </td>
                </tr>
              ) : (
                plcs.map((plc) =>
                  editingName === plc.name ? (
                    <EditRow
                      key={plc.name}
                      plc={plc}
                      onSave={(ip, rack, slot) => save.mutate({ name: plc.name, ip, rack, slot })}
                      onCancel={() => setEditingName(null)}
                    />
                  ) : (
                    <PlcRow
                      key={plc.name}
                      plc={plc}
                      onEdit={() => setEditingName(plc.name)}
                      onDelete={() => remove.mutate(plc.name)}
                    />
                  )
                )
              )}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-gray-600">
        IP değiştirildiğinde yeni bağlantı bir sonraki poller döngüsünde kurulur. PLC silindiğinde tüm bağlı tag'ler de kaldırılır.
      </p>
    </div>
  )
}
