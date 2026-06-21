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
