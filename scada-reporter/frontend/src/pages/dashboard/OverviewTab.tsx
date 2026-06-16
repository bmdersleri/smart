import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { tr } from 'date-fns/locale'
import { getDashboardDevices, getOverview, listPlcs } from '../../api/client'
import type { PlcEntry } from '../../api/client'

function StatCard({ label, value, sub, flash }: { label: string; value: string | number; sub?: string; flash?: boolean }) {
  return (
    <div className={`bg-gray-900 border rounded-xl p-4 transition-colors duration-300 ${flash ? 'border-cyan-600' : 'border-gray-800'}`}>
      <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-2xl font-bold transition-colors duration-300 ${flash ? 'text-cyan-400' : 'text-white'}`}>{value}</p>
      {sub && <p className="text-gray-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

function PlcActivityBar() {
  return (
    <div className="relative w-20 h-1.5 bg-gray-800 rounded-full overflow-hidden">
      <div className="absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-cyan-400 to-transparent rounded-full animate-[scan_1.8s_linear_infinite]" />
    </div>
  )
}

function PlcStatusDot({ connected }: { connected: boolean }) {
  if (!connected) {
    return <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
  }
  return (
    <span className="relative inline-flex w-2 h-2">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-60" />
      <span className="relative inline-flex w-2 h-2 rounded-full bg-green-400" />
    </span>
  )
}

function PlcRow({ plc, writeFlash }: { plc: PlcEntry; writeFlash: boolean }) {
  return (
    <tr className="border-t border-gray-800 hover:bg-gray-800/30 transition-colors">
      <td className="px-4 py-2.5 text-sm font-medium text-white">{plc.name}</td>
      <td className="px-4 py-2.5 text-xs font-mono text-gray-400">{plc.ip || '—'}</td>
      <td className="px-4 py-2.5 text-xs text-gray-500 text-right">{plc.tag_count}</td>
      <td className="px-4 py-2.5">
        <span className={`inline-flex items-center gap-2 text-xs font-medium px-2 py-0.5 rounded-full ${plc.connected ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
          <PlcStatusDot connected={plc.connected} />
          {plc.connected ? 'Bağlı' : 'Bağlantı Yok'}
        </span>
      </td>
      <td className="px-4 py-2.5">
        {plc.connected ? (
          <div className="flex items-center gap-2">
            <PlcActivityBar />
            <span className={`text-xs transition-colors duration-200 ${writeFlash ? 'text-cyan-400' : 'text-gray-600'}`}>
              {writeFlash ? '↑ DB' : '↓ PLC'}
            </span>
          </div>
        ) : (
          <span className="text-gray-700 text-xs">—</span>
        )}
      </td>
    </tr>
  )
}

export default function OverviewTab({ active }: { active: boolean }) {
  const [writeFlash, setWriteFlash] = useState(false)
  const lastReadingRef = useRef<string | null>(null)

  const { data: overview } = useQuery({
    queryKey: ['overview'],
    queryFn: () => getOverview().then((r) => r.data),
    refetchInterval: 10000,
    enabled: active,
  })
  const { data: devices = [] } = useQuery({
    queryKey: ['dashboard-devices'],
    queryFn: () => getDashboardDevices().then((r) => r.data),
    staleTime: 60000,
    enabled: active,
  })
  const { data: plcs = [] } = useQuery({
    queryKey: ['plcs'],
    queryFn: () => listPlcs().then((r) => r.data),
    refetchInterval: 15000,
    enabled: active,
  })

  // Flash DB write indicator when last_reading changes
  useEffect(() => {
    if (!overview?.last_reading) return
    if (lastReadingRef.current !== null && lastReadingRef.current !== overview.last_reading) {
      setWriteFlash(true)
      const t = setTimeout(() => setWriteFlash(false), 1500)
      return () => clearTimeout(t)
    }
    lastReadingRef.current = overview.last_reading
  }, [overview?.last_reading])

  const connectedCount = plcs.filter((p) => p.connected).length
  const plcLabel = plcs.length > 0 ? `${connectedCount}/${plcs.length}` : '...'
  const deviceCount = devices.length || undefined

  return (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Aktif Tag" value={overview?.active_tags ?? '—'} sub={`${deviceCount ?? '—'} cihaz`} />
        <StatCard label="Son 24 Saat Okuma" value={overview?.readings_24h?.toLocaleString('tr') ?? '—'} />
        <StatCard
          label="Son Veri"
          flash={writeFlash}
          value={overview?.last_reading ? format(parseISO(overview.last_reading + 'Z'), 'HH:mm:ss') : '—'}
          sub={overview?.last_reading ? format(parseISO(overview.last_reading + 'Z'), 'dd MMM yyyy', { locale: tr }) : undefined}
        />
        <StatCard label="PLC Bağlantı" value={plcLabel} sub="bağlı / toplam" />
      </div>

      {/* PLC status table */}
      {plcs.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">PLC Durumu</h2>
            {connectedCount > 0 && (
              <span className="flex items-center gap-1.5 text-xs text-cyan-500">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                Canlı veri akışı
              </span>
            )}
          </div>
          <table className="w-full">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-2 text-left">PLC Adı</th>
                <th className="px-4 py-2 text-left">IP</th>
                <th className="px-4 py-2 text-right">Tag</th>
                <th className="px-4 py-2 text-left">Durum</th>
                <th className="px-4 py-2 text-left">Aktivite</th>
              </tr>
            </thead>
            <tbody>
              {plcs.map((plc) => (
                <PlcRow key={plc.name} plc={plc} writeFlash={writeFlash} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
