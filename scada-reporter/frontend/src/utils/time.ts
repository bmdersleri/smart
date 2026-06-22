import { parseISO } from 'date-fns'

/**
 * Parse a backend ISO timestamp as a UTC instant.
 *
 * The API now emits an explicit UTC offset (`…+00:00`). This helper also
 * tolerates legacy offset-less strings by assuming UTC, so call sites never
 * hand-append `'Z'`. Rendering (local time via date-fns `format`) is unchanged.
 */
export function parseUtc(s: string): Date {
  const hasOffset = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(s)
  return parseISO(hasOffset ? s : s + 'Z')
}

function unit(value: number, u: 'day' | 'hour' | 'minute', lang: string): string {
  return value.toLocaleString(lang, { style: 'unit', unit: u, unitDisplay: 'narrow' })
}

/**
 * Compact, locale-aware uptime string from a second count.
 *
 * Shows the two largest meaningful units: days+hours over a day, hours+minutes
 * under a day, minutes only under an hour (Intl narrow units → "1d 1h" / "1h 1m"
 * / "1m", localized by `lang`).
 */
export function formatUptime(seconds: number, lang: string): string {
  const total = Math.max(0, Math.floor(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)

  if (days > 0) return `${unit(days, 'day', lang)} ${unit(hours, 'hour', lang)}`
  if (hours > 0) return `${unit(hours, 'hour', lang)} ${unit(minutes, 'minute', lang)}`
  return unit(minutes, 'minute', lang)
}
