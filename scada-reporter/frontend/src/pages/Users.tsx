import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listUsers, createUser, patchUser, resetUserPassword, deleteUser,
  type ManagedUser, type UserCreatePayload, type UserRole,
} from '../api/client'

const PERM_KEYS = [
  ['tag:create', 'perm_tag_create'],
  ['plc:manage', 'perm_plc_manage'],
  ['report_template:create', 'perm_report_create'],
  ['report_template:edit', 'perm_report_edit'],
  ['report_template:delete', 'perm_report_delete'],
  ['facility_variable:create', 'perm_fv_create'],
  ['facility_variable:edit', 'perm_fv_edit'],
  ['facility_variable:delete', 'perm_fv_delete'],
] as const

const ROLES = ['admin', 'operator', 'viewer'] as const

const EMPTY: UserCreatePayload = {
  username: '', email: '', password: '', full_name: '', role: 'operator', permission_overrides: {},
}

export default function Users() {
  const { t } = useTranslation('users')
  const qc = useQueryClient()
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => listUsers().then((r) => r.data) })
  const [form, setForm] = useState<UserCreatePayload>(EMPTY)
  const [editing, setEditing] = useState<ManagedUser | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['users'] })
  const onMutError = (e: unknown) => {
    const ax = e as { response?: { status?: number; data?: { detail?: string } } }
    alert(ax.response?.data?.detail || t('last_admin_error'))
  }

  const createMut = useMutation({ mutationFn: createUser, onSuccess: () => { invalidate(); setForm(EMPTY) } })
  const patchMut = useMutation({
    mutationFn: (v: { id: number; data: Parameters<typeof patchUser>[1] }) => patchUser(v.id, v.data),
    onSuccess: () => { invalidate(); setEditing(null) },
    onError: onMutError,
  })
  const delMut = useMutation({ mutationFn: deleteUser, onSuccess: invalidate, onError: onMutError })

  const toggleOverride = (target: UserCreatePayload | ManagedUser, key: string, set: (o: Record<string, boolean>) => void) => {
    const cur = { ...(target.permission_overrides || {}) }
    if (key in cur) delete cur[key]
    else cur[key] = true
    set(cur)
  }

  return (
    <div className="p-6 text-gray-200">
      <h1 className="text-xl font-semibold mb-4">{t('title')}</h1>

      {/* Create form */}
      <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 mb-6 grid gap-2 max-w-xl">
        <h2 className="font-medium">{t('new_user')}</h2>
        <input className="bg-surface-sunken px-2 py-1 rounded" placeholder={t('username')} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input className="bg-surface-sunken px-2 py-1 rounded" placeholder={t('email')} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <input className="bg-surface-sunken px-2 py-1 rounded" placeholder={t('full_name')} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        <input className="bg-surface-sunken px-2 py-1 rounded" type="password" placeholder={t('password')} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <select className="bg-surface-sunken px-2 py-1 rounded" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}>
          {ROLES.map((r) => <option key={r} value={r}>{t(`role_${r}`)}</option>)}
        </select>
        <div className="text-sm text-gray-400">{t('overrides')}</div>
        {PERM_KEYS.map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={key in (form.permission_overrides || {})} onChange={() => toggleOverride(form, key, (o) => setForm({ ...form, permission_overrides: o }))} />
            {t(label)}
          </label>
        ))}
        <button className="bg-blue-600 px-3 py-1.5 rounded mt-2 disabled:opacity-50" disabled={!form.username || !form.password} onClick={() => createMut.mutate(form)}>{t('create')}</button>
      </div>

      {/* User table */}
      <table className="w-full text-sm">
        <thead className="text-gray-400 text-start">
          <tr><th className="py-2">{t('username')}</th><th>{t('full_name')}</th><th>{t('role')}</th><th>{t('active')}</th><th>{t('permissions')}</th><th /></tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-t border-edge">
              <td className="py-2">{u.username}</td>
              <td>{u.full_name}</td>
              <td>{t(`role_${u.role}`)}</td>
              <td>{u.is_active ? '✓' : '—'}</td>
              <td className="text-gray-500 text-xs">{u.permissions.join(', ')}</td>
              <td className="text-end space-x-2">
                <button className="text-cyan-400" onClick={() => setEditing(u)}>{t('edit')}</button>
                <button className="text-amber-400" onClick={() => { const p = prompt(t('reset_password')); if (p) resetUserPassword(u.id, p).catch((e: unknown) => { const ax = e as { response?: { data?: { detail?: string } } }; alert(ax.response?.data?.detail || t('last_admin_error')) }) }}>{t('reset_password')}</button>
                <button className="text-red-400" onClick={() => { if (confirm(t('confirm_delete'))) delMut.mutate(u.id) }}>{t('delete')}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Edit modal */}
      {editing && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center" onClick={() => setEditing(null)}>
          <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 grid gap-2 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <h2 className="font-medium">{editing.username}</h2>
            <select className="bg-surface-sunken px-2 py-1 rounded" value={editing.role} onChange={(e) => setEditing({ ...editing, role: e.target.value as UserRole })}>
              {ROLES.map((r) => <option key={r} value={r}>{t(`role_${r}`)}</option>)}
            </select>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={editing.is_active} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} />{t('active')}</label>
            <div className="text-sm text-gray-400">{t('overrides')}</div>
            {PERM_KEYS.map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={key in (editing.permission_overrides || {})} onChange={() => toggleOverride(editing, key, (o) => setEditing({ ...editing, permission_overrides: o }))} />
                {t(label)}
              </label>
            ))}
            <div className="flex gap-2 mt-2">
              <button className="bg-blue-600 px-3 py-1.5 rounded" onClick={() => patchMut.mutate({ id: editing.id, data: { role: editing.role, is_active: editing.is_active, permission_overrides: editing.permission_overrides } })}>{t('save')}</button>
              <button className="bg-gray-700 px-3 py-1.5 rounded" onClick={() => setEditing(null)}>{t('cancel')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
