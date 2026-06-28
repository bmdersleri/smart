// Pure formatting / date helpers for the Compliance Center. Kept separate from
// helpers.tsx (which exports React components) so Fast Refresh stays happy.

// "first day of the current month" → datetime-local value (00:00 local).
export function startOfMonthISO(d = new Date()): string {
  const local = new Date(d.getFullYear(), d.getMonth(), 1, 0, 0, 0)
  return toLocalInputValue(local)
}

export function nowISO(d = new Date()): string {
  return toLocalInputValue(d)
}

// datetime-local input expects "YYYY-MM-DDTHH:mm" in local time (no Z).
export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(
    d.getMinutes(),
  )}`
}

export function fmtDateTime(s: string | null, locale: string): string {
  if (!s) return '—'
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleString(locale)
}

export function fmtNum(n: number | null): string {
  if (n === null || n === undefined) return '—'
  return Number.isInteger(n) ? String(n) : n.toFixed(3)
}
