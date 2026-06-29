import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { Variable } from 'lucide-react'
import { listFacilityVariables, deleteFacilityVariable } from '../api/client'
import type { FacilityVariable } from '../api/client'
import { useAuth } from '../context/AuthContext'

// Replaced by the real editor in Task 5. Stub keeps the page compiling.
function VariableEditorModal(_props: { initial?: FacilityVariable; onClose: () => void }) {
  return null
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
