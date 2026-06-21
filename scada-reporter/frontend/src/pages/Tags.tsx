import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation(['tags', 'common'])
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
        <h2 className="text-lg font-semibold text-white">{t('add_modal_title')}</h2>
        {[
          { k: 'name', label: t('field_name'), ph: 'Line Flow' },
          { k: 'plc_name', label: t('field_plc_name'), ph: 'PLC4' },
          { k: 'plc_ip', label: t('field_plc_ip'), ph: '192.168.115.2' },
          { k: 's7_address', label: t('field_s7_address'), ph: 'DB301,DD7890' },
          { k: 'unit', label: t('field_unit'), ph: 'm³/h' },
          { k: 'sample_interval', label: t('field_interval'), ph: '5' },
        ].map(({ k, label, ph }) => (
          <div key={k}>
            <label className="text-xs text-gray-400 mb-1 block">{label}</label>
            <input className={inputCls} value={(form as Record<string, string>)[k]} onChange={set(k)} placeholder={ph} />
          </div>
        ))}
        <div>
          <label className="text-xs text-gray-400 mb-1 block">{t('field_data_type')}</label>
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
            <p className="text-gray-300">{t('current_value')}
              <span className="text-white font-mono ms-1">{result.current_value ?? '—'}</span>
              {result.unit ? ` ${result.unit}` : ''}
            </p>
            <p className="text-xs mt-1">
              {t('quality_label')} <span className={result.quality === 192 ? 'text-green-400' : 'text-yellow-400'}>
                {result.quality === 192 ? t('quality_good') : t('quality_unreachable')}
              </span>
            </p>
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors">
            {result ? t('close') : t('common:cancel')}
          </button>
          <button
            onClick={submit} disabled={!form.name || !form.s7_address || mut.isPending}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {mut.isPending ? t('adding') : result ? t('add_again') : t('common:add')}
          </button>
        </div>
        {mut.isError && <p className="text-red-400 text-sm">{t('error_occurred')}</p>}
      </div>
    </div>
  )
}

function EditTagModal({ tag, groups, onClose }: { tag: Tag; groups: Group[]; onClose: () => void }) {
  const { t } = useTranslation(['tags', 'common'])
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
          <h2 className="text-lg font-semibold text-white">{t('edit_modal_title', { name: tag.name })}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div>
          <label className="text-xs text-gray-400 mb-1 block">{t('s7_immutable')}</label>
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-500 font-mono">
            {tag.s7_address ?? tag.node_id}{tag.plc_ip ? ` @ ${tag.plc_ip}` : ''}
          </div>
        </div>

        {[
          { label: t('field_unit'), value: unit, set: setUnit, ph: 'm³/h' },
          { label: t('field_device'), value: device, set: setDevice, ph: 'PLC_1500' },
          { label: t('field_channel'), value: channel, set: setChannel, ph: 'Channel1' },
        ].map(({ label, value, set, ph }) => (
          <div key={label}>
            <label className="text-xs text-gray-400 mb-1 block">{label}</label>
            <input className={inputCls} value={value} onChange={(e) => set(e.target.value)} placeholder={ph} />
          </div>
        ))}

        <div>
          <label className="text-xs text-gray-400 mb-1 block">{t('field_group_hierarchy')}</label>
          <select
            className={inputCls}
            value={groupId ?? ''}
            onChange={(e) => setGroupId(e.target.value === '' ? null : Number(e.target.value))}
          >
            <option value="">{t('ungrouped_option')}</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-400 mb-1 block">{t('deadband_label')}</label>
          <input className={inputCls} type="number" step="any" min="0" value={deadband} onChange={(e) => setDeadband(e.target.value)} placeholder={t('deadband_placeholder')} />
          <p className="text-gray-600 text-xs mt-1">{t('deadband_hint')}</p>
        </div>

        {mut.isError && <p className="text-red-400 text-sm">{t('save_error')}</p>}

        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors">{t('common:cancel')}</button>
          <button
            onClick={save} disabled={mut.isPending}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {mut.isPending ? t('saving') : t('common:save')}
          </button>
        </div>
      </div>
    </div>
  )
}

function ImportTagModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation(['tags', 'common'])
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
          <h2 className="text-lg font-semibold text-white">{t('import_modal_title')}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        <p className="text-gray-400 text-sm">
          {t('import_desc_before_winncc')}<strong className="text-gray-300">{t('import_winncc')}</strong> <code className="text-blue-400">full_export.xlsx</code>{t('import_desc_between')}<strong className="text-gray-300">{t('import_generic_csv')}</strong>{t('import_desc_between2')}<code className="text-blue-400">tags-export.csv</code>{t('import_desc_after_csv')}<code className="text-blue-400">name</code>{t('import_desc_name_suffix')}
          <br />{t('import_catalog_before')}<code className="text-blue-400">just seed-catalog</code>{t('import_catalog_after')}
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
          {file ? `${file.name} ${isCsv ? t('import_csv_label') : t('import_xlsx_label')}` : t('import_pick_file')}
        </button>

        {mut.isSuccess && (
          <div className="bg-green-900/30 border border-green-700 rounded-lg p-3 text-sm text-green-400">
            <p><strong>{mut.data.data.imported}</strong> {t('import_done')}</p>
            {mut.data.data.skipped > 0 && <p><strong>{mut.data.data.skipped}</strong> {t('import_skipped')}</p>}
          </div>
        )}
        {mut.isError && (
          <p className="text-red-400 text-sm">{t('import_error')} {(mut.error as AxiosError<{ detail: string }>)?.response?.data?.detail || t('import_unknown_error')}</p>
        )}

        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors">{t('common:cancel')}</button>
          <button
            onClick={() => file && mut.mutate(file)}
            disabled={!file || mut.isPending}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {mut.isPending ? t('importing') : t('import_action')}
          </button>
        </div>
      </div>
    </div>
  )
}

function FormatGuideModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation('tags')
  const examples = [
    { addr: 'DB301,DD7890', desc: t('format_desc_db301') },
    { addr: 'DB310,DBW90', desc: t('format_desc_db310') },
    { addr: 'Q254.1', desc: t('format_desc_q254') },
    { addr: 'DB1,REAL0', desc: t('format_desc_db1') },
    { addr: 'DB5,BOOL10.3', desc: t('format_desc_db5') },
  ]
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">{t('format_modal_title')}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        <p className="text-gray-400 text-sm">{t('format_intro')}</p>
        <div className="bg-gray-800 rounded-lg p-4 space-y-2">
          {examples.map(({ addr, desc }) => (
            <div key={addr} className="flex items-baseline gap-3">
              <span className="text-blue-400 font-mono text-sm w-32 flex-shrink-0">{addr}</span>
              <span className="text-gray-500 text-xs">{desc}</span>
            </div>
          ))}
        </div>
        <p className="text-gray-600 text-xs">{t('format_operands')}</p>
        <button onClick={onClose} className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors">{t('ok')}</button>
      </div>
    </div>
  )
}

function GroupsModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation(['tags', 'common'])
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

  // resolve parent name for single-level indentation
  const nameOf = (id: number | null) => groups.find((g) => g.id === id)?.name ?? null
  const inputCls = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">{t('groups_modal_title')}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        <p className="text-gray-400 text-sm">
          {t('groups_desc_before')}<strong className="text-gray-300">{t('groups_auto')}</strong>{t('groups_desc_after')}
        </p>

        <div className="bg-gray-800/40 border border-gray-700 rounded-lg p-3 space-y-2">
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder={t('groups_new_name')} />
          <select className={inputCls} value={parentId ?? ''} onChange={(e) => setParentId(e.target.value === '' ? null : Number(e.target.value))}>
            <option value="">{t('groups_parent_root')}</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <button
            onClick={() => createMut.mutate()}
            disabled={!name.trim() || createMut.isPending}
            className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {createMut.isPending ? t('adding') : t('groups_add')}
          </button>
        </div>

        <div className="max-h-64 overflow-y-auto space-y-1">
          {groups.length === 0 && <p className="text-gray-500 text-sm text-center py-4">{t('groups_none')}</p>}
          {groups.map((g) => (
            <div key={g.id} className="flex items-center justify-between bg-gray-800/40 rounded-lg px-3 py-2">
              <span className="text-sm text-gray-200">
                {g.parent_id != null && <span className="text-gray-600">{nameOf(g.parent_id)} / </span>}
                {g.name}
              </span>
              <button
                onClick={() => { if (confirm(t('groups_confirm_delete', { name: g.name }))) delMut.mutate(g.id) }}
                className="text-gray-500 hover:text-red-400 text-xs px-2"
              >
                {t('common:delete')}
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
  const { t } = useTranslation(['tags', 'common'])
  return (
    <div className="flex items-center gap-2 py-1.5 pe-2 hover:bg-gray-800/40 rounded-lg" style={{ paddingInlineStart: indent }}>
      <span className="w-1.5 h-1.5 rounded-full bg-gray-600 flex-shrink-0" />
      <span className="text-sm text-white truncate flex-1">{tag.name}</span>
      <span className="text-xs font-mono text-gray-600 hidden sm:inline">{tag.s7_address ?? '—'}</span>
      <span className="text-xs text-gray-500 w-10 text-end">{tag.unit}</span>
      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${tag.is_active ? 'bg-green-900/50 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
        {tag.is_active ? t('status_active') : t('status_passive')}
      </span>
      {canEdit && (
        <div className="flex gap-1">
          <button onClick={() => onEdit(tag)} title={t('common:edit')} className="p-1 rounded text-gray-500 hover:text-blue-400 hover:bg-blue-500/10">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
          </button>
          <button onClick={() => onDelete(tag)} title={t('common:delete')} className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-red-500/10">
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
  // total tag count in the subtree (for the badge)
  const count = (n: GroupNode): number => n.tag_ids.length + n.children.reduce((s, c) => s + count(c), 0)
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1.5 py-1.5 text-sm text-gray-200 hover:text-white"
        style={{ paddingInlineStart: depth * 16 + 4 }}
      >
        <span className="text-gray-500 w-3">{open ? '▾' : '▸'}</span>
        <svg className="w-4 h-4 text-indigo-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" /></svg>
        <span className="font-medium truncate">{node.name}</span>
        <span className="text-xs text-gray-600 ms-1">{count(node)}</span>
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
  const { t } = useTranslation(['tags', 'common'])
  const { data: tree = [], isLoading } = useQuery({
    queryKey: ['groupTree', source],
    queryFn: () => getGroupTree(source).then((r) => r.data),
  })
  const tagMap = new Map(tags.map((t) => [t.id, t]))
  const ungrouped = source === 'manual' ? tags.filter((t) => t.group_id === null) : []

  if (isLoading) return <div className="py-12 text-center text-gray-500">{t('common:loading')}</div>
  return (
    <div className="p-2 space-y-0.5">
      {tree.length === 0 && ungrouped.length === 0 && (
        <p className="py-8 text-center text-gray-500 text-sm">
          {source === 'manual' ? t('tree_no_group') : t('tree_no_tag')}
        </p>
      )}
      {tree.map((n, i) => (
        <TagTreeNode key={n.id ?? `root-${i}`} node={n} tagMap={tagMap} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} depth={0} />
      ))}
      {ungrouped.length > 0 && (
        <div className="pt-2 mt-2 border-t border-gray-800">
          <p className="text-xs text-gray-500 uppercase tracking-wide px-2 py-1">{t('ungrouped_count', { value: ungrouped.length })}</p>
          {ungrouped.map((t) => (
            <TagRow key={t.id} tag={t} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} indent={22} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function Tags() {
  const { t } = useTranslation(['tags', 'common'])
  const { user, can } = useAuth()
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
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const PAGE_SIZE_OPTIONS = [25, 50, 100, 200]

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
  const handleDelete = (tag: Tag) => { if (confirm(t('confirm_delete', { name: tag.name }))) delMut.mutate(tag.id) }

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

  // Client-side pagination for the table view — rendering all ~3000 rows at once
  // freezes the page, so only one page of rows is mounted at a time.
  const total = sorted.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const pageClamped = Math.min(page, totalPages)
  const pageRows = sorted.slice((pageClamped - 1) * pageSize, pageClamped * pageSize)

  // Reset to the first page whenever the result set or page size changes.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPage(1)
  }, [search, groupFilter, pageSize])

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">{t('title')}</h1>
        <div className="flex gap-2 flex-wrap">
          <div className="flex">
            <button onClick={() => doExport('csv')} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-s-lg border border-gray-700 transition-colors">
              {t('export_csv')}
            </button>
            <button onClick={() => doExport('xlsx')} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-e-lg border border-s-0 border-gray-700 transition-colors">
              {t('export_xlsx')}
            </button>
          </div>
          {canEdit && (
            <>
              <button onClick={() => setShowGroups(true)} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors">
                {t('groups_btn')}
              </button>
              <button onClick={() => setShowImport(true)} className="px-3 py-2 text-sm bg-green-800 hover:bg-green-700 text-green-300 rounded-lg border border-green-700 transition-colors">
                {t('import_btn')}
              </button>
              <button onClick={() => setShowFormat(true)} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors">
                {t('format_btn')}
              </button>
              {can('tag:create') && (
                <button onClick={() => setShowAdd(true)} className="px-3 py-2 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">
                  {t('add_tag_btn')}
                </button>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('search_placeholder')}
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
            title={t('filter_by_group')}
          >
            <option value="all">{t('all_groups')}</option>
            <option value="none">{t('ungrouped')}</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        )}
        {/* Table / Tree view switch */}
        <div className="flex bg-gray-900 border border-gray-800 rounded-xl p-0.5">
          <button
            onClick={() => setViewMode('table')}
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${viewMode === 'table' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
            title={t('view_table_title')}
          >
            {t('view_table')}
          </button>
          <button
            onClick={() => setViewMode('tree')}
            className={`px-3 py-2 text-sm rounded-lg transition-colors ${viewMode === 'tree' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
            title={t('view_tree_title')}
          >
            {t('view_tree')}
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
                {s === 'manual' ? t('source_manual') : t('source_auto')}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {viewMode === 'tree' ? (
          <TagTreeView source={treeSource} tags={tags} canEdit={canEdit} onEdit={setEditTag} onDelete={handleDelete} />
        ) : isLoading ? (
          <div className="py-12 text-center text-gray-500">{t('common:loading')}</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-gray-400">{search ? t('no_match') : t('no_tags')}</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="border-b border-gray-800">
              <tr className="text-xs text-gray-500 uppercase tracking-wide">
                {[
                  { label: t('col_plc'), key: 'plc' },
                  { label: t('col_name'), key: 'name' },
                  { label: t('col_plc_ip'), key: 'plc_ip' },
                  { label: t('col_s7_address'), key: 's7_address' },
                  { label: t('col_interval'), key: 'sample_interval' },
                  { label: t('col_unit'), key: 'unit' },
                  { label: t('col_group'), key: 'group_id' },
                  { label: t('col_status'), key: 'is_active' },
                ].map((c) => (
                  <SortHeader key={c.key} label={c.label} sortKey={c.key} sort={sort} onToggle={toggle} className="px-4 py-3" />
                ))}
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row: Tag) => (
                <tr key={row.id} className="border-t border-gray-800 hover:bg-gray-800/40">
                  <td className="px-4 py-3 text-sm text-gray-400">{row.plc_name || row.device}</td>
                  <td className="px-4 py-3 text-sm font-medium text-white">
                    {row.name}
                    {row.long_term && <span className="ms-2 text-[10px] px-1.5 py-0.5 rounded bg-blue-900/50 text-blue-300">{t('badge_long_term')}</span>}
                    {row.daily_tracking && <span className="ms-1 text-[10px] px-1.5 py-0.5 rounded bg-purple-900/50 text-purple-300">{t('badge_daily')}</span>}
                  </td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-500">{row.plc_ip ?? '—'}</td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-500">{row.s7_address ?? '—'}</td>
                  <td className="px-4 py-3 text-sm text-gray-400">{row.sample_interval}s</td>
                  <td className="px-4 py-3 text-sm text-gray-300">{row.unit}</td>
                  <td className="px-4 py-3 text-sm">
                    {groupName(row.group_id)
                      ? <span className="text-[11px] px-1.5 py-0.5 rounded bg-indigo-900/40 text-indigo-300">{groupName(row.group_id)}</span>
                      : <span className="text-gray-600">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${row.is_active ? 'bg-green-900/50 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
                      {row.is_active ? t('status_active') : t('status_passive')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-end">
                    {canEdit && (
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => setEditTag(row)}
                          title={t('common:edit')}
                          className="p-1.5 rounded-lg text-gray-400 hover:text-blue-400 hover:bg-blue-500/10 border border-gray-700 hover:border-blue-500/40 transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => { if (confirm(t('confirm_delete', { name: row.name }))) delMut.mutate(row.id) }}
                          title={t('common:delete')}
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

      {viewMode === 'table' && !isLoading && total > 0 && (
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">
              {t('pagination_showing', {
                from: (pageClamped - 1) * pageSize + 1,
                to: Math.min(pageClamped * pageSize, total),
                total,
              })}
            </span>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-gray-500">{t('per_page')}</span>
              <select
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
                className="bg-gray-900 border border-gray-800 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                {PAGE_SIZE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center gap-3">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={pageClamped === 1}
                className="px-3 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-lg border border-gray-700 disabled:opacity-40 hover:bg-gray-700 transition-colors"
              >
                {t('prev')}
              </button>
              <div className="flex items-center gap-1.5 text-sm text-gray-400">
                <select
                  value={pageClamped}
                  onChange={(e) => setPage(Number(e.target.value))}
                  title={t('go_to_page')}
                  className="bg-gray-900 border border-gray-800 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
                >
                  {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
                <span>/ {totalPages}</span>
              </div>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={pageClamped === totalPages}
                className="px-3 py-1.5 text-sm bg-gray-800 text-gray-300 rounded-lg border border-gray-700 disabled:opacity-40 hover:bg-gray-700 transition-colors"
              >
                {t('next')}
              </button>
            </div>
          )}
        </div>
      )}

      {showAdd && <AddTagModal onClose={() => setShowAdd(false)} />}
      {showImport && <ImportTagModal onClose={() => setShowImport(false)} />}
      {showFormat && <FormatGuideModal onClose={() => setShowFormat(false)} />}
      {showGroups && <GroupsModal onClose={() => setShowGroups(false)} />}
      {editTag && <EditTagModal tag={editTag} groups={groups} onClose={() => setEditTag(null)} />}
    </div>
  )
}
