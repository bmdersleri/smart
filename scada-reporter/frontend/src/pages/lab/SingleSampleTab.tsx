import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createSample,
  listLabParameters,
  listLabSamplePoints,
  type LabParameterOut,
  type LabSamplePointOut,
} from '../../api/client'

// Pure, unit-tested: a value is out of range when below min or above max.
// eslint-disable-next-line react-refresh/only-export-components
export function isOutOfRange(
  value: number | null,
  min: number | null,
  max: number | null,
): boolean {
  if (value === null || Number.isNaN(value)) return false
  if (min !== null && value < min) return true
  if (max !== null && value > max) return true
  return false
}

export default function SingleSampleTab() {
  const { t } = useTranslation('lab')
  const [points, setPoints] = useState<LabSamplePointOut[]>([])
  const [params, setParams] = useState<LabParameterOut[]>([])
  const [pointId, setPointId] = useState<number | ''>('')
  const [sampledAt, setSampledAt] = useState(() => new Date().toISOString().slice(0, 16))
  const [values, setValues] = useState<Record<number, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([listLabSamplePoints({ approved: true }), listLabParameters({ approved: true })])
      .then(([pts, prs]) => {
        setPoints(pts.data ?? [])
        setParams(prs.data ?? [])
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const handleSave = async () => {
    if (pointId === '') return
    setSaving(true)
    setSaved(false)
    setError(null)
    const measurements = Object.entries(values)
      .filter(([, v]) => v !== '')
      .map(([pid, v]) => ({ parameter_id: Number(pid), value: Number(v) }))
    try {
      await createSample({ sample_point_id: Number(pointId), sampled_at: new Date(sampledAt).toISOString(), measurements })
      setSaved(true)
      setValues({})
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <label className="space-y-1">
          <span className="block text-xs uppercase text-gray-500">{t('sample_point')}</span>
          <select
            value={pointId}
            onChange={(e) => setPointId(e.target.value === '' ? '' : Number(e.target.value))}
            className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100"
          >
            <option value="">—</option>
            {points.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="block text-xs uppercase text-gray-500">{t('sampled_at')}</span>
          <input
            type="datetime-local"
            value={sampledAt}
            onChange={(e) => setSampledAt(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100"
          />
        </label>
      </div>

      <div className="space-y-2">
        {params.map((param) => {
          const raw = values[param.id] ?? ''
          const num = raw === '' ? null : Number(raw)
          const bad = isOutOfRange(num, param.min_limit, param.max_limit)
          return (
            <div key={param.id} className="flex items-center gap-3">
              <span className="w-40 text-sm text-gray-300">
                {param.name} {param.unit ? `(${param.unit})` : ''}
              </span>
              <input
                value={raw}
                onChange={(e) => setValues((v) => ({ ...v, [param.id]: e.target.value }))}
                className={`w-32 rounded-lg border bg-gray-900 px-3 py-2 text-sm text-gray-100 ${bad ? 'border-red-500' : 'border-gray-700'}`}
              />
              {bad && <span className="text-xs text-red-400">{t('out_of_range')}</span>}
            </div>
          )
        })}
      </div>

      <button
        onClick={handleSave}
        disabled={saving || pointId === ''}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:bg-gray-700"
      >
        {saving ? '…' : t('save')}
      </button>
      {saved && <span className="ml-3 text-sm text-green-400">{t('saved')}</span>}
      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  )
}
