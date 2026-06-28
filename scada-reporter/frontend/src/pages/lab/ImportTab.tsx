import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  importPreview,
  importCommit,
  listLabParameters,
  listLabSamplePoints,
  type LabParameterOut,
  type LabSamplePointOut,
} from '../../api/client'

interface Preview {
  headers: string[]
  rows: string[][]
}

export default function ImportTab() {
  const { t } = useTranslation('lab')
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [points, setPoints] = useState<LabSamplePointOut[]>([])
  const [params, setParams] = useState<LabParameterOut[]>([])
  const [pointId, setPointId] = useState<number | ''>('')
  const [timeCol, setTimeCol] = useState('')
  const [mapping, setMapping] = useState<Record<string, number>>({})
  const [result, setResult] = useState<{ inserted: number; errors: string[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const [prev, pts, prs] = await Promise.all([
        importPreview(file),
        listLabSamplePoints({ approved: true }),
        listLabParameters({ approved: true }),
      ])
      setPreview(prev.data)
      setPoints(pts.data ?? [])
      setParams(prs.data ?? [])
      if (prev.data.headers.length) setTimeCol(prev.data.headers[0])
    } catch (e2) {
      setError(e2 instanceof Error ? e2.message : String(e2))
    } finally {
      setLoading(false)
    }
  }

  const setParamCol = (paramId: number, col: string) => {
    setMapping((m) => {
      const next = { ...m }
      if (col === '') {
        delete next[String(paramId)]
      } else {
        next[String(paramId)] = Number(col)
      }
      return next
    })
  }

  const handleCommit = async () => {
    if (!preview || pointId === '' || !timeCol) return
    setLoading(true)
    setError(null)
    try {
      const r = await importCommit({
        headers: preview.headers,
        rows: preview.rows,
        sample_point_id: Number(pointId),
        time_column: timeCol,
        mapping,
      })
      setResult(r.data)
      setPreview(null)
      if (fileRef.current) fileRef.current.value = ''
    } catch (e2) {
      setError(e2 instanceof Error ? e2.message : String(e2))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-red-400">{error}</p>}

      <div>
        <span className="block text-xs uppercase text-gray-500 mb-1">{t('tab_import')}</span>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          onChange={onFile}
          className="text-sm text-gray-400"
        />
      </div>

      {loading && <p className="text-sm text-gray-500">…</p>}

      {result && (
        <div className="rounded-lg border border-green-800 bg-green-950 p-4 space-y-1">
          <p className="text-sm text-green-400">
            {t('saved')}: {result.inserted}
          </p>
          {result.errors.length > 0 && (
            <ul className="text-xs text-red-400 list-disc list-inside">
              {result.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}

      {preview && (
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
              <select
                value={timeCol}
                onChange={(e) => setTimeCol(e.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              >
                {preview.headers.map((h, i) => <option key={i} value={h}>{h}</option>)}
              </select>
            </label>
          </div>

          <div className="space-y-2">
            <p className="text-xs uppercase text-gray-500">{t('value')}</p>
            {params.map((p) => (
              <div key={p.id} className="flex items-center gap-3">
                <span className="w-40 text-sm text-gray-300">
                  {p.name}{p.unit ? ` (${p.unit})` : ''}
                </span>
                <select
                  value={mapping[String(p.id)] !== undefined ? String(mapping[String(p.id)]) : ''}
                  onChange={(e) => setParamCol(p.id, e.target.value)}
                  className="rounded-lg border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-100"
                >
                  <option value="">—</option>
                  {preview.headers.map((h, i) => (
                    <option key={i} value={i}>{h}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto max-h-48">
            <table className="text-xs text-gray-400 w-full">
              <thead>
                <tr>
                  {preview.headers.map((h, i) => (
                    <th key={i} className="text-start pe-3 pb-1">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.slice(0, 5).map((row, ri) => (
                  <tr key={ri}>
                    {row.map((cell, ci) => (
                      <td key={ci} className="pe-3">{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button
            onClick={handleCommit}
            disabled={loading || pointId === '' || !timeCol}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:bg-gray-700"
          >
            {loading ? '…' : t('save')}
          </button>
        </div>
      )}
    </div>
  )
}
