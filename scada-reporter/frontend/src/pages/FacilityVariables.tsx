import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { Variable } from 'lucide-react'
import {
  listFacilityVariables,
  deleteFacilityVariable,
  createFacilityVariable,
  updateFacilityVariable,
  getTags,
} from '../api/client'
import type { FacilityVariable, ExprNode } from '../api/client'
import { useAuth } from '../context/AuthContext'
import ExpressionBuilder, { emptyNode } from './facilityVariables/ExpressionBuilder'
import PreviewPanel from './facilityVariables/PreviewPanel'

export function VariableEditorModal({ initial, onClose }: { initial?: FacilityVariable; onClose: () => void }) {
  const { t } = useTranslation(['facilityVariables', 'common'])
  const qc = useQueryClient()
  const [code, setCode] = useState(initial?.code ?? '')
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [kind, setKind] = useState<'scalar' | 'series'>(initial?.kind ?? 'scalar')
  const [unit, setUnit] = useState(initial?.unit ?? '')
  const [grain, setGrain] = useState(initial?.default_time_grain ?? 'day')
  const [expression, setExpression] = useState<ExprNode>(initial?.expression ?? emptyNode('const'))

  const { data: tags = [] } = useQuery({ queryKey: ['tags'], queryFn: () => getTags().then((r) => r.data) })
  const { data: variables = [] } = useQuery({
    queryKey: ['facility-variables'],
    queryFn: () => listFacilityVariables().then((r) => r.data),
  })

  const mut = useMutation({
    mutationFn: () => {
      if (initial) {
        return updateFacilityVariable(initial.id, {
          name, description, unit, expression, default_time_grain: grain,
        }).then((r) => r.data)
      }
      return createFacilityVariable({
        code, name, description, kind, unit, expression, default_time_grain: grain,
      }).then((r) => r.data)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['facility-variables'] }); onClose() },
  })

  const errDetail = (mut.error as AxiosError<{ detail: string }>)?.response?.data?.detail
  const status = (mut.error as AxiosError)?.response?.status
  const inputCls = 'w-full bg-surface-sunken border border-edge-strong rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-hidden focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl w-full max-w-2xl p-6 space-y-4 my-8">
        <h2 className="text-lg font-semibold text-white">{t(initial ? 'edit_title' : 'create_title')}</h2>

        <section className="space-y-2">
          <h3 className="text-xs uppercase text-gray-500">{t('step_basic')}</h3>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_code')}</span>
              <input aria-label={t('field_code')} className={inputCls} value={code} disabled={!!initial}
                onChange={(e) => setCode(e.target.value)} />
            </label>
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_name')}</span>
              <input aria-label={t('field_name')} className={inputCls} value={name}
                onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_kind')}</span>
              <select className={inputCls} value={kind} disabled={!!initial}
                onChange={(e) => setKind(e.target.value as 'scalar' | 'series')}>
                <option value="scalar">{t('kind_scalar')}</option>
                <option value="series">{t('kind_series')}</option>
              </select>
            </label>
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_unit')}</span>
              <input className={inputCls} value={unit} onChange={(e) => setUnit(e.target.value)} />
            </label>
            <label className="text-xs text-gray-400 space-y-1 col-span-2">
              <span>{t('field_description')}</span>
              <input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} />
            </label>
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_grain')}</span>
              <select className={inputCls} value={grain ?? 'day'} onChange={(e) => setGrain(e.target.value)}>
                {['hour', 'day', 'week', 'month'].map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
          </div>
        </section>

        <section className="space-y-2">
          <h3 className="text-xs uppercase text-gray-500">{t('step_expression')}</h3>
          <ExpressionBuilder value={expression} onChange={setExpression}
            tags={tags} variables={variables.map((v) => ({ id: v.id, code: v.code }))} />
        </section>

        {initial && (
          <section className="space-y-2">
            <h3 className="text-xs uppercase text-gray-500">{t('step_preview')}</h3>
            <PreviewPanel variableId={initial.id} kind={kind} />
          </section>
        )}

        {mut.isError && (
          <p className="text-red-400 text-sm">
            {status === 409 ? t('error_duplicate_code') : errDetail || t('error_generic')}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
            {t('common:cancel')}
          </button>
          <button onClick={() => mut.mutate()} disabled={mut.isPending || !code || !name}
            className="px-4 py-2 rounded-lg bg-cyan-600/30 border border-cyan-500/40 text-cyan-200 text-sm disabled:opacity-40">
            {mut.isPending ? t('saving') : t('save')}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function FacilityVariables() {
  const { t } = useTranslation(['facilityVariables', 'common'])
  const { can } = useAuth()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editVar, setEditVar] = useState<FacilityVariable | null>(null)

  const { data: vars = [], isLoading } = useQuery({
    queryKey: ['facility-variables'],
    queryFn: () => listFacilityVariables().then((r) => r.data),
  })

  const delMut = useMutation({
    mutationFn: (v: FacilityVariable) => deleteFacilityVariable(v.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['facility-variables'] }),
  })

  const handleDeactivate = (v: FacilityVariable) => {
    if (!confirm(t('confirm_deactivate', { name: v.name }))) return
    delMut.mutate(v, {
      onError: (e) => {
        const status = (e as AxiosError)?.response?.status
        alert(status === 409 ? t('deactivate_blocked') : t('error_generic'))
      },
    })
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white flex items-center gap-2">
            <Variable className="w-5 h-5 text-emerald-400" /> {t('title')}
          </h1>
          <p className="text-sm text-gray-400">{t('subtitle')}</p>
        </div>
        {can('facility_variable:create') && (
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 rounded-lg bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 text-sm hover:bg-emerald-600/30"
          >
            {t('add')}
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-gray-500">{t('common:loading')}</div>
      ) : vars.length === 0 ? (
        <div className="py-12 text-center text-gray-500">{t('empty')}</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-start border-b border-edge text-gray-400">
              <th className="text-start py-2">{t('col_code')}</th>
              <th className="text-start">{t('col_name')}</th>
              <th className="text-start">{t('col_kind')}</th>
              <th className="text-start">{t('col_unit')}</th>
              <th className="text-start">{t('col_deps')}</th>
              <th className="text-start">{t('col_status')}</th>
              <th className="text-end">{t('col_actions')}</th>
            </tr>
          </thead>
          <tbody>
            {vars.map((v) => (
              <tr key={v.id} className="border-b border-edge/50">
                <td className="py-2 font-mono text-cyan-300">{v.code}</td>
                <td className="text-gray-200">{v.name}</td>
                <td className="text-gray-400">{t(v.kind === 'scalar' ? 'kind_scalar' : 'kind_series')}</td>
                <td className="text-gray-400">{v.unit || '—'}</td>
                <td className="text-gray-400">{v.dependency_count}</td>
                <td>
                  <span className={v.is_active ? 'text-emerald-400' : 'text-gray-500'}>
                    {t(v.is_active ? 'status_active' : 'status_inactive')}
                  </span>
                </td>
                <td className="text-end space-x-2 whitespace-nowrap">
                  {can('facility_variable:edit') && (
                    <button onClick={() => setEditVar(v)} className="text-cyan-400 hover:underline">
                      {t('action_edit')}
                    </button>
                  )}
                  {can('facility_variable:delete') && v.is_active && (
                    <button onClick={() => handleDeactivate(v)} className="text-red-400 hover:underline">
                      {t('action_deactivate')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showAdd && <VariableEditorModal onClose={() => setShowAdd(false)} />}
      {editVar && <VariableEditorModal initial={editVar} onClose={() => setEditVar(null)} />}
    </div>
  )
}
