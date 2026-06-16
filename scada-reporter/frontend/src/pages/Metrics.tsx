import { useQuery } from '@tanstack/react-query'
import { getMetrics } from '../api/client'
import type { MetricsSummary } from '../api/client'
import { useSortable } from '../hooks/useSortable'
import SortHeader from '../components/SortHeader'

function StatCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-semibold mt-1 font-mono ${accent ?? 'text-white'}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function fmtMs(s: number | null): string {
  if (s === null) return '—'
  return `${(s * 1000).toFixed(1)} ms`
}

function fmtPct(r: number | null): string {
  if (r === null) return '—'
  return `${(r * 100).toFixed(2)} %`
}

export default function Metrics() {
  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['metrics'],
    queryFn: () => getMetrics().then((r) => r.data),
    refetchInterval: 2000,
  })

  const m: MetricsSummary | undefined = data
  const maxAvg = m?.plcs.reduce((acc, p) => Math.max(acc, p.avg_seconds ?? 0), 0) || 0
  const badAccent =
    m?.bad_ratio == null ? 'text-white' : m.bad_ratio > 0.05 ? 'text-red-400' : 'text-green-400'

  // varsayılan: en yavaş PLC üstte; başlığa tıklayınca yeniden sıralanır
  const byAvg = [...(m?.plcs ?? [])].sort((a, b) => (b.avg_seconds ?? 0) - (a.avg_seconds ?? 0))
  const { sorted: plcRows, sort, toggle } = useSortable(byAvg)

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Canlı Metrikler</h1>
          <p className="text-sm text-gray-500">Poller / PLC okuma sağlığı — 2 sn'de bir güncellenir</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          {dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : 'bağlanıyor...'}
        </div>
      </div>

      {isLoading && <div className="text-center py-16 text-gray-500">Yükleniyor...</div>}
      {isError && <div className="text-center py-16 text-red-400">Metrikler alınamadı.</div>}

      {m && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Yazılan Satır" value={m.rows_written_total.toLocaleString()} sub="toplam (DB)" accent="text-cyan-300" />
            <StatCard label="BAD Kalite" value={m.bad_quality_total.toLocaleString()} sub="toplam okuma" accent={badAccent} />
            <StatCard label="BAD Oranı" value={fmtPct(m.bad_ratio)} sub="bad / toplam" accent={badAccent} />
            <StatCard label="Ortalama Tick" value={fmtMs(m.tick_avg_seconds)} sub={`${m.tick_count.toLocaleString()} tick`} accent="text-blue-300" />
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800">
              <h2 className="text-sm font-medium text-white">PLC Okuma Gecikmeleri</h2>
              <p className="text-xs text-gray-500">PLC başına ortalama batch okuma süresi ({m.plcs.length} PLC)</p>
            </div>
            <table className="w-full">
              <thead>
                <tr className="text-xs text-gray-500 uppercase tracking-wide">
                  <SortHeader label="PLC Adı" sortKey="name" sort={sort} onToggle={toggle} />
                  <SortHeader label="IP" sortKey="plc" sort={sort} onToggle={toggle} />
                  <SortHeader label="Tag Sayısı" sortKey="tag_count" sort={sort} onToggle={toggle} align="right" />
                  <SortHeader label="Okuma Sayısı" sortKey="count" sort={sort} onToggle={toggle} align="right" />
                  <SortHeader label="Ort. Süre" sortKey="avg_seconds" sort={sort} onToggle={toggle} align="right" />
                  <th className="px-4 py-2 text-left w-1/4">Gecikme</th>
                </tr>
              </thead>
              <tbody>
                {plcRows
                  .map((p) => {
                    const pct = maxAvg > 0 ? ((p.avg_seconds ?? 0) / maxAvg) * 100 : 0
                    const slow = (p.avg_seconds ?? 0) > 0.5
                    return (
                      <tr key={p.plc} className="border-t border-gray-800 hover:bg-gray-800/40">
                        <td className="px-4 py-2 text-sm text-white">{p.name || '—'}</td>
                        <td className="px-4 py-2 text-sm font-mono text-gray-400">{p.plc}</td>
                        <td className="px-4 py-2 text-sm text-right text-gray-300 font-mono">{p.tag_count.toLocaleString()}</td>
                        <td className="px-4 py-2 text-sm text-right text-gray-400 font-mono">{p.count.toLocaleString()}</td>
                        <td className={`px-4 py-2 text-sm text-right font-mono ${slow ? 'text-red-400' : 'text-gray-200'}`}>{fmtMs(p.avg_seconds)}</td>
                        <td className="px-4 py-2">
                          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${slow ? 'bg-red-500' : 'bg-blue-500'}`} style={{ width: `${pct}%` }} />
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                {m.plcs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-500 text-sm">
                      Henüz PLC okuma metriği yok (poller ısınıyor).
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
