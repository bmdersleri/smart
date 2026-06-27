import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listLabParameters,
  listLabSamplePoints,
  createParameter,
  updateParameter,
  deleteParameter,
  createSamplePoint,
  updateSamplePoint,
  deleteSamplePoint,
  type LabParameterOut,
  type LabSamplePointOut,
} from '../../api/client'

export default function LabCatalogCard() {
  const { t } = useTranslation('lab')
  const [params, setParams] = useState<LabParameterOut[]>([])
  const [points, setPoints] = useState<LabSamplePointOut[]>([])
  const [error, setError] = useState<string | null>(null)

  // New parameter form
  const [newParamName, setNewParamName] = useState('')
  const [newParamCode, setNewParamCode] = useState('')
  const [newParamUnit, setNewParamUnit] = useState('')

  // New sample point form
  const [newPointName, setNewPointName] = useState('')
  const [newPointCode, setNewPointCode] = useState('')
  const [newPointDesc, setNewPointDesc] = useState('')

  const reloadAll = () =>
    Promise.all([listLabParameters(), listLabSamplePoints()])
      .then(([prs, pts]) => {
        setParams(prs.data ?? [])
        setPoints(pts.data ?? [])
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))

  useEffect(() => {
    reloadAll()
  }, [])

  const handleAddParam = async () => {
    if (!newParamName || !newParamCode) return
    try {
      await createParameter({ name: newParamName, code: newParamCode, unit: newParamUnit })
      setNewParamName('')
      setNewParamCode('')
      setNewParamUnit('')
      await reloadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleApproveParam = async (id: number) => {
    try {
      await updateParameter(id, { approved: true })
      await reloadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleDeleteParam = async (id: number) => {
    try {
      await deleteParameter(id)
      await reloadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleAddPoint = async () => {
    if (!newPointName || !newPointCode) return
    try {
      await createSamplePoint({ name: newPointName, code: newPointCode, description: newPointDesc })
      setNewPointName('')
      setNewPointCode('')
      setNewPointDesc('')
      await reloadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleApprovePoint = async (id: number) => {
    try {
      await updateSamplePoint(id, { approved: true })
      await reloadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleDeletePoint = async (id: number) => {
    try {
      await deleteSamplePoint(id)
      await reloadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const pendingParams = params.filter((p) => !p.approved)
  const approvedParams = params.filter((p) => p.approved)
  const pendingPoints = points.filter((p) => !p.approved)
  const approvedPoints = points.filter((p) => p.approved)

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-6 mt-4">
      <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">
        {t('catalog_title')}
      </h2>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {/* Parameters */}
      <div className="space-y-3">
        <h3 className="text-sm text-white font-medium">{t('catalog_parameters')}</h3>

        {pendingParams.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs uppercase text-yellow-600">{t('pending_approval')}</p>
            {pendingParams.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-2 text-sm text-gray-300">
                <span>{p.name} ({p.code})</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApproveParam(p.id)}
                    className="text-xs text-green-400 hover:underline"
                  >
                    {t('approve')}
                  </button>
                  <button
                    onClick={() => handleDeleteParam(p.id)}
                    className="text-xs text-red-400 hover:underline"
                  >
                    {t('delete')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-1">
          {approvedParams.map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-2 text-sm text-gray-400">
              <span>{p.name}{p.unit ? ` (${p.unit})` : ''}</span>
              <button
                onClick={() => handleDeleteParam(p.id)}
                className="text-xs text-red-400 hover:underline"
              >
                {t('delete')}
              </button>
            </div>
          ))}
        </div>

        <div className="flex gap-2 flex-wrap">
          <input
            value={newParamName}
            onChange={(e) => setNewParamName(e.target.value)}
            placeholder={t('name')}
            className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100 w-36"
          />
          <input
            value={newParamCode}
            onChange={(e) => setNewParamCode(e.target.value)}
            placeholder={t('code')}
            className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100 w-24"
          />
          <input
            value={newParamUnit}
            onChange={(e) => setNewParamUnit(e.target.value)}
            placeholder={t('unit')}
            className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100 w-20"
          />
          <button
            onClick={handleAddParam}
            disabled={!newParamName || !newParamCode}
            className="rounded-lg bg-blue-600 px-3 py-1 text-sm text-white disabled:bg-gray-700"
          >
            {t('add')}
          </button>
        </div>
      </div>

      {/* Sample Points */}
      <div className="space-y-3">
        <h3 className="text-sm text-white font-medium">{t('catalog_points')}</h3>

        {pendingPoints.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs uppercase text-yellow-600">{t('pending_approval')}</p>
            {pendingPoints.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-2 text-sm text-gray-300">
                <span>{p.name} ({p.code})</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprovePoint(p.id)}
                    className="text-xs text-green-400 hover:underline"
                  >
                    {t('approve')}
                  </button>
                  <button
                    onClick={() => handleDeletePoint(p.id)}
                    className="text-xs text-red-400 hover:underline"
                  >
                    {t('delete')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-1">
          {approvedPoints.map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-2 text-sm text-gray-400">
              <span>{p.name}</span>
              <button
                onClick={() => handleDeletePoint(p.id)}
                className="text-xs text-red-400 hover:underline"
              >
                {t('delete')}
              </button>
            </div>
          ))}
        </div>

        <div className="flex gap-2 flex-wrap">
          <input
            value={newPointName}
            onChange={(e) => setNewPointName(e.target.value)}
            placeholder={t('name')}
            className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100 w-36"
          />
          <input
            value={newPointCode}
            onChange={(e) => setNewPointCode(e.target.value)}
            placeholder={t('code')}
            className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100 w-24"
          />
          <input
            value={newPointDesc}
            onChange={(e) => setNewPointDesc(e.target.value)}
            placeholder={t('description')}
            className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100 w-40"
          />
          <button
            onClick={handleAddPoint}
            disabled={!newPointName || !newPointCode}
            className="rounded-lg bg-blue-600 px-3 py-1 text-sm text-white disabled:bg-gray-700"
          >
            {t('add')}
          </button>
        </div>
      </div>
    </div>
  )
}
