// Presentational helpers shared by the Dashboard System + Database tabs.

export function StatCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-semibold mt-1 font-mono ${accent ?? 'text-white'}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

export function fmtMs(s: number | null): string {
  if (s === null) return '—'
  return `${(s * 1000).toFixed(1)} ms`
}

export function fmtPct(r: number | null): string {
  if (r === null) return '—'
  return `${(r * 100).toFixed(2)} %`
}
