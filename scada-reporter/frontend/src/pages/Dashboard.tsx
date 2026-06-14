import { useQuery } from '@tanstack/react-query'
import { getCurrentValues, getOverview } from '../api/client'
import type { CurrentValue } from '../api/client'
import { format, parseISO } from 'date-fns'
import { tr } from 'date-fns/locale'

function QualityDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-green-400' : 'bg-red-400'}`} />
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-gray-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

function TagRow({ tv }: { tv: CurrentValue }) {
  const val = tv.value !== null ? `${tv.value.toFixed(2)} ${tv.unit}` : '—'
  const ts = tv.timestamp ? format(parseISO(tv.timestamp), 'HH:mm:ss', { locale: tr }) : '—'
  return (
    <tr className="border-t border-gray-800 hover:bg-gray-800/40 transition-colors">
      <td className="px-4 py-3 text-sm text-gray-300">{tv.device}</td>
      <td className="px-4 py-3 text-sm text-white font-medium">{tv.name}</td>
      <td className="px-4 py-3 text-sm text-right font-mono text-cyan-300">{val}</td>
      <td className="px-4 py-3 text-sm text-gray-400 text-right">{ts}</td>
      <td className="px-4 py-3 text-right">
        <QualityDot ok={tv.quality_ok} />
      </td>
    </tr>
  )
}

export default function Dashboard() {
  const { data: overview } = useQuery({ queryKey: ['overview'], queryFn: () => getOverview().then((r) => r.data), refetchInterval: 10000 })
  const { data: values = [], isLoading } = useQuery({ queryKey: ['current-values'], queryFn: () => getCurrentValues().then((r) => r.data), refetchInterval: 5000 })

  const byDevice = values.reduce<Record<string, CurrentValue[]>>((acc, v) => {
    const d = v.device || 'Diğer';
    (acc[d] ??= []).push(v)
    return acc
  }, {})

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Dashboard</h1>
        <span className="text-xs text-gray-500">5 sn'de bir güncellenir</span>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Aktif Tag" value={overview?.active_tags ?? '—'} />
        <StatCard label="Son 24 Saat Okuma" value={overview?.readings_24h?.toLocaleString('tr') ?? '—'} />
        <StatCard
          label="Son Veri"
          value={overview?.last_reading ? format(parseISO(overview.last_reading), 'HH:mm:ss') : '—'}
          sub={overview?.last_reading ? format(parseISO(overview.last_reading), 'dd MMM yyyy', { locale: tr }) : undefined}
        />
      </div>

      {/* Live values table */}
      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Yükleniyor...</div>
      ) : values.length === 0 ? (
        <div className="text-center py-16 bg-gray-900 rounded-xl border border-gray-800">
          <p className="text-gray-400">Henüz tag eklenmemiş.</p>
          <p className="text-gray-500 text-sm mt-1">Tag Yönetimi sayfasından PLC tag'lerini ekleyin.</p>
        </div>
      ) : (
        Object.entries(byDevice).map(([device, tvs]) => (
          <div key={device} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-sm font-semibold text-white">{device}</span>
              <span className="text-xs text-gray-500">({tvs.length} tag)</span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="text-xs text-gray-500 uppercase tracking-wide">
                  <th className="px-4 py-2 text-left">Cihaz</th>
                  <th className="px-4 py-2 text-left">Tag</th>
                  <th className="px-4 py-2 text-right">Değer</th>
                  <th className="px-4 py-2 text-right">Saat</th>
                  <th className="px-4 py-2 text-right">Kalite</th>
                </tr>
              </thead>
              <tbody>
                {tvs.map((tv) => <TagRow key={tv.tag_id} tv={tv} />)}
              </tbody>
            </table>
          </div>
        ))
      )}
    </div>
  )
}
