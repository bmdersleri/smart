import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  deleteSample,
  listLabParameters,
  listSamples,
  updateSample,
  type LabParameterOut,
  type SampleOut,
} from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { useTimezone } from '../../hooks/useTimezone'
import { utcToTzInput, utcToTzDisplay, wallclockToUtcIso } from '../../utils/labTime'

// eslint-disable-next-line react-refresh/only-export-components
export function canEditRecord(
  user: { role: string; id: number },
  enteredBy: number,
): boolean {
  return user.role === 'admin' || user.id === enteredBy
}

interface EditState {
  sample: SampleOut
  sample_point_id: number
  sampled_at: string
  values: Record<number, string>
}

export default function RecordsTab() {
  const { t, i18n } = useTranslation('lab')
  const tz = useTimezone()
  const { user } = useAuth()
  const [samples, setSamples] = useState<SampleOut[]>([])
  const [params, setParams] = useState<LabParameterOut[]>([])
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<EditState | null>(null)
  const [saving, setSaving] = useState(false)

  const reload = () =>
    listSamples({ limit: 100 })
      .then((r) => setSamples(r.data ?? []))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))

  useEffect(() => {
    reload()
    listLabParameters({ approved: true })
      .then((r) => setParams(r.data ?? []))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const onDelete = async (id: number) => {
    await deleteSample(id)
    await reload()
  }

  const openEdit = (s: SampleOut) => {
    const values: Record<number, string> = {}
    for (const m of s.measurements) {
      values[m.parameter_id] = String(m.value)
    }
    setEditing({
      sample: s,
      sample_point_id: s.sample_point_id,
      sampled_at: utcToTzInput(s.sampled_at, tz),
      values,
    })
  }

  const closeEdit = () => setEditing(null)

  const onSave = async () => {
    if (!editing) return
    setSaving(true)
    setError(null)
    try {
      const measurements = Object.entries(editing.values)
        .filter(([, v]) => v !== '')
        .map(([pid, v]) => ({ parameter_id: Number(pid), value: Number(v) }))
      await updateSample(editing.sample.id, {
        sample_point_id: editing.sample_point_id,
        sampled_at: wallclockToUtcIso(editing.sampled_at, tz),
        measurements,
      })
      closeEdit()
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-2">
      {error && <p className="text-sm text-red-400">{error}</p>}

      {editing && (
        <div className="rounded-lg border border-gray-700 bg-gray-900 p-4 space-y-3">
          <p className="text-sm font-medium text-gray-300">{t('edit_record')}</p>
          <label className="block space-y-1">
            <span className="block text-xs uppercase text-gray-500">{t('sampled_at')}</span>
            <input
              type="datetime-local"
              value={editing.sampled_at}
              onChange={(e) => setEditing((prev) => prev && { ...prev, sampled_at: e.target.value })}
              className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100"
            />
          </label>
          {params.map((p) => (
            <label key={p.id} className="block space-y-1">
              <span className="block text-xs uppercase text-gray-500">
                {p.name}{p.unit ? ` (${p.unit})` : ''}
              </span>
              <input
                type="number"
                value={editing.values[p.id] ?? ''}
                onChange={(e) =>
                  setEditing((prev) =>
                    prev && { ...prev, values: { ...prev.values, [p.id]: e.target.value } },
                  )
                }
                className="w-32 rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100"
              />
            </label>
          ))}
          <div className="flex gap-2">
            <button
              onClick={onSave}
              disabled={saving}
              className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:bg-gray-700"
            >
              {saving ? '…' : t('save')}
            </button>
            <button
              onClick={closeEdit}
              className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-400 hover:text-white"
            >
              {t('cancel')}
            </button>
          </div>
        </div>
      )}

      <table className="w-full text-sm text-gray-200">
        <thead className="text-gray-500">
          <tr>
            <th className="text-start">{t('sampled_at')}</th>
            <th className="text-start">{t('sample_point')}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {samples.map((s) => (
            <tr key={s.id} className="border-t border-gray-800">
              <td>{utcToTzDisplay(s.sampled_at, tz, i18n.language)}</td>
              <td>{s.sample_point_id}</td>
              <td className="text-end space-x-2">
                {user && canEditRecord({ role: user.role, id: user.id }, s.entered_by) && (
                  <>
                    <button
                      onClick={() => openEdit(s)}
                      className="text-blue-400 hover:underline"
                    >
                      {t('edit')}
                    </button>
                    <button onClick={() => onDelete(s.id)} className="text-red-400 hover:underline">
                      &#x2715;
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
