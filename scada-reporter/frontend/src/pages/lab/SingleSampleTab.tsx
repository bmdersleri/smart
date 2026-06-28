import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createParameter,
  createSample,
  createSamplePoint,
  listLabParameters,
  listLabSamplePoints,
  type LabParameterOut,
  type LabSamplePointOut,
} from '../../api/client'
import { useTimezone } from '../../hooks/useTimezone'
import { nowInTz, wallclockToUtcIso } from '../../utils/labTime'

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

// Pure, unit-tested: both code and name must be non-empty strings.
// eslint-disable-next-line react-refresh/only-export-components
export function canCreate(code: string, name: string): boolean {
  return code.trim().length > 0 && name.trim().length > 0
}

export default function SingleSampleTab() {
  const { t } = useTranslation('lab')
  const tz = useTimezone()
  const [points, setPoints] = useState<LabSamplePointOut[]>([])
  const [params, setParams] = useState<LabParameterOut[]>([])
  const [pointId, setPointId] = useState<number | ''>('')
  const [sampledAt, setSampledAt] = useState(() => nowInTz('Europe/Istanbul'))
  const [touched, setTouched] = useState(false)
  const [values, setValues] = useState<Record<number, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // New sample point inline form
  const [showNewPoint, setShowNewPoint] = useState(false)
  const [newPointCode, setNewPointCode] = useState('')
  const [newPointName, setNewPointName] = useState('')
  const [addingPoint, setAddingPoint] = useState(false)

  // New parameter inline form
  const [showNewParam, setShowNewParam] = useState(false)
  const [newParamCode, setNewParamCode] = useState('')
  const [newParamName, setNewParamName] = useState('')
  const [newParamUnit, setNewParamUnit] = useState('')
  const [addingParam, setAddingParam] = useState(false)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!touched) setSampledAt(nowInTz(tz))
  }, [tz, touched])

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
      await createSample({ sample_point_id: Number(pointId), sampled_at: wallclockToUtcIso(sampledAt, tz), measurements })
      setSaved(true)
      setValues({})
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleAddPoint = async () => {
    if (!canCreate(newPointCode, newPointName)) return
    setAddingPoint(true)
    setError(null)
    try {
      const res = await createSamplePoint({ code: newPointCode.trim(), name: newPointName.trim() })
      setPoints((prev) => [...prev, res.data])
      setPointId(res.data.id)
      setShowNewPoint(false)
      setNewPointCode('')
      setNewPointName('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setAddingPoint(false)
    }
  }

  const handleAddParam = async () => {
    if (!canCreate(newParamCode, newParamName)) return
    setAddingParam(true)
    setError(null)
    try {
      const res = await createParameter({ code: newParamCode.trim(), name: newParamName.trim(), unit: newParamUnit.trim() || undefined })
      setParams((prev) => [...prev, res.data])
      setShowNewParam(false)
      setNewParamCode('')
      setNewParamName('')
      setNewParamUnit('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setAddingParam(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <span className="block text-xs uppercase text-gray-500">{t('sample_point')}</span>
          <div className="flex items-center gap-2">
            <select
              value={pointId}
              onChange={(e) => setPointId(e.target.value === '' ? '' : Number(e.target.value))}
              className="flex-1 rounded-lg border border-gray-700 bg-gray-900/40 backdrop-blur-xl px-3 py-2 text-sm text-gray-100"
            >
              <option value="">—</option>
              {points.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <button
              onClick={() => setShowNewPoint((v) => !v)}
              className="shrink-0 rounded-lg border border-gray-700 bg-gray-800 px-2 py-2 text-xs text-gray-300 hover:bg-gray-700"
            >
              {t('add_point')}
            </button>
          </div>
          {showNewPoint && (
            <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 p-2">
              <input
                value={newPointCode}
                onChange={(e) => setNewPointCode(e.target.value)}
                placeholder={t('code')}
                className="w-24 rounded-lg border border-gray-700 bg-gray-900/40 backdrop-blur-xl px-2 py-1 text-sm text-gray-100"
              />
              <input
                value={newPointName}
                onChange={(e) => setNewPointName(e.target.value)}
                placeholder={t('name')}
                className="w-36 rounded-lg border border-gray-700 bg-gray-900/40 backdrop-blur-xl px-2 py-1 text-sm text-gray-100"
              />
              <button
                onClick={handleAddPoint}
                disabled={addingPoint || !canCreate(newPointCode, newPointName)}
                className="rounded-lg bg-blue-600 px-3 py-1 text-xs text-white disabled:bg-gray-700"
              >
                {t('add')}
              </button>
              <button
                onClick={() => { setShowNewPoint(false); setNewPointCode(''); setNewPointName('') }}
                className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1 text-xs text-gray-400 hover:bg-gray-700"
              >
                {t('cancel')}
              </button>
            </div>
          )}
        </div>
        <label className="space-y-1">
          <span className="block text-xs uppercase text-gray-500">{t('sampled_at')}</span>
          <input
            type="datetime-local"
            value={sampledAt}
            onChange={(e) => { setTouched(true); setSampledAt(e.target.value) }}
            className="w-full rounded-lg border border-gray-700 bg-gray-900/40 backdrop-blur-xl px-3 py-2 text-sm text-gray-100"
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
                className={`w-32 rounded-lg border bg-gray-900/40 backdrop-blur-xl px-3 py-2 text-sm text-gray-100 ${bad ? 'border-red-500' : 'border-gray-700'}`}
              />
              {bad && <span className="text-xs text-red-400">{t('out_of_range')}</span>}
            </div>
          )
        })}

        <div>
          <button
            onClick={() => setShowNewParam((v) => !v)}
            className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-xs text-gray-300 hover:bg-gray-700"
          >
            {t('add_parameter')}
          </button>
          {showNewParam && (
            <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 p-2">
              <input
                value={newParamCode}
                onChange={(e) => setNewParamCode(e.target.value)}
                placeholder={t('code')}
                className="w-24 rounded-lg border border-gray-700 bg-gray-900/40 backdrop-blur-xl px-2 py-1 text-sm text-gray-100"
              />
              <input
                value={newParamName}
                onChange={(e) => setNewParamName(e.target.value)}
                placeholder={t('name')}
                className="w-36 rounded-lg border border-gray-700 bg-gray-900/40 backdrop-blur-xl px-2 py-1 text-sm text-gray-100"
              />
              <input
                value={newParamUnit}
                onChange={(e) => setNewParamUnit(e.target.value)}
                placeholder={t('unit')}
                className="w-20 rounded-lg border border-gray-700 bg-gray-900/40 backdrop-blur-xl px-2 py-1 text-sm text-gray-100"
              />
              <button
                onClick={handleAddParam}
                disabled={addingParam || !canCreate(newParamCode, newParamName)}
                className="rounded-lg bg-blue-600 px-3 py-1 text-xs text-white disabled:bg-gray-700"
              >
                {t('add')}
              </button>
              <button
                onClick={() => { setShowNewParam(false); setNewParamCode(''); setNewParamName(''); setNewParamUnit('') }}
                className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1 text-xs text-gray-400 hover:bg-gray-700"
              >
                {t('cancel')}
              </button>
            </div>
          )}
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={saving || pointId === ''}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:bg-gray-700"
      >
        {saving ? '…' : t('save')}
      </button>
      {saved && <span className="ms-3 text-sm text-green-400">{t('saved')}</span>}
      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  )
}
