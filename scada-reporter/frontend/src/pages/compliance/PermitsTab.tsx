import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listPermits,
  createPermit,
  deletePermit,
  type CompliancePermit,
  type CompliancePermitPayload,
} from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { Card } from './helpers'
import { REPORT_FREQUENCIES } from './constants'
import PermitDetail from './PermitDetail'

const EMPTY_PERMIT: CompliancePermitPayload = {
  name: '',
  facility_name: '',
  authority: '',
  permit_number: '',
  report_frequency: 'monthly',
  is_active: true,
}

export default function PermitsTab() {
  const { t } = useTranslation(['compliance', 'common'])
  const { user } = useAuth()
  const qc = useQueryClient()
  const isAdmin = user?.role === 'admin'

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [form, setForm] = useState<CompliancePermitPayload>(EMPTY_PERMIT)
  const [err, setErr] = useState('')

  const { data: permits = [], isLoading, isError } = useQuery({
    queryKey: ['compliance-permits'],
    queryFn: () => listPermits().then((r) => r.data),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['compliance-permits'] })
  const onErr = (e: unknown) => {
    const ax = e as { response?: { data?: { detail?: string } } }
    setErr(ax.response?.data?.detail || t('save_error'))
  }

  const createMut = useMutation({
    mutationFn: () => createPermit(form),
    onSuccess: () => {
      invalidate()
      setForm(EMPTY_PERMIT)
      setShowNew(false)
      setErr('')
    },
    onError: onErr,
  })

  const delMut = useMutation({
    mutationFn: (id: number) => deletePermit(id),
    onSuccess: () => {
      invalidate()
      setSelectedId(null)
    },
    onError: onErr,
  })

  if (isLoading) return <div className="text-center py-16 text-gray-500">{t('common:loading')}</div>
  if (isError) return <div className="text-center py-16 text-red-400">{t('load_error')}</div>

  return (
    <div className="grid md:grid-cols-[18rem_1fr] gap-4">
      {/* Permit list */}
      <div className="space-y-3">
        {isAdmin && (
          <button
            className="w-full bg-blue-600 hover:bg-blue-500 px-3 py-1.5 rounded text-sm text-white"
            onClick={() => {
              setShowNew((v) => !v)
              setErr('')
            }}
          >
            {t('new_permit')}
          </button>
        )}

        {isAdmin && showNew && (
          <Card className="p-3 grid gap-2">
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
            <button
              className="bg-blue-600 hover:bg-blue-500 px-3 py-1.5 rounded text-sm text-white disabled:opacity-50"
              disabled={!form.name.trim() || createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              {t('common:save')}
            </button>
            {err && <p className="text-xs text-red-400">{err}</p>}
          </Card>
        )}

        <Card className="overflow-hidden">
          <ul>
            {permits.map((p: CompliancePermit) => (
              <li key={p.id}>
                <button
                  className={`w-full text-start px-3 py-2 text-sm border-t border-edge first:border-t-0 hover:bg-white/5 ${
                    selectedId === p.id ? 'bg-cyan-500/10 text-cyan-300' : 'text-gray-200'
                  }`}
                  onClick={() => setSelectedId(p.id)}
                >
                  <span className="block font-medium">{p.name}</span>
                  <span className="block text-xs text-gray-500">
                    {p.permit_number || '—'} · {p.is_active ? t('active') : t('inactive')}
                  </span>
                </button>
              </li>
            ))}
            {permits.length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-gray-500">{t('no_permits')}</li>
            )}
          </ul>
        </Card>
      </div>

      {/* Permit detail */}
      <div>
        {selectedId === null ? (
          <Card className="p-8 text-center text-gray-500 text-sm">{t('select_permit_hint')}</Card>
        ) : (
          <PermitDetail
            permitId={selectedId}
            isAdmin={isAdmin}
            onDelete={() => {
              if (confirm(t('confirm_deactivate'))) delMut.mutate(selectedId)
            }}
          />
        )}
      </div>
    </div>
  )
}
