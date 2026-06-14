import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTags, createTag, deleteTag, browseOpcTags } from '../api/client'
import type { Tag } from '../api/client'
import { useAuth } from '../context/AuthContext'

function AddTagModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ node_id: '', name: '', unit: '', device: '', channel: '', description: '' })
  const mut = useMutation({
    mutationFn: createTag,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tags'] }); onClose() },
  })
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }))

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-white">Yeni Tag Ekle</h2>
        {[
          { k: 'node_id', label: 'OPC Node ID', ph: 'ns=2;s=Channel1.PLC.Debi' },
          { k: 'name', label: 'Tag Adı', ph: 'Hat Debisi' },
          { k: 'unit', label: 'Birim', ph: 'm³/h' },
          { k: 'device', label: 'Cihaz (PLC)', ph: 'PLC_1500' },
          { k: 'channel', label: 'Kanal', ph: 'Channel1' },
        ].map(({ k, label, ph }) => (
          <div key={k}>
            <label className="text-xs text-gray-400 mb-1 block">{label}</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
              value={(form as Record<string, string>)[k]} onChange={set(k)} placeholder={ph}
            />
          </div>
        ))}
        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors">İptal</button>
          <button
            onClick={() => mut.mutate(form)} disabled={!form.node_id || !form.name || mut.isPending}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {mut.isPending ? 'Ekleniyor...' : 'Ekle'}
          </button>
        </div>
        {mut.isError && <p className="text-red-400 text-sm">Hata oluştu.</p>}
      </div>
    </div>
  )
}

function BrowseModal({ onSelect, onClose }: { onSelect: (t: { node_id: string; name: string }) => void; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({ queryKey: ['browse-opc'], queryFn: () => browseOpcTags().then((r) => r.data) })

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">OPC UA Tag Tarayıcı</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        <div className="flex-1 overflow-auto p-4">
          {isLoading && <p className="text-gray-400 text-center py-8">KEPServerEX taranıyor...</p>}
          {error && (
            <div className="text-center py-8">
              <p className="text-red-400">OPC UA bağlantısı kurulamadı.</p>
              <p className="text-gray-500 text-sm mt-1">KEPServerEX'te None güvenlik modunu etkinleştirin.</p>
            </div>
          )}
          {data?.tags.map((t) => (
            <button
              key={t.node_id}
              onClick={() => onSelect(t)}
              className="w-full text-left px-3 py-2 rounded-lg hover:bg-gray-800 transition-colors flex items-center gap-3"
              style={{ paddingLeft: `${(t.depth + 1) * 12}px` }}
            >
              <span className="text-gray-500 text-xs font-mono flex-shrink-0">{t.node_id.split(';s=')[1] ?? t.node_id}</span>
              <span className="text-white text-sm">{t.name}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function Tags() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [showBrowse, setShowBrowse] = useState(false)
  const { data: tags = [], isLoading } = useQuery({ queryKey: ['tags'], queryFn: () => getTags().then((r) => r.data) })
  const delMut = useMutation({ mutationFn: deleteTag, onSuccess: () => qc.invalidateQueries({ queryKey: ['tags'] }) })

  const canEdit = user?.role === 'admin' || user?.role === 'operator'

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Tag Yönetimi</h1>
        {canEdit && (
          <div className="flex gap-2">
            <button onClick={() => setShowBrowse(true)} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors">
              OPC Tara
            </button>
            <button onClick={() => setShowAdd(true)} className="px-3 py-2 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">
              + Tag Ekle
            </button>
          </div>
        )}
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="py-12 text-center text-gray-500">Yükleniyor...</div>
        ) : tags.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-gray-400">Henüz tag yok.</p>
            <p className="text-gray-500 text-sm mt-1">OPC Tara ile KEPServerEX'ten tag seçin veya elle ekleyin.</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="border-b border-gray-800">
              <tr className="text-xs text-gray-500 uppercase tracking-wide">
                {['Cihaz', 'Tag Adı', 'Node ID', 'Birim', 'Durum', ''].map((h) => (
                  <th key={h} className="px-4 py-3 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tags.map((t: Tag) => (
                <tr key={t.id} className="border-t border-gray-800 hover:bg-gray-800/40">
                  <td className="px-4 py-3 text-sm text-gray-400">{t.device}</td>
                  <td className="px-4 py-3 text-sm font-medium text-white">{t.name}</td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-500">{t.node_id}</td>
                  <td className="px-4 py-3 text-sm text-gray-300">{t.unit}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${t.is_active ? 'bg-green-900/50 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
                      {t.is_active ? 'Aktif' : 'Pasif'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {canEdit && (
                      <button
                        onClick={() => delMut.mutate(t.id)}
                        className="text-xs text-gray-500 hover:text-red-400 transition-colors"
                      >
                        Sil
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showAdd && <AddTagModal onClose={() => setShowAdd(false)} />}
      {showBrowse && (
        <BrowseModal
          onSelect={(_t) => { setShowBrowse(false); setShowAdd(true) }}
          onClose={() => setShowBrowse(false)}
        />
      )}
    </div>
  )
}
