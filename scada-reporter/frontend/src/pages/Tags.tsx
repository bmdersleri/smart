import { useRef, useState } from 'react'
import type { AxiosError } from 'axios'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTags, createTag, deleteTag, updateTag, importTags } from '../api/client'
import type { Tag } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useSortable } from '../hooks/useSortable'
import SortHeader from '../components/SortHeader'

function AddTagModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    name: '', plc_name: '', plc_ip: '', s7_address: '', data_type: 'float32',
    unit: '', sample_interval: '5',
  })
  const mut = useMutation({
    mutationFn: createTag,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tags'] }) },
  })
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = () => mut.mutate({
    name: form.name, plc_name: form.plc_name, plc_ip: form.plc_ip || null,
    s7_address: form.s7_address || null, data_type: form.data_type, unit: form.unit,
    device: form.plc_name, sample_interval: parseInt(form.sample_interval) || 5, long_term: true,
  })

  const inputCls = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500'
  const result = mut.data?.data

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-white">Yeni Tag Ekle</h2>
        {[
          { k: 'name', label: 'Tag Adı', ph: 'Hat Debisi' },
          { k: 'plc_name', label: 'PLC Adı', ph: 'PLC4' },
          { k: 'plc_ip', label: 'PLC IP', ph: '192.168.115.2' },
          { k: 's7_address', label: 'S7 Adresi (WinCC)', ph: 'DB301,DD7890' },
          { k: 'unit', label: 'Birim', ph: 'm³/h' },
          { k: 'sample_interval', label: 'Kayıt Aralığı (sn)', ph: '5' },
        ].map(({ k, label, ph }) => (
          <div key={k}>
            <label className="text-xs text-gray-400 mb-1 block">{label}</label>
            <input className={inputCls} value={(form as Record<string, string>)[k]} onChange={set(k)} placeholder={ph} />
          </div>
        ))}
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Veri Tipi</label>
          <select className={inputCls} value={form.data_type} onChange={set('data_type')}>
            <option value="float32">float32 (REAL)</option>
            <option value="float64">float64 (REAL)</option>
            <option value="uint16">uint16 (WORD)</option>
            <option value="int16">int16 (INT)</option>
            <option value="Binary">Binary (BOOL)</option>
          </select>
        </div>

        {result && (
          <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-3 text-sm">
            <p className="text-gray-300">Anlık değer:
              <span className="text-white font-mono ml-1">{result.current_value ?? '—'}</span>
              {result.unit ? ` ${result.unit}` : ''}
            </p>
            <p className="text-xs mt-1">
              Kalite: <span className={result.quality === 192 ? 'text-green-400' : 'text-yellow-400'}>
                {result.quality === 192 ? 'Good' : 'PLC erişilemedi / —'}
              </span>
            </p>
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors">
            {result ? 'Kapat' : 'İptal'}
          </button>
          <button
            onClick={submit} disabled={!form.name || !form.s7_address || mut.isPending}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {mut.isPending ? 'Ekleniyor...' : result ? 'Tekrar Ekle' : 'Ekle'}
          </button>
        </div>
        {mut.isError && <p className="text-red-400 text-sm">Hata oluştu.</p>}
      </div>
    </div>
  )
}

function EditTagModal({ tag, onClose }: { tag: Tag; onClose: () => void }) {
  const qc = useQueryClient()
  const [unit, setUnit] = useState(tag.unit)
  const [device, setDevice] = useState(tag.device)
  const [channel, setChannel] = useState(tag.channel)
  const [deadband, setDeadband] = useState(tag.deadband ?? '')

  const mut = useMutation({
    mutationFn: (payload: Parameters<typeof updateTag>[1]) => updateTag(tag.id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tags'] }); onClose() },
  })

  const save = () => mut.mutate({ unit, device, channel, deadband: deadband === '' ? null : Number(deadband) })

  const inputCls = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">{tag.name} — Düzenle</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div>
          <label className="text-xs text-gray-400 mb-1 block">S7 Adresi / PLC (değiştirilemez)</label>
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-500 font-mono">
            {tag.s7_address ?? tag.node_id}{tag.plc_ip ? ` @ ${tag.plc_ip}` : ''}
          </div>
        </div>

        {[
          { label: 'Birim', value: unit, set: setUnit, ph: 'm³/h' },
          { label: 'Cihaz', value: device, set: setDevice, ph: 'PLC_1500' },
          { label: 'Kanal', value: channel, set: setChannel, ph: 'Channel1' },
        ].map(({ label, value, set, ph }) => (
          <div key={label}>
            <label className="text-xs text-gray-400 mb-1 block">{label}</label>
            <input className={inputCls} value={value} onChange={(e) => set(e.target.value)} placeholder={ph} />
          </div>
        ))}

        <div>
          <label className="text-xs text-gray-400 mb-1 block">Deadband (ölü bant) — boş: her okuma kaydedilir</label>
          <input className={inputCls} type="number" step="any" min="0" value={deadband} onChange={(e) => setDeadband(e.target.value)} placeholder="ör. 0.5 (mutlak değişim eşiği)" />
          <p className="text-gray-600 text-xs mt-1">Değer bu kadar değişmedikçe geçmişe yazılmaz; heartbeat ile periyodik zorla-yazılır.</p>
        </div>

        {mut.isError && <p className="text-red-400 text-sm">Kayıt hatası.</p>}

        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors">İptal</button>
          <button
            onClick={save} disabled={mut.isPending}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {mut.isPending ? 'Kaydediliyor...' : 'Kaydet'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ImportTagModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const mut = useMutation({
    mutationFn: importTags,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tags'] }); onClose() },
  })

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">WinCC Tag Import</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        <p className="text-gray-400 text-sm">
          WinCC <code className="text-blue-400">full_export.xlsx</code> dosyasını seçin (Connections + Tags sayfaları).
          PLC IP'leri çözülür, mutlak adres + tip ile tag'ler eklenir.
          <br />Uzun-süre (archive) katalogu için sunucuda <code className="text-blue-400">just seed-catalog</code> kullanın.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx,.xls"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button
          onClick={() => fileRef.current?.click()}
          className="w-full py-10 border-2 border-dashed border-gray-700 rounded-xl text-gray-500 hover:border-blue-500 hover:text-blue-400 transition-colors text-sm"
        >
          {file ? file.name : 'Dosya seçmek için tıklayın'}
        </button>

        {mut.isSuccess && (
          <div className="bg-green-900/30 border border-green-700 rounded-lg p-3 text-sm text-green-400">
            <p><strong>{mut.data.data.imported}</strong> tag içe aktarıldı.</p>
            {mut.data.data.skipped > 0 && <p><strong>{mut.data.data.skipped}</strong> tag atlandı (zaten mevcut).</p>}
          </div>
        )}
        {mut.isError && (
          <p className="text-red-400 text-sm">Import hatası: {(mut.error as AxiosError<{ detail: string }>)?.response?.data?.detail || 'Bilinmeyen hata'}</p>
        )}

        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors">İptal</button>
          <button
            onClick={() => file && mut.mutate(file)}
            disabled={!file || mut.isPending}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {mut.isPending ? 'Import ediliyor...' : 'Import Et'}
          </button>
        </div>
      </div>
    </div>
  )
}

function FormatGuideModal({ onClose }: { onClose: () => void }) {
  const examples = [
    { addr: 'DB301,DD7890', desc: 'WinCC: DB301, double word (REAL), offset 7890' },
    { addr: 'DB310,DBW90', desc: 'WinCC: DB310, word (uint16), offset 90' },
    { addr: 'Q254.1', desc: 'WinCC: çıkış biti (BOOL), byte 254, bit 1' },
    { addr: 'DB1,REAL0', desc: 'Legacy: DB1, REAL (32-bit float), offset 0' },
    { addr: 'DB5,BOOL10.3', desc: 'Legacy: DB5, BOOL, byte 10, bit 3' },
  ]
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">S7 Adres Formatı</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        <p className="text-gray-400 text-sm">Node ID alanına aşağıdaki formatta girin:</p>
        <div className="bg-gray-800 rounded-lg p-4 space-y-2">
          {examples.map(({ addr, desc }) => (
            <div key={addr} className="flex items-baseline gap-3">
              <span className="text-blue-400 font-mono text-sm w-32 flex-shrink-0">{addr}</span>
              <span className="text-gray-500 text-xs">{desc}</span>
            </div>
          ))}
        </div>
        <p className="text-gray-600 text-xs">Operandlar: DD/DBD (4B) · DBW/DW (2B) · DBB · DBX/BOOL · Q/I (proses imaj biti)</p>
        <button onClick={onClose} className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors">Tamam</button>
      </div>
    </div>
  )
}

export default function Tags() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [showFormat, setShowFormat] = useState(false)
  const [editTag, setEditTag] = useState<Tag | null>(null)
  const [search, setSearch] = useState('')

  const { data: tags = [], isLoading } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
  })
  const delMut = useMutation({
    mutationFn: deleteTag,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tags'] }),
  })

  const canEdit = user?.role === 'admin' || user?.role === 'operator'
  const filtered = search
    ? tags.filter((t) =>
        t.name.toLowerCase().includes(search.toLowerCase()) ||
        t.device.toLowerCase().includes(search.toLowerCase())
      )
    : tags
  const { sorted, sort, toggle } = useSortable(filtered, (t, k) =>
    k === 'plc' ? t.plc_name || t.device : (t as unknown as Record<string, unknown>)[k]
  )

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Tag Yönetimi</h1>
        {canEdit && (
          <div className="flex gap-2">
            <button onClick={() => setShowImport(true)} className="px-3 py-2 text-sm bg-green-800 hover:bg-green-700 text-green-300 rounded-lg border border-green-700 transition-colors">
              📥 Import
            </button>
            <button onClick={() => setShowFormat(true)} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors">
              Format
            </button>
            <button onClick={() => setShowAdd(true)} className="px-3 py-2 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">
              + Tag Ekle
            </button>
          </div>
        )}
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Tag veya cihaz adı ara..."
        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
      />

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="py-12 text-center text-gray-500">Yükleniyor...</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-gray-400">{search ? 'Eşleşen tag bulunamadı.' : 'Henüz tag yok.'}</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="border-b border-gray-800">
              <tr className="text-xs text-gray-500 uppercase tracking-wide">
                {[
                  { label: 'PLC', key: 'plc' },
                  { label: 'Tag Adı', key: 'name' },
                  { label: 'PLC IP', key: 'plc_ip' },
                  { label: 'S7 Adresi', key: 's7_address' },
                  { label: 'Aralık', key: 'sample_interval' },
                  { label: 'Birim', key: 'unit' },
                  { label: 'Durum', key: 'is_active' },
                ].map((c) => (
                  <SortHeader key={c.key} label={c.label} sortKey={c.key} sort={sort} onToggle={toggle} className="px-4 py-3" />
                ))}
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((t: Tag) => (
                <tr key={t.id} className="border-t border-gray-800 hover:bg-gray-800/40">
                  <td className="px-4 py-3 text-sm text-gray-400">{t.plc_name || t.device}</td>
                  <td className="px-4 py-3 text-sm font-medium text-white">
                    {t.name}
                    {t.long_term && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-blue-900/50 text-blue-300">uzun-süre</span>}
                    {t.daily_tracking && <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-purple-900/50 text-purple-300">günlük</span>}
                  </td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-500">{t.plc_ip ?? '—'}</td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-500">{t.s7_address ?? '—'}</td>
                  <td className="px-4 py-3 text-sm text-gray-400">{t.sample_interval}s</td>
                  <td className="px-4 py-3 text-sm text-gray-300">{t.unit}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${t.is_active ? 'bg-green-900/50 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
                      {t.is_active ? 'Aktif' : 'Pasif'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {canEdit && (
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => setEditTag(t)}
                          title="Düzenle"
                          className="p-1.5 rounded-lg text-gray-400 hover:text-blue-400 hover:bg-blue-500/10 border border-gray-700 hover:border-blue-500/40 transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => { if (confirm(`"${t.name}" silinsin mi?`)) delMut.mutate(t.id) }}
                          title="Sil"
                          className="p-1.5 rounded-lg text-gray-400 hover:text-red-400 hover:bg-red-500/10 border border-gray-700 hover:border-red-500/40 transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showAdd && <AddTagModal onClose={() => setShowAdd(false)} />}
      {showImport && <ImportTagModal onClose={() => setShowImport(false)} />}
      {showFormat && <FormatGuideModal onClose={() => setShowFormat(false)} />}
      {editTag && <EditTagModal tag={editTag} onClose={() => setEditTag(null)} />}
    </div>
  )
}
