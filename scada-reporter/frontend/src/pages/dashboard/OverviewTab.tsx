import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import { enUS, tr, ru, de } from 'date-fns/locale'
import { getDashboardDevices, getOverview, listPlcs, getDeadbandSavings, getHealth } from '../../api/client'
import { parseUtc, formatUptime } from '../../utils/time'
import type { PlcEntry } from '../../api/client'

// date-fns locale follows the active language (month/day names)
const DATE_LOCALES: Record<string, typeof tr> = { en: enUS, tr, ru, de }

// shorten large numbers using the active locale: 63,396,597 -> "63.4M" (en) / "63,4 Mio." (de)
function fmtCompact(n: number, lang: string): string {
  return n.toLocaleString(lang, { notation: 'compact', maximumFractionDigits: 1 })
}

// locale-aware percent placement: tr "%92,9" / en "92.9%" / de "92,9 %" (value is 0-100)
function fmtPercent(n: number, lang: string): string {
  return (n / 100).toLocaleString(lang, { style: 'percent', maximumFractionDigits: 1 })
}

// ── Stat card ──────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, flash, flip, accent }: {
  label: string
  value: string | number
  sub?: string
  flash?: boolean
  flip?: boolean   // animates value on change
  accent?: string  // color class for value e.g. 'text-green-400'
}) {
  return (
    <div className={`relative bg-surface-raised/40 backdrop-blur-xl border rounded-2xl p-5 transition-all duration-300 shadow-xl overflow-hidden group
      ${flash ? 'border-cyan-500/50 shadow-[0_0_20px_rgba(6,182,212,0.15)] bg-cyan-950/10' : 'border-white/5 hover:border-white/10 hover:bg-surface-raised/60'}`}>
      {/* Background gradients for premium feel */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.02] to-transparent pointer-events-none" />
      <div className={`absolute top-0 right-0 w-32 h-32 rounded-full transition-opacity duration-500 blur-3xl opacity-0 group-hover:opacity-10 pointer-events-none
        ${flash ? 'bg-cyan-500' : 'bg-white'}`} />

      <p className="text-gray-400 text-[11px] font-semibold uppercase tracking-wider mb-2 relative z-10">{label}</p>
      <div className="overflow-hidden h-10 relative z-10 flex items-center">
        <p
          key={flip ? String(value) : undefined}
          className={`text-3xl font-bold tracking-tight transition-colors duration-300
            ${flash ? 'text-cyan-300 drop-shadow-[0_0_8px_rgba(103,232,249,0.5)]' : (accent ?? 'text-white')}
            ${flip ? 'animate-flip-in' : ''}`}
        >
          {value}
        </p>
      </div>
      {sub && <p className="text-gray-500 text-xs mt-1.5 font-medium relative z-10">{sub}</p>}
    </div>
  )
}

// ── Packet-dot flow (3 staggered dots) ────────────────────────────────────

function PacketFlow() {
  return (
    <div className="relative w-24 h-3 flex items-center">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="absolute w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_4px_rgba(6,182,212,0.8)]"
          style={{ animation: `packet 2s linear ${i * 0.65}s infinite` }}
        />
      ))}
    </div>
  )
}

// ── Connecting animation (disconnected PLC) ───────────────────────────────

function ConnectingDots() {
  return (
    <span className="flex gap-0.5 items-center">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1 h-1 rounded-full bg-red-500"
          style={{ animation: `blink 1.2s ease-in-out ${i * 0.3}s infinite` }}
        />
      ))}
    </span>
  )
}

// ── DB write counter badge ────────────────────────────────────────────────

function WriteCounter({ count, flash }: { count: number; flash: boolean }) {
  const { t, i18n } = useTranslation('dashboard')
  return (
    <div className={`flex items-center gap-1.5 text-xs transition-all duration-300 ${flash ? 'text-cyan-400' : 'text-gray-600'}`}>
      <span className={`text-base leading-none transition-transform duration-200 ${flash ? 'translate-y-[-2px]' : ''}`}>
        ↑
      </span>
      <span className="font-mono tabular-nums">{count.toLocaleString(i18n.language)}</span>
      <span>{t('writes')}</span>
    </div>
  )
}

// ── Mini topology header ───────────────────────────────────────────────────

function TopologyBar({ connectedCount, total, writeFlash }: {
  connectedCount: number; total: number; writeFlash: boolean
}) {
  if (total === 0) return null
  return (
    <div className="flex items-center justify-center gap-4 py-3.5 px-5 bg-black/20 backdrop-blur-lg border-b border-white/5 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-950/10 to-transparent pointer-events-none" />
      {/* PLC side */}
      <div className="flex items-center gap-1.5">
        <span className="text-gray-500 text-xs font-mono">PLC</span>
        <div className="flex gap-1">
          {Array.from({ length: Math.min(total, 6) }).map((_, i) => (
            <span
              key={i}
              className={`w-2 h-3 rounded-sm ${i < connectedCount ? 'bg-green-500' : 'bg-gray-700'}`}
            />
          ))}
          {total > 6 && <span className="text-gray-600 text-xs">+{total - 6}</span>}
        </div>
      </div>

      {/* Flow arrow with packets */}
      <div className="flex-1 max-w-[140px] relative flex items-center">
        <div className="w-full h-px bg-gray-700" />
        {connectedCount > 0 && (
          <div className="absolute inset-0 overflow-hidden flex items-center">
            {[0, 1, 2, 3].map((i) => (
              <span
                key={i}
                className="absolute w-2 h-px bg-gradient-to-r from-cyan-400/0 via-cyan-400 to-cyan-400/0"
                style={{ animation: `flowArrow 1.6s linear ${i * 0.4}s infinite` }}
              />
            ))}
          </div>
        )}
        <span className={`absolute right-0 text-xs transition-colors duration-300 ${connectedCount > 0 ? 'text-cyan-500' : 'text-gray-700'}`}>▶</span>
      </div>

      {/* DB side */}
      <div className={`flex items-center gap-1.5 transition-all duration-300 ${writeFlash ? 'text-cyan-400' : 'text-gray-500'}`}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" opacity="0.8">
          <ellipse cx="12" cy="6" rx="8" ry="3" />
          <path d="M4 6v4c0 1.66 3.58 3 8 3s8-1.34 8-3V6" />
          <path d="M4 10v4c0 1.66 3.58 3 8 3s8-1.34 8-3v-4" />
          <path d="M4 14v4c0 1.66 3.58 3 8 3s8-1.34 8-3v-4" />
        </svg>
        <span className="text-xs font-mono">DB</span>
        {writeFlash && (
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
        )}
      </div>
    </div>
  )
}

// ── PLC card ──────────────────────────────────────────────────────────────

function PlcCard({ plc, writeFlash }: { plc: PlcEntry; writeFlash: boolean }) {
  const { t, i18n } = useTranslation('dashboard')
  const isConnected = plc.connected
  const [hovered, setHovered] = useState(false)

  return (
    <div
      className={`relative bg-surface-raised/40 backdrop-blur-xl border rounded-2xl p-5 transition-all duration-300 overflow-hidden cursor-default group
        ${isConnected
          ? writeFlash
            ? 'border-cyan-500/40 shadow-[0_0_24px_rgba(6,182,212,0.15)] bg-cyan-950/20'
            : hovered
              ? 'border-cyan-500/30 shadow-[0_8px_32px_rgba(6,182,212,0.1)] -translate-y-1 bg-surface-raised/60'
              : 'border-white/5 hover:border-white/10'
          : hovered
            ? 'border-red-500/30 shadow-[0_8px_32px_rgba(239,68,68,0.1)] -translate-y-1 bg-surface-raised/60'
            : 'border-white/5'
        }`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Hover gradient reveal */}
      <div className={`absolute inset-0 pointer-events-none transition-opacity duration-300 rounded-2xl
        ${isConnected
          ? 'bg-gradient-to-br from-cyan-500/5 via-transparent to-transparent'
          : 'bg-gradient-to-br from-red-500/5 via-transparent to-transparent'}
        ${hovered ? 'opacity-100' : 'opacity-0'}`}
      />

      {/* Corner accent on hover */}
      <div className={`absolute top-0 right-0 w-12 h-12 pointer-events-none transition-opacity duration-200
        ${hovered ? 'opacity-100' : 'opacity-0'}`}>
        <div className={`absolute top-0 right-0 w-px h-6 ${isConnected ? 'bg-cyan-500/60' : 'bg-red-500/40'}`} />
        <div className={`absolute top-0 right-0 h-px w-6 ${isConnected ? 'bg-cyan-500/60' : 'bg-red-500/40'}`} />
      </div>

      {/* Subtle scan sweep on connected PLCs */}
      {isConnected && (
        <div
          className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/4 to-transparent pointer-events-none"
          style={{ animation: 'cardSweep 3s ease-in-out infinite' }}
        />
      )}

      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className={`text-sm font-semibold leading-tight transition-colors duration-150 ${hovered ? 'text-white' : 'text-gray-200'}`}>
            {plc.name}
          </p>
          <p className={`text-xs font-mono mt-0.5 transition-colors duration-150 ${hovered ? 'text-gray-300' : 'text-gray-500'}`}>
            {plc.ip || t('plc_no_ip')}
          </p>
        </div>
        <span className={`text-xs px-2.5 py-1 rounded-md font-semibold tracking-wide transition-all duration-200
          ${isConnected
            ? hovered ? 'bg-green-500/20 text-green-300 ring-1 ring-green-500/30' : 'bg-green-500/10 text-green-400'
            : hovered ? 'bg-red-500/20 text-red-300 ring-1 ring-red-500/30' : 'bg-red-500/10 text-red-400'
          }`}>
          {t('plc_tag_count', { value: plc.tag_count.toLocaleString(i18n.language) })}
        </span>
      </div>

      {/* Status row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isConnected ? (
            <>
              <span className="relative inline-flex w-2 h-2 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-50" />
                <span className="relative inline-flex w-2 h-2 rounded-full bg-green-400" />
              </span>
              <span className="text-xs text-green-400 font-medium">{t('plc_connected')}</span>
            </>
          ) : (
            <>
              <ConnectingDots />
              <span className="text-xs text-red-500">{t('plc_disconnected')}</span>
            </>
          )}
        </div>

        {/* Activity */}
        {isConnected ? (
          <div className="flex flex-col items-end gap-1">
            <PacketFlow />
            <span className={`text-[10px] transition-colors duration-200 ${writeFlash ? 'text-cyan-400' : 'text-gray-600'}`}>
              {writeFlash ? t('plc_writing_db') : t('plc_reading_data')}
            </span>
          </div>
        ) : (
          <span className="text-gray-700 text-xs">—</span>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────

export default function OverviewTab({ active }: { active: boolean }) {
  const { t, i18n } = useTranslation('dashboard')
  const [writeFlash, setWriteFlash] = useState(false)
  const [writeCount, setWriteCount] = useState(0)
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
  const { data: savings } = useQuery({
    queryKey: ['deadbandSavings'],
    queryFn: () => getDeadbandSavings(24).then((r) => r.data),
    refetchInterval: 30000,
    enabled: active,
  })
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => getHealth().then((r) => r.data),
    refetchInterval: 30000,
    enabled: active,
  })

  // Flash + increment counter when last_reading changes
  useEffect(() => {
    if (!overview?.last_reading) return
    if (lastReadingRef.current !== null && lastReadingRef.current !== overview.last_reading) {
      setWriteFlash(true)
      setWriteCount((c) => c + 1)
      const t = setTimeout(() => setWriteFlash(false), 1800)
      return () => clearTimeout(t)
    }
    lastReadingRef.current = overview.last_reading
  }, [overview?.last_reading])

  const connectedCount = plcs.filter((p) => p.connected).length
  const plcLabel = plcs.length > 0 ? `${connectedCount}/${plcs.length}` : '...'
  const deviceCount = devices.length || undefined

  const readRate = overview?.readings_1h != null
    ? overview.readings_1h < 60
      ? t('rate_reads_per_hour', { value: overview.readings_1h.toLocaleString(i18n.language) })
      : t('rate_reads_per_min', { value: Math.round(overview.readings_1h / 60).toLocaleString(i18n.language) })
    : '—'

  const qualityAccent = overview?.quality_rate == null
    ? 'text-white'
    : overview.quality_rate >= 90
      ? 'text-green-400'
      : overview.quality_rate >= 70
        ? 'text-yellow-400'
        : 'text-red-400'

  const lastTs = overview?.last_reading
    ? format(parseUtc(overview.last_reading), 'HH:mm:ss')
    : '—'

  return (
    <div className="space-y-6">
      {/* Stat cards — 6 cards, 2 rows */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard
          label={t('stat_active_tags')}
          value={overview?.active_tags ?? '—'}
          sub={t('stat_devices', { value: deviceCount != null ? deviceCount.toLocaleString(i18n.language) : '—' })}
        />
        <StatCard
          label={t('stat_readings_24h')}
          value={overview?.readings_24h?.toLocaleString(i18n.language) ?? '—'}
        />
        <StatCard
          label={t('stat_readings_1h')}
          value={overview?.readings_1h?.toLocaleString(i18n.language) ?? '—'}
          sub={readRate}
          flip
        />
        <StatCard
          label={t('stat_data_quality')}
          value={overview?.quality_rate != null ? fmtPercent(overview.quality_rate, i18n.language) : '—'}
          sub={t('stat_quality_sub')}
          accent={qualityAccent}
          flip
        />
        <StatCard
          label={t('stat_last_data')}
          flash={writeFlash}
          flip
          value={lastTs}
          sub={overview?.last_reading
            ? format(parseUtc(overview.last_reading), 'dd MMM yyyy', { locale: DATE_LOCALES[i18n.language] ?? enUS })
            : undefined}
        />
        <StatCard label={t('stat_plc_connection')} value={plcLabel} sub={t('stat_plc_sub')} />
        <StatCard
          label={t('stat_deadband_savings')}
          value={savings?.savings_pct != null ? fmtPercent(savings.savings_pct, i18n.language) : '—'}
          sub={savings ? t('saved_rows_per_day', { value: fmtCompact(savings.saved_rows_per_day, i18n.language) }) : t('stat_deadband_sub_24h')}
          accent="text-emerald-400"
        />
        <StatCard
          label={t('stat_uptime')}
          value={health?.uptime_seconds != null ? formatUptime(health.uptime_seconds, i18n.language) : '—'}
          sub={health?.started_at
            ? t('uptime_since', { value: format(parseUtc(health.started_at), 'dd MMM HH:mm', { locale: DATE_LOCALES[i18n.language] ?? enUS }) })
            : t('stat_uptime_sub')}
          accent="text-cyan-400"
        />
      </div>

      {/* PLC section */}
      {plcs.length > 0 && (
        <div className="bg-surface-raised/30 backdrop-blur-xl border border-white/5 rounded-3xl overflow-hidden shadow-2xl ring-1 ring-white/5">
          {/* Header */}
          <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between bg-gradient-to-r from-white/[0.02] to-transparent">
            <h2 className="text-sm font-bold tracking-wide text-white uppercase">{t('plc_status')}</h2>
            <div className="flex items-center gap-4">
              {writeCount > 0 && (
                <WriteCounter count={writeCount} flash={writeFlash} />
              )}
              {connectedCount > 0 && (
                <span className="flex items-center gap-1.5 text-xs text-cyan-500">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  {t('live')}
                </span>
              )}
            </div>
          </div>

          {/* Topology bar */}
          <TopologyBar
            connectedCount={connectedCount}
            total={plcs.length}
            writeFlash={writeFlash}
          />

          {/* PLC cards grid */}
          <div className="p-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {plcs.map((plc) => (
              <PlcCard key={plc.name} plc={plc} writeFlash={writeFlash} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
