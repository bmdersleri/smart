import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getPermit,
  updatePermit,
  createPoint,
  updatePoint,
  deletePoint,
  createParameterCompliance,
  updateParameterCompliance,
  deleteParameterCompliance,
  createLimit,
  updateLimit,
  deleteLimit,
  getTags,
  listLabParameters,
  type CompliancePermitDetail,
  type CompliancePointPayload,
  type ComplianceParameterPayload,
  type ComplianceParameterWithLimits,
  type ComplianceLimitPayload,
} from '../../api/client'
import { Card } from './helpers'
import {
  REPORT_FREQUENCIES,
  SOURCE_TYPES,
  LIMIT_TYPES,
  AGGREGATIONS,
  SEVERITIES,
} from './constants'

interface Props {
  permitId: number
  isAdmin: boolean
  onDelete: () => void
}

export default function PermitDetail({ permitId, isAdmin, onDelete }: Props) {
  const { t } = useTranslation(['compliance', 'common'])
  const qc = useQueryClient()
  const [err, setErr] = useState('')

  const { data: permit, isLoading } = useQuery({
    queryKey: ['compliance-permit', permitId],
    queryFn: () => getPermit(permitId).then((r) => r.data),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['compliance-permit', permitId] })
    qc.invalidateQueries({ queryKey: ['compliance-permits'] })
  }
  const onErr = (e: unknown) => {
    const ax = e as { response?: { data?: { detail?: string } } }
    setErr(ax.response?.data?.detail || t('save_error'))
  }

  if (isLoading || !permit)
    return <Card className="p-8 text-center text-gray-500 text-sm">{t('common:loading')}</Card>

  return (
    <div className="space-y-4">
      {/* key forces a fresh form state whenever the permit data changes. */}
      <MetadataSection
        key={`meta-${permit.id}-${permit.updated_at}`}
        permit={permit}
        isAdmin={isAdmin}
        onSaved={invalidate}
        onErr={onErr}
        onDelete={onDelete}
      />
      <PointsSection permit={permit} isAdmin={isAdmin} onChanged={invalidate} onErr={onErr} />
      <ParametersSection permit={permit} isAdmin={isAdmin} onChanged={invalidate} onErr={onErr} />
      {err && <p className="text-xs text-red-400">{err}</p>}
    </div>
  )
}

// ── Metadata ──────────────────────────────────────────────────────────────────
function MetadataSection({
  permit,
  isAdmin,
  onSaved,
  onErr,
  onDelete,
}: {
  permit: CompliancePermitDetail
  isAdmin: boolean
  onSaved: () => void
  onErr: (e: unknown) => void
  onDelete: () => void
}) {
  const { t } = useTranslation(['compliance', 'common'])
  const [edit, setEdit] = useState(false)
  const [form, setForm] = useState({
    name: permit.name,
    facility_name: permit.facility_name,
    authority: permit.authority,
    permit_number: permit.permit_number,
    report_frequency: permit.report_frequency,
    is_active: permit.is_active,
  })

  const saveMut = useMutation({
    mutationFn: () => updatePermit(permit.id, form),
    onSuccess: () => {
      onSaved()
      setEdit(false)
    },
    onError: onErr,
  })

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-medium text-white">{t('metadata')}</h3>
        {isAdmin && (
          <div className="flex gap-2">
            <button className="text-cyan-400 text-sm" onClick={() => setEdit((v) => !v)}>
              {t('common:edit')}
            </button>
            <button className="text-red-400 text-sm" onClick={onDelete}>
              {t('deactivate')}
            </button>
          </div>
        )}
      </div>

      {edit && isAdmin ? (
        <div className="grid gap-2 max-w-md">
          <input
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            placeholder={t('permit_name')}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            placeholder={t('facility_name')}
            value={form.facility_name}
            onChange={(e) => setForm({ ...form, facility_name: e.target.value })}
          />
          <input
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            placeholder={t('authority')}
            value={form.authority}
            onChange={(e) => setForm({ ...form, authority: e.target.value })}
          />
          <input
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            placeholder={t('permit_number')}
            value={form.permit_number}
            onChange={(e) => setForm({ ...form, permit_number: e.target.value })}
          />
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            value={form.report_frequency}
            onChange={(e) => setForm({ ...form, report_frequency: e.target.value })}
            aria-label={t('report_frequency')}
          >
            {REPORT_FREQUENCIES.map((f) => (
              <option key={f} value={f}>
                {t(`freq_${f}`)}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            {t('active')}
          </label>
          <button
            className="bg-blue-600 hover:bg-blue-500 px-3 py-1.5 rounded text-sm text-white disabled:opacity-50"
            disabled={!form.name.trim() || saveMut.isPending}
            onClick={() => saveMut.mutate()}
          >
            {t('common:save')}
          </button>
        </div>
      ) : (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <Field label={t('facility_name')} value={permit.facility_name} />
          <Field label={t('authority')} value={permit.authority} />
          <Field label={t('permit_number')} value={permit.permit_number} />
          <Field label={t('report_frequency')} value={t(`freq_${permit.report_frequency}`, permit.report_frequency)} />
          <Field label={t('status')} value={permit.is_active ? t('active') : t('inactive')} />
        </dl>
      )}
    </Card>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-gray-500">{label}</dt>
      <dd className="text-gray-200">{value || '—'}</dd>
    </>
  )
}

// ── Discharge / sample points ───────────────────────────────────────────────────
const EMPTY_POINT: CompliancePointPayload = { code: '', name: '', description: '' }

function PointsSection({
  permit,
  isAdmin,
  onChanged,
  onErr,
}: {
  permit: CompliancePermitDetail
  isAdmin: boolean
  onChanged: () => void
  onErr: (e: unknown) => void
}) {
  const { t } = useTranslation(['compliance', 'common'])
  const [form, setForm] = useState<CompliancePointPayload>(EMPTY_POINT)
  const [editId, setEditId] = useState<number | null>(null)

  const createMut = useMutation({
    mutationFn: () => createPoint(permit.id, form),
    onSuccess: () => {
      onChanged()
      setForm(EMPTY_POINT)
    },
    onError: onErr,
  })
  const updateMut = useMutation({
    mutationFn: (id: number) => updatePoint(id, form),
    onSuccess: () => {
      onChanged()
      setForm(EMPTY_POINT)
      setEditId(null)
    },
    onError: onErr,
  })
  const delMut = useMutation({ mutationFn: deletePoint, onSuccess: onChanged, onError: onErr })

  return (
    <Card className="p-4">
      <h3 className="font-medium text-white mb-2">{t('points')}</h3>
      <table className="w-full text-sm mb-3">
        <thead>
          <tr className="text-xs text-gray-500 uppercase tracking-wide">
            <th className="text-start py-1">{t('code')}</th>
            <th className="text-start py-1">{t('name')}</th>
            <th className="text-start py-1">{t('description')}</th>
            {isAdmin && <th />}
          </tr>
        </thead>
        <tbody>
          {permit.discharge_points.map((p) => (
            <tr key={p.id} className="border-t border-edge">
              <td className="py-1 text-gray-300 font-mono">{p.code}</td>
              <td className="py-1 text-gray-200">{p.name}</td>
              <td className="py-1 text-gray-400 text-xs">{p.description || '—'}</td>
              {isAdmin && (
                <td className="py-1 text-end space-x-2">
                  <button
                    className="text-cyan-400 text-xs"
                    onClick={() => {
                      setEditId(p.id)
                      setForm({ code: p.code, name: p.name, description: p.description, lab_sample_point_id: p.lab_sample_point_id })
                    }}
                  >
                    {t('common:edit')}
                  </button>
                  <button
                    className="text-red-400 text-xs"
                    onClick={() => {
                      if (confirm(t('confirm_delete'))) delMut.mutate(p.id)
                    }}
                  >
                    {t('common:delete')}
                  </button>
                </td>
              )}
            </tr>
          ))}
          {permit.discharge_points.length === 0 && (
            <tr>
              <td colSpan={isAdmin ? 4 : 3} className="py-3 text-center text-gray-500 text-xs">
                {t('no_points')}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {isAdmin && (
        <div className="flex flex-wrap gap-2 items-end">
          <input
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm w-24"
            placeholder={t('code')}
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
          />
          <input
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            placeholder={t('name')}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm flex-1"
            placeholder={t('description')}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <button
            className="bg-blue-600 hover:bg-blue-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
            disabled={!form.code.trim() || !form.name.trim()}
            onClick={() => (editId ? updateMut.mutate(editId) : createMut.mutate())}
          >
            {editId ? t('common:save') : t('common:add')}
          </button>
          {editId && (
            <button
              className="text-gray-400 text-sm px-2"
              onClick={() => {
                setEditId(null)
                setForm(EMPTY_POINT)
              }}
            >
              {t('common:cancel')}
            </button>
          )}
        </div>
      )}
    </Card>
  )
}

// ── Parameters + source mapping ─────────────────────────────────────────────────
const EMPTY_PARAM: ComplianceParameterPayload = {
  discharge_point_id: 0,
  parameter_name: '',
  unit: '',
  source_type: 'scada',
  tag_id: null,
  lab_parameter_id: null,
}

// Enforce the same source-mapping required-field rules the backend validates.
function sourceMappingError(p: ComplianceParameterPayload): string | null {
  if (p.source_type === 'scada' && !p.tag_id) return 'scada_needs_tag'
  if (p.source_type === 'lab' && !p.lab_parameter_id) return 'lab_needs_param'
  if (p.source_type === 'hybrid' && (!p.tag_id || !p.lab_parameter_id)) return 'hybrid_needs_both'
  return null
}

function ParametersSection({
  permit,
  isAdmin,
  onChanged,
  onErr,
}: {
  permit: CompliancePermitDetail
  isAdmin: boolean
  onChanged: () => void
  onErr: (e: unknown) => void
}) {
  const { t } = useTranslation(['compliance', 'common'])
  const [form, setForm] = useState<ComplianceParameterPayload>(EMPTY_PARAM)
  const [editId, setEditId] = useState<number | null>(null)
  const [localErr, setLocalErr] = useState('')

  const { data: tags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
    enabled: isAdmin,
  })
  const { data: labParams = [] } = useQuery({
    queryKey: ['lab-parameters'],
    queryFn: () => listLabParameters().then((r) => r.data),
    enabled: isAdmin,
  })

  const resetForm = () => {
    setForm({ ...EMPTY_PARAM, discharge_point_id: permit.discharge_points[0]?.id ?? 0 })
    setEditId(null)
    setLocalErr('')
  }

  const createMut = useMutation({
    mutationFn: () => createParameterCompliance(permit.id, form),
    onSuccess: () => {
      onChanged()
      resetForm()
    },
    onError: onErr,
  })
  const updateMut = useMutation({
    mutationFn: (id: number) => updateParameterCompliance(id, form),
    onSuccess: () => {
      onChanged()
      resetForm()
    },
    onError: onErr,
  })
  const delMut = useMutation({
    mutationFn: deleteParameterCompliance,
    onSuccess: onChanged,
    onError: onErr,
  })

  const submit = () => {
    setLocalErr('')
    if (!form.parameter_name.trim()) return
    if (!form.discharge_point_id) {
      setLocalErr(t('need_point'))
      return
    }
    const mapErr = sourceMappingError(form)
    if (mapErr) {
      setLocalErr(t(mapErr))
      return
    }
    if (editId) updateMut.mutate(editId)
    else createMut.mutate()
  }

  const startEdit = (p: ComplianceParameterWithLimits) => {
    setEditId(p.id)
    setForm({
      discharge_point_id: p.discharge_point_id,
      parameter_name: p.parameter_name,
      unit: p.unit,
      source_type: p.source_type,
      tag_id: p.tag_id,
      lab_parameter_id: p.lab_parameter_id,
    })
  }

  return (
    <Card className="p-4">
      <h3 className="font-medium text-white mb-2">{t('parameters')}</h3>

      <div className="space-y-3 mb-3">
        {permit.parameters.map((p) => (
          <div key={p.id} className="border border-edge rounded-lg p-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-gray-200 font-medium">{p.parameter_name}</span>
                <span className="text-gray-500 text-xs ms-2">
                  {p.unit} · {t(`source_${p.source_type}`)}
                </span>
              </div>
              {isAdmin && (
                <div className="space-x-2">
                  <button className="text-cyan-400 text-xs" onClick={() => startEdit(p)}>
                    {t('common:edit')}
                  </button>
                  <button
                    className="text-red-400 text-xs"
                    onClick={() => {
                      if (confirm(t('confirm_delete'))) delMut.mutate(p.id)
                    }}
                  >
                    {t('common:delete')}
                  </button>
                </div>
              )}
            </div>
            <LimitsSection parameter={p} isAdmin={isAdmin} onChanged={onChanged} onErr={onErr} />
          </div>
        ))}
        {permit.parameters.length === 0 && (
          <p className="text-center text-gray-500 text-xs py-3">{t('no_parameters')}</p>
        )}
      </div>

      {isAdmin && (
        <div className="border-t border-edge pt-3 grid gap-2 max-w-md">
          <p className="text-xs text-gray-500 uppercase tracking-wide">
            {editId ? t('edit_parameter') : t('add_parameter')}
          </p>
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            value={form.discharge_point_id || ''}
            onChange={(e) => setForm({ ...form, discharge_point_id: Number(e.target.value) })}
            aria-label={t('discharge_point')}
          >
            <option value="">{t('select_point')}</option>
            {permit.discharge_points.map((pt) => (
              <option key={pt.id} value={pt.id}>
                {pt.code} — {pt.name}
              </option>
            ))}
          </select>
          <input
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            placeholder={t('parameter_name')}
            value={form.parameter_name}
            onChange={(e) => setForm({ ...form, parameter_name: e.target.value })}
          />
          <input
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            placeholder={t('unit')}
            value={form.unit}
            onChange={(e) => setForm({ ...form, unit: e.target.value })}
          />
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
            value={form.source_type}
            onChange={(e) => setForm({ ...form, source_type: e.target.value })}
            aria-label={t('source_type')}
          >
            {SOURCE_TYPES.map((s) => (
              <option key={s} value={s}>
                {t(`source_${s}`)}
              </option>
            ))}
          </select>
          {(form.source_type === 'scada' || form.source_type === 'hybrid') && (
            <select
              className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
              value={form.tag_id ?? ''}
              onChange={(e) => setForm({ ...form, tag_id: e.target.value ? Number(e.target.value) : null })}
              aria-label={t('scada_tag')}
            >
              <option value="">{t('select_tag')}</option>
              {tags.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
                </option>
              ))}
            </select>
          )}
          {(form.source_type === 'lab' || form.source_type === 'hybrid') && (
            <select
              className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-sm"
              value={form.lab_parameter_id ?? ''}
              onChange={(e) =>
                setForm({ ...form, lab_parameter_id: e.target.value ? Number(e.target.value) : null })
              }
              aria-label={t('lab_parameter')}
            >
              <option value="">{t('select_lab_parameter')}</option>
              {labParams.map((lp) => (
                <option key={lp.id} value={lp.id}>
                  {lp.name}
                </option>
              ))}
            </select>
          )}
          <div className="flex gap-2">
            <button
              className="bg-blue-600 hover:bg-blue-500 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
              disabled={createMut.isPending || updateMut.isPending}
              onClick={submit}
            >
              {editId ? t('common:save') : t('common:add')}
            </button>
            {editId && (
              <button className="text-gray-400 text-sm px-2" onClick={resetForm}>
                {t('common:cancel')}
              </button>
            )}
          </div>
          {localErr && <p className="text-xs text-red-400">{localErr}</p>}
        </div>
      )}
    </Card>
  )
}

// ── Limit rules per parameter ────────────────────────────────────────────────────
const EMPTY_LIMIT: ComplianceLimitPayload = {
  limit_type: 'value_limit',
  min_value: null,
  max_value: null,
  aggregation: 'instant',
  severity: 'warning',
  requires_explanation: false,
}

function LimitsSection({
  parameter,
  isAdmin,
  onChanged,
  onErr,
}: {
  parameter: ComplianceParameterWithLimits
  isAdmin: boolean
  onChanged: () => void
  onErr: (e: unknown) => void
}) {
  const { t } = useTranslation(['compliance', 'common'])
  const [form, setForm] = useState<ComplianceLimitPayload>(EMPTY_LIMIT)
  const [editId, setEditId] = useState<number | null>(null)
  const [open, setOpen] = useState(false)

  const reset = () => {
    setForm(EMPTY_LIMIT)
    setEditId(null)
  }
  const createMut = useMutation({
    mutationFn: () => createLimit(parameter.id, form),
    onSuccess: () => {
      onChanged()
      reset()
    },
    onError: onErr,
  })
  const updateMut = useMutation({
    mutationFn: (id: number) => updateLimit(id, form),
    onSuccess: () => {
      onChanged()
      reset()
    },
    onError: onErr,
  })
  const delMut = useMutation({ mutationFn: deleteLimit, onSuccess: onChanged, onError: onErr })

  return (
    <div className="mt-2 ps-1">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 uppercase tracking-wide">
          {t('limits')} ({parameter.limits.length})
        </p>
        {isAdmin && (
          <button className="text-cyan-400 text-xs" onClick={() => setOpen((v) => !v)}>
            {open ? t('common:cancel') : t('add_limit')}
          </button>
        )}
      </div>

      {parameter.limits.length > 0 && (
        <ul className="text-xs text-gray-400 mt-1 space-y-1">
          {parameter.limits.map((l) => (
            <li key={l.id} className="flex items-center justify-between">
              <span className="font-mono">
                {t(`limit_${l.limit_type}`)} · {t(`agg_${l.aggregation}`)} · min={l.min_value ?? '—'} max=
                {l.max_value ?? '—'} · {t(`severity_${l.severity}`, l.severity)}
                {l.requires_explanation ? ` · ${t('requires_explanation_short')}` : ''}
              </span>
              {isAdmin && (
                <span className="space-x-2 shrink-0 ms-2">
                  <button
                    className="text-cyan-400"
                    onClick={() => {
                      setEditId(l.id)
                      setOpen(true)
                      setForm({
                        limit_type: l.limit_type,
                        min_value: l.min_value,
                        max_value: l.max_value,
                        aggregation: l.aggregation,
                        window: l.window,
                        sample_frequency: l.sample_frequency,
                        severity: l.severity,
                        requires_explanation: l.requires_explanation,
                      })
                    }}
                  >
                    {t('common:edit')}
                  </button>
                  <button
                    className="text-red-400"
                    onClick={() => {
                      if (confirm(t('confirm_delete'))) delMut.mutate(l.id)
                    }}
                  >
                    {t('common:delete')}
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {isAdmin && open && (
        <div className="grid grid-cols-2 gap-2 mt-2">
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-xs"
            value={form.limit_type}
            onChange={(e) => setForm({ ...form, limit_type: e.target.value })}
            aria-label={t('limit_type')}
          >
            {LIMIT_TYPES.map((l) => (
              <option key={l} value={l}>
                {t(`limit_${l}`)}
              </option>
            ))}
          </select>
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-xs"
            value={form.aggregation}
            onChange={(e) => setForm({ ...form, aggregation: e.target.value })}
            aria-label={t('aggregation')}
          >
            {AGGREGATIONS.map((a) => (
              <option key={a} value={a}>
                {t(`agg_${a}`)}
              </option>
            ))}
          </select>
          <input
            type="number"
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-xs"
            placeholder={t('min_value')}
            value={form.min_value ?? ''}
            onChange={(e) => setForm({ ...form, min_value: e.target.value === '' ? null : Number(e.target.value) })}
          />
          <input
            type="number"
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-xs"
            placeholder={t('max_value')}
            value={form.max_value ?? ''}
            onChange={(e) => setForm({ ...form, max_value: e.target.value === '' ? null : Number(e.target.value) })}
          />
          <select
            className="bg-surface-sunken px-2 py-1 rounded text-gray-200 text-xs"
            value={form.severity}
            onChange={(e) => setForm({ ...form, severity: e.target.value })}
            aria-label={t('severity')}
          >
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {t(`severity_${s}`)}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-xs text-gray-300">
            <input
              type="checkbox"
              checked={form.requires_explanation}
              onChange={(e) => setForm({ ...form, requires_explanation: e.target.checked })}
            />
            {t('requires_explanation')}
          </label>
          <button
            className="bg-blue-600 hover:bg-blue-500 px-3 py-1 rounded text-xs text-white col-span-2 disabled:opacity-50"
            disabled={createMut.isPending || updateMut.isPending}
            onClick={() => (editId ? updateMut.mutate(editId) : createMut.mutate())}
          >
            {editId ? t('common:save') : t('common:add')}
          </button>
        </div>
      )}
    </div>
  )
}
