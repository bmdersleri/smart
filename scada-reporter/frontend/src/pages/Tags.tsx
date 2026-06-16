import { useRef, useState } from 'react'
import type { AxiosError } from 'axios'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getTags, createTag, deleteTag, updateTag, importTags, importTagsCsv, exportTags,
  getGroups, getGroupTree, createGroup, deleteGroup, assignTagsToGroup, unassignTags,
} from '../api/client'
import type { Tag, Group, GroupNode } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useSortable } from '../hooks/useSortable'
import SortHeader from '../components/SortHeader'

function downloadBlob(data: BlobPart, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([data], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

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

function EditTagModal({ tag, groups, onClose }: { tag: Tag; groups: Group[]; onClose: () => void }) {
  const qc = useQueryClient()
  const [unit, setUnit] = useState(tag.unit)
  const [device, setDevice] = useState(tag.device)
  const [channel, setChannel] = useState(tag.channel)
  const [deadband, setDeadband] = useState(tag.deadband ?? '')
  const [groupId, setGroupId] = useState<number | null>(tag.group_id)

  const mut = useMutation({
    mutationFn: async (payload: Parameters<typeof updateTag>[1]) => {
      await updateTag(tag.id, payload)
      if (groupId !== tag.group_id) {
        if (groupId === null) await unassignTags([tag.id])
        else await assignTagsToGroup(groupId, [tag.id])
      }
    },
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
          <label className="text-xs text-gray-400 mb-1 block">Grup (hiyerarşi)</label>
          <select
            className={inputCls}
            value={groupId ?? ''}
            onChange={(e) => setGroupId(e.target.value === '' ? null : Number(e.target.value))}
          >
            <option value="">— Gruplanmamış —</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </div>

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
  const isCsv = !!file && /\.csv$/i.test(file.name)
  const mut = useMutation({
    mutationFn: (f: File) => (/\.csv$/i.test(f.name) ? importTagsCsv(f) : importTags(f)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tags'] }) },
  })

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Tag Import</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        <p className="text-gray-400 text-sm">
          <strong className="text-gray-300">WinCC</strong> <code className="text-blue-400">full_export.xlsx</code> (Connections + Tags),
          veya <strong className="text-gray-300">genel CSV</strong> (<code className="text-blue-400">tags-export.csv</code> ile aynı kolonlar) seçin.
          CSV'de en az <code className="text-blue-400">name</code> kolonu yeterli; mevcut node_id atlanır.
          <br />Archive katalogu için sunucuda <code className="text-blue-400">just seed-catalog</code> kullanın.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button
          onClick={() => fileRef.current?.click()}
          className="w-full py-10 border-2 border-dashed border-gray-700 rounded-xl text-gray-500 hover:border-blue-500 hover:text-blue-400 transition-colors text-sm"
        >
          {file ? `${file.name} ${isCsv ? '(CSV)' : '(WinCC xlsx)'}` : 'Dosya seçmek için tıklayın (.xlsx / .csv)'}
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

function GroupsModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: () => getGroups().then((r) => r.data) })
  const [name, setName] = useState('')
  const [parentId, setParentId] = useState<number | null>(null)

  const createMut = useMutation({
    mutationFn: () => createGroup({ name: name.trim(), parent_id: parentId }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['groups'] }); setName('') },
  })
  const delMut = useMutation({
    mutationFn: (id: number) => deleteGroup(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['groups'] }); qc.invalidateQueries({ queryKey: ['tags'] }) },
  })

  // tek-seviye girinti için parent adı çözümü
  const nameOf = (id: number | null) => groups.find((g) => g.id === id)?.name ?? null
  const inputCls = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Tag Grupları (Hiyerarşi)</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        <p className="text-gray-400 text-sm">
          Tesis hiyerarşisi düğümleri (Site → Ünite → Ekipman). Tag'leri düzenleme ekranından bir gruba atayın.
          Trend ekranında <strong className="text-gray-300">Otomatik</strong> ağaç (PLC → cihaz) her zaman mevcuttur.
        </p>

        <div className="bg-gray-800/40 border border-gray-700 rounded-lg p-3 space-y-2">
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Yeni grup adı (ör. Arıtma Hattı 1)" />
          <select className={inputCls} value={parentId ?? ''} onChange={(e) => setParentId(e.target.value === '' ? null : Number(e.target.value))}>
            <option value="">Üst grup: (kök)</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <button
            onClick={() => createMut.mutate()}
            disabled={!name.trim() || createMut.isPending}
            className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {createMut.isPending ? 'Ekleniyor...' : '+ Grup Ekle'}
          </button>
        </div>

        <div className="max-h-64 overflow-y-auto space-y-1">
          {groups.length === 0 && <p className="text-gray-500 text-sm text-center py-4">Henüz grup yok.</p>}
          {groups.map((g) => (
            <div key={g.id} className="flex items-center justify-between bg-gray-800/40 rounded-lg px-3 py-2">
              <span className="text-sm text-gray-200">
                {g.parent_id != null && <span className="text-gray-600">{nameOf(g.parent_id)} / </span>}
                {g.name}
              </span>
              <button
                onClick={() => { if (confirm(`"${g.name}" grubu silinsin mi? Tag'ler gruplanmamış olur.`)) delMut.mutate(g.id) }}
                className="text-gray-500 hover:text-red-400 text-xs px-2"
              >
                Sil
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function TagRow({
  tag, canEdit, onEdit, onDelete, indent,
}: {
  tag: Tag; canEdit: boolean; onEdit: (t: Tag) => void; onDelete: (t: Tag) => void; indent: number
}) {
  return (
    <div className="flex items-center gap-2 py-1.5 pr-2 hover:bg-gray-800/40 rounded-lg" style={{ paddingLeft: indent }}>
      <span className="w-1.5 h-1.5 rounded-full bg-gray-600 flex-shrink-0" />
      <span className="text-sm text-white truncate flex-1">{tag.name}</span>
      <span className="text-xs font-mono text-gray-600 hidden sm:inline">{tag.s7_address ?? '—'}</span>
      <span className="text-xs text-gray-500 w-10 text-right">{tag.unit}</span>
      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${tag.is_active ? 'bg-green-900/50 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
        {tag.is_active ? 'Aktif' : 'Pasif'}
      </span>
      {canEdit && (
        <div className="flex gap-1">
          <button onClick={() => onEdit(tag)} title="Düzenle" className="p-1 rounded text-gray-500 hover:text-blue-400 hover:bg-blue-500/10">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
          </button>
          <button onClick={() => onDelete(tag)} title="Sil" className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-red-500/10">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
          </button>
        </div>
      )}
    </div>
  )
}

function TagTreeNode({
  node, tagMap, canEdit, onEdit, onDelete, depth,
}: {
  node: GroupNode; tagMap: Map<number, Tag>; canEdit: boolean
  onEdit: (t: Tag) => void; onDelete: (t: Tag) => void; depth: number
}) {
  const [open, setOpen] = useState(depth < 1)
  const leafTags = node.tag_ids.map((id) => tagMap.get(id)).filter(Boolean) as Tag[]
  // alt ağaçtaki toplam tag sayısı (rozet için)
  const count = (n: GroupNode): number => n.tag_ids.length + n.children.reduce((s, c) => s + count(c), 0)
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1.5 py-1.5 text-sm text-gray-200 hover:text-white"
        style={{ paddingLeft: depth * 16 + 4 }}
      >
        <span className="text-gray-500 w-3">{open ? '▾' : '▸'}</span>
        <svg className="w-4 h-4 text-indigo-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" /></svg>
        <span className="font-medium truncate">{node.name}</span>
        <span className="text-xs text-gray-600 ml-1">{count(node)}</span>
      </button>
      {open && (
        <div>
          {node.children.map((c, i) => (
            <TagTreeNode key={c.id ?? `${node.name}-${i}`} node={c} tagMap={tagMap} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} depth={depth + 1} />
          ))}
          {leafTags.map((t) => (
            <TagRow key={t.id} tag={t} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} indent={(depth + 1) * 16 + 18} />
          ))}
        </div>
      )}
    </div>
  )
}

function TagTreeView({
  source, tags, canEdit, onEdit, onDelete,
}: {
  source: 'manual' | 'auto'; tags: Tag[]; canEdit: boolean
  onEdit: (t: Tag) => void; onDelete: (t: Tag) => void
}) {
  const { data: tree = [], isLoading } = useQuery({
    queryKey: ['groupTree', source],
    queryFn: () => getGroupTree(source).then((r) => r.data),
  })
  const tagMap = new Map(tags.map((t) => [t.id, t]))
  const ungrouped = source === 'manual' ? tags.filter((t) => t.group_id === null) : []

  if (isLoading) return <div className="py-12 text-center text-gray-500">Yükleniyor...</div>
  return (
    <div className="p-2 space-y-0.5">
      {tree.length === 0 && ungrouped.length === 0 && (
        <p className="py-8 text-center text-gray-500 text-sm">
          {source === 'manual' ? 'Grup yok. 🗂 Gruplar ile oluşturun.' : 'Tag yok.'}
        </p>
      )}
      {tree.map((n, i) => (
        <TagTreeNode key={n.id ?? `root-${i}`} node={n} tagMap={tagMap} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} depth={0} />
      ))}
      {ungrouped.length > 0 && (
        <div className="pt-2 mt-2 border-t border-gray-800">
          <p className="text-xs text-gray-500 uppercase tracking-wide px-2 py-1">Gruplanmamış ({ungrouped.length})</p>
          {ungrouped.map((t) => (
            <TagRow key={t.id} tag={t} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} indent={22} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function Tags() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [showFormat, setShowFormat] = useState(false)
  const [showGroups, setShowGroups] = useState(false)
  const [editTag, setEditTag] = useState<Tag | null>(null)
  const [search, setSearch] = useState('')
  const [groupFilter, setGroupFilter] = useState<number | 'all' | 'none'>('all')
  const [viewMode, setViewMode] = useState<'table' | 'tree'>('table')
  const [treeSource, setTreeSource] = useState<'manual' | 'auto'>('manual')

  const { data: tags = [], isLoading } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
  })
  const { data: groups = [] } = useQuery({
    queryKey: ['groups'],
    queryFn: () => getGroups().then((r) => r.data),
  })
  const groupName = (id: number | null) => groups.find((g) => g.id === id)?.name ?? null

  const doExport = async (format: 'csv' | 'xlsx') => {
    const res = await exportTags(format)
    const ext = format === 'csv' ? 'csv' : 'xlsx'
    const type = format === 'csv'
      ? 'text/csv'
      : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    downloadBlob(res.data as BlobPart, `tags-export.${ext}`, type)
  }
  const delMut = useMutation({
    mutationFn: deleteTag,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tags'] }),
  })
  const handleDelete = (t: Tag) => { if (confirm(`"${t.name}" silinsin mi?`)) delMut.mutate(t.id) }

  const canEdit = user?.role === 'admin' || user?.role === 'operator'
  const filtered = tags.filter((t) => {
    if (groupFilter === 'none' && t.group_id !== null) return false
    if (typeof groupFilter === 'number' && t.group_id !== groupFilter) return false
    if (search) {
      const q = search.toLowerCase()
      if (!t.name.toLowerCase().includes(q) && !t.device.toLowerCase().includes(q)) return false
    }
    return true
  })
  const { sorted, sort, toggle } = useSortable(filtered, (t, k) =>
    k === 'plc' ? t.plc_name || t.device : (t as unknown as Record<string, unknown>)[k]
  )

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Tag Yönetimi</h1>
        <div className="flex gap-2 flex-wrap">
          <div className="flex">
            <button onClick={() => doExport('csv')} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-l-lg border border-gray-700 transition-colors">
              ↓ CSV
            </button>
            <button onClick={() => doExport('xlsx')} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-r-lg border border-l-0 border-gray-700 transition-colors">
              xlsx
            </button>
          </div>
          {canEdit && (
            <>
              <button onClick={() => setShowGroups(true)} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors">
                🗂 Gruplar
              </button>
              <button onClick={() => setShowImport(true)} className="px-3 py-2 text-sm bg-green-800 hover:bg-green-700 text-green-300 rounded-lg border border-green-700 transition-colors">
                📥 Import
              </button>
              <button onClick={() => setShowFormat(true)} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors">
                Format
              </button>
              <button onClick={() => setShowAdd(true)} className="px-3 py-2 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">
                + Tag Ekle
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Tag veya cihaz adı ara..."
          className="flex-1 bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
        />
        {viewMode === 'table' && (
          <select
            value={String(groupFilter)}
            onChange={(e) => {
              const v = e.target.value
              setGroupFilter(v === 'all' || v === 'none' ? v : Number(v))
            }}
            className="bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
            title="Gruba göre filtrele"
          >
            <option value="all">Tüm gruplar</option>
            <option value="none">Gruplanmamış</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        )}
        {/* Tablo / Ağaç görünüm anahtarı */}
        <div className="flex bg-gray-900 border border-gray-800 rounded-xl p-0.5">
          <button
            onClick={() => setViewMode('table')}
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${viewMode === 'table' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
            title="Tablo görünümü"
          >
            ☰ Tablo
          </button>
          <button
            onClick={() => setViewMode('tree')}
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${viewMode === 'tree' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
            title="Hiyerarşi ağacı"
          >
            🌲 Ağaç
          </button>
        </div>
        {viewMode === 'tree' && (
          <div className="flex bg-gray-900 border border-gray-800 rounded-xl p-0.5">
            {(['manual', 'auto'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setTreeSource(s)}
                className={`px-3 py-2 text-sm rounded-lg transition-colors ${treeSource === s ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}
              >
                {s === 'manual' ? 'Manuel' : 'Auto'}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {viewMode === 'tree' ? (
          <TagTreeView source={treeSource} tags={tags} canEdit={canEdit} onEdit={setEditTag} onDelete={handleDelete} />
        ) : isLoading ? (
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
                  { label: 'Grup', key: 'group_id' },
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
                  <td className="px-4 py-3 text-sm">
                    {groupName(t.group_id)
                      ? <span className="text-[11px] px-1.5 py-0.5 rounded bg-indigo-900/40 text-indigo-300">{groupName(t.group_id)}</span>
                      : <span className="text-gray-600">—</span>}
                  </td>
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
      {showGroups && <GroupsModal onClose={() => setShowGroups(false)} />}
      {editTag && <EditTagModal tag={editTag} groups={groups} onClose={() => setEditTag(null)} />}
    </div>
  )
}
