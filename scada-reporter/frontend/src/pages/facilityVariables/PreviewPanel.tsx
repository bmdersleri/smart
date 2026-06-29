import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { previewVariable } from '../../api/client'
import type { PreviewResult } from '../../api/client'

export default function PreviewPanel({ variableId, kind }: { variableId: number; kind: 'scalar' | 'series' }) {
  const { t } = useTranslation('facilityVariables')
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const mut = useMutation({
    mutationFn: () => previewVariable(variableId, { window: { type: 'month', year, month } }).then((r) => r.data),
  })
  const result = mut.data as PreviewResult | undefined
  const errDetail = (mut.error as AxiosError<{ detail: string }>)?.response?.data?.detail
  const selCls = 'bg-surface-sunken border border-edge-strong rounded px-2 py-1 text-sm text-white w-24'

  return (
    <div className="border border-edge rounded-lg p-3 space-y-2 bg-black/20">
      <div className="flex items-end gap-3">
        <label className="text-xs text-gray-400 space-y-1"><span>{t('preview_year')}</span>
          <input type="number" className={selCls} value={year} onChange={(e) => setYear(Number(e.target.value))} />
        </label>
        <label className="text-xs text-gray-400 space-y-1"><span>{t('preview_month')}</span>
          <input type="number" min={1} max={12} className={selCls} value={month}
            onChange={(e) => setMonth(Number(e.target.value))} />
        </label>
        <button onClick={() => mut.mutate()} disabled={mut.isPending}
          className="px-3 py-1.5 rounded bg-cyan-600/30 border border-cyan-500/40 text-cyan-200 text-sm disabled:opacity-40">
          {t('preview')}
        </button>
      </div>

      {mut.isError && <p className="text-red-400 text-sm">{errDetail || t('error_generic')}</p>}

      {!result ? (
        <p className="text-xs text-gray-500">{t('preview_empty')}</p>
      ) : result.kind === 'scalar' ? (
        <p className="text-white text-sm">
          {t('preview_scalar')}: <span className="font-mono">{result.value ?? '—'}</span> {result.unit}
        </p>
      ) : (
        <p className="text-gray-300 text-sm">{t('preview_series_points', { count: result.points.length })}</p>
      )}
    </div>
  )
}
