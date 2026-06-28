import type { ReactNode } from 'react'

// A compact counter/stat card, mirroring the StatCard used on the Metrics page.
export function StatCard({
  label,
  value,
  accent,
  onClick,
}: {
  label: string
  value: string | number
  accent?: string
  onClick?: () => void
}) {
  return (
    <div
      className={`bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 ${
        onClick ? 'cursor-pointer hover:border-cyan-500/30 transition-colors' : ''
      }`}
      onClick={onClick}
    >
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-semibold mt-1 font-mono ${accent ?? 'text-white'}`}>{value}</p>
    </div>
  )
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl ${
        className ?? ''
      }`}
    >
      {children}
    </div>
  )
}
