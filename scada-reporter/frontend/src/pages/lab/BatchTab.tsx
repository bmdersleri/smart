import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createSamplesBatch,
  listLabParameters,
  listLabSamplePoints,
  type LabParameterOut,
  type LabSamplePointOut,
} from '../../api/client'
import { useTimezone } from '../../hooks/useTimezone'
import { nowInTz, wallclockToUtcIso } from '../../utils/labTime'

interface BatchRow {
  sampled_at: string
  values: Record<number, string>
}

export default function BatchTab() {
  const { t } = useTranslation('lab')
  const tz = useTimezone()

  function emptyRow(): BatchRow {
    return { sampled_at: nowInTz(tz), values: {} }
  }
  const [points, setPoints] = useState<LabSamplePointOut[]>([])
  const [params, setParams] = useState<LabParameterOut[]>([])
  const [pointId, setPointId] = useState<number | ''>('')
  const [rows, setRows] = useState<BatchRow[]>([emptyRow()])
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

  const setCell = (rowIdx: number, paramId: number, val: string) => {
    setRows((prev) =>
      prev.map((r, i) =>
        i === rowIdx ? { ...r, values: { ...r.values, [paramId]: val } } : r,
      ),
    )
  }

  const setTime = (rowIdx: number, val: string) => {
    setRows((prev) => prev.map((r, i) => (i === rowIdx ? { ...r, sampled_at: val } : r)))
  }

  const addRow = () => setRows((prev) => [...prev, emptyRow()])

  const removeRow = (idx: number) =>
    setRows((prev) => prev.filter((_, i) => i !== idx))

  const handleSave = async () => {
    if (pointId === '') return
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      const batchRows = rows.map((r) => ({
        sample_point_id: Number(pointId),
        sampled_at: wallclockToUtcIso(r.sampled_at, tz),
        measurements: Object.entries(r.values)
          .filter(([, v]) => v !== '')
          .map(([pid, v]) => ({ parameter_id: Number(pid), value: Number(v) })),
      }))
      await createSamplesBatch({ rows: batchRows })
      setSaved(true)
      setRows([emptyRow()])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-red-400">{error}</p>}
      <label className="space-y-1 block">
        <span className="block text-xs uppercase text-gray-500">{t('sample_point')}</span>
        <select
          value={pointId}
          onChange={(e) => setPointId(e.target.value === '' ? '' : Number(e.target.value))}
          className="rounded-lg border border-edge-strong bg-surface-raised/40 backdrop-blur-xl px-3 py-2 text-sm text-gray-100"
        >
          <option value="">—</option>
          {points.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </label>

      <div className="overflow-x-auto">
        <table className="text-sm text-gray-200 w-full">
          <thead className="text-gray-500">
            <tr>
              <th className="text-start pe-2">{t('sampled_at')}</th>
              {params.map((p) => (
                <th key={p.id} className="text-start pe-2">
                  {p.name}{p.unit ? ` (${p.unit})` : ''}
                </th>
              ))}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className="border-t border-edge">
                <td className="pe-2 py-1">
                  <input
                    type="datetime-local"
                    value={row.sampled_at}
                    onChange={(e) => setTime(ri, e.target.value)}
                    className="rounded-lg border border-edge-strong bg-surface-raised/40 backdrop-blur-xl px-2 py-1 text-sm text-gray-100"
                  />
                </td>
                {params.map((p) => (
                  <td key={p.id} className="pe-2 py-1">
                    <input
                      type="number"
                      value={row.values[p.id] ?? ''}
                      onChange={(e) => setCell(ri, p.id, e.target.value)}
                      className="w-24 rounded-lg border border-edge-strong bg-surface-raised/40 backdrop-blur-xl px-2 py-1 text-sm text-gray-100"
                    />
                  </td>
                ))}
                <td className="py-1">
                  {rows.length > 1 && (
                    <button
                      onClick={() => removeRow(ri)}
                      className="text-red-400 hover:underline text-xs"
                    >
                      &#x2715;
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={addRow}
          className="rounded-lg border border-edge-strong px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-white/5"
        >
          {t('add_row')}
        </button>
        <button
          onClick={handleSave}
          disabled={saving || pointId === ''}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:bg-gray-700"
        >
          {saving ? '…' : t('save')}
        </button>
        {saved && <span className="text-sm text-green-400">{t('saved')}</span>}
      </div>
    </div>
  )
}
