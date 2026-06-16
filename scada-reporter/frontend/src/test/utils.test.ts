import { describe, it, expect } from 'vitest'

// Utility: format a numeric value with fixed decimals
function formatValue(value: number | null, unit: string): string {
  if (value === null) return '—'
  return `${value.toFixed(2)}${unit ? ` ${unit}` : ''}`
}

describe('formatValue', () => {
  it('formats number with unit', () => {
    expect(formatValue(12.5, 'm³/h')).toBe('12.50 m³/h')
  })

  it('formats number without unit', () => {
    expect(formatValue(0.1, '')).toBe('0.10')
  })

  it('returns dash for null', () => {
    expect(formatValue(null, 'm³/h')).toBe('—')
  })

  it('rounds to 2 decimal places', () => {
    expect(formatValue(3.14159, 'bar')).toBe('3.14 bar')
  })
})
