// Timezone-aware helpers for lab data entry. The configured IANA timezone
// governs the entry default + display; sampled_at is stored UTC.

function tzParts(tz: string, date: Date): Record<string, string> {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
  const out: Record<string, string> = {}
  for (const part of fmt.formatToParts(date)) {
    if (part.type !== 'literal') out[part.type] = part.value
  }
  if (out.hour === '24') out.hour = '00' // some engines emit 24 at midnight
  return out
}

// The current wall-clock in `tz` as a datetime-local value (no UTC shift).
export function nowInTz(tz: string): string {
  const p = tzParts(tz, new Date())
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

// The signed offset (ms) of `tz` at `date`: (wall-clock-as-UTC) - actual UTC.
function tzOffsetMs(tz: string, date: Date): number {
  const p = tzParts(tz, date)
  const asUtc = Date.UTC(
    Number(p.year),
    Number(p.month) - 1,
    Number(p.day),
    Number(p.hour),
    Number(p.minute),
    Number(p.second),
  )
  return asUtc - date.getTime()
}

// A datetime-local `value` (interpreted as a wall-clock in `tz`) -> UTC ISO.
export function wallclockToUtcIso(value: string, tz: string): string {
  const naiveUtc = new Date(`${value}:00Z`).getTime()
  const off = tzOffsetMs(tz, new Date(naiveUtc))
  return new Date(naiveUtc - off).toISOString()
}

// A stored UTC ISO -> datetime-local value in `tz` (edit-form prefill).
export function utcToTzInput(iso: string, tz: string): string {
  const p = tzParts(tz, new Date(iso))
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

// A stored UTC ISO -> human display in `tz`.
export function utcToTzDisplay(iso: string, tz: string, locale = 'tr'): string {
  return new Date(iso).toLocaleString(locale, { timeZone: tz })
}
