import { useQuery } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { tr } from 'date-fns/locale'
import { getDashboardDevices, getOverview } from '../../api/client'

interface HealthPlc { name: string; ip: string; connected: boolean }
interface HealthResp { plc_connected?: number; plc_total?: number; plcs?: HealthPlc[] }

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-gray-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

export default function OverviewTab({ active }: { active: boolean }) {
  const { data: overview } = useQuery({
    queryKey: ['overview'],
    queryFn: () => getOverview().then((r) => r.data),
    refetchInterval: 10000,
    enabled: active,
  })
  const { data: health } = useQuery<HealthResp>({
    queryKey: ['health'],
    queryFn: () => fetch('/health').then((r) => r.json()),
    refetchInterval: 10000,
    enabled: active,
  })
  const { data: deviceCount } = useQuery({
    queryKey: ['dashboard-devices'],
    queryFn: () => getDashboardDevices().then((r) => r.data.length),
    staleTime: 60000,
    enabled: active,
  })

  const plcLabel = health == null ? '...' : `${health.plc_connected ?? 0}/${health.plc_total ?? 0}`

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Aktif Tag" value={overview?.active_tags ?? '—'} sub={`${deviceCount ?? '—'} cihaz`} />
        <StatCard label="Son 24 Saat Okuma" value={overview?.readings_24h?.toLocaleString('tr') ?? '—'} />
        <StatCard
          label="Son Veri"
          value={overview?.last_reading ? format(parseISO(overview.last_reading + 'Z'), 'HH:mm:ss') : '—'}
          sub={overview?.last_reading ? format(parseISO(overview.last_reading + 'Z'), 'dd MMM yyyy', { locale: tr }) : undefined}
        />
        <StatCard label="PLC Bağlantı" value={plcLabel} sub="bağlı / toplam" />
      </div>

      {health?.plcs && health.plcs.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800">
            <h2 className="text-sm font-semibold text-white">PLC Durumu</h2>
          </div>
          <table className="w-full">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-2 text-left">Cihaz</th>
                <th className="px-4 py-2 text-left">IP</th>
                <th className="px-4 py-2 text-left">Durum</th>
              </tr>
            </thead>
            <tbody>
              {health.plcs.map((plc) => (
                <tr key={plc.ip} className="border-t border-gray-800 hover:bg-gray-800/40">
                  <td className="px-4 py-2 text-sm text-white">{plc.name}</td>
                  <td className="px-4 py-2 text-sm text-gray-400 font-mono">{plc.ip}</td>
                  <td className="px-4 py-2">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${plc.connected ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${plc.connected ? 'bg-green-400' : 'bg-red-400'}`} />
                      {plc.connected ? 'Bağlı' : 'Bağlantı Yok'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
