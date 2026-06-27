import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { deleteSample, listSamples, type SampleOut } from '../../api/client'
import { useAuth } from '../../context/AuthContext'

// eslint-disable-next-line react-refresh/only-export-components
export function canEditRecord(
  user: { role: string; id: number },
  enteredBy: number,
): boolean {
  return user.role === 'admin' || user.id === enteredBy
}

export default function RecordsTab() {
  const { t } = useTranslation('lab')
  const { user } = useAuth()
  const [samples, setSamples] = useState<SampleOut[]>([])
  const [error, setError] = useState<string | null>(null)

  const reload = () =>
    listSamples({ limit: 100 })
      .then((r) => setSamples(r.data ?? []))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))

  useEffect(() => {
    reload()
  }, [])

  const onDelete = async (id: number) => {
    await deleteSample(id)
    await reload()
  }

  return (
    <div className="space-y-2">
      {error && <p className="text-sm text-red-400">{error}</p>}
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
              <td>{new Date(s.sampled_at).toLocaleString()}</td>
              <td>{s.sample_point_id}</td>
              <td className="text-end">
                {user && canEditRecord({ role: user.role, id: user.id }, s.entered_by) && (
                  <button onClick={() => onDelete(s.id)} className="text-red-400 hover:underline">
                    &#x2715;
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
