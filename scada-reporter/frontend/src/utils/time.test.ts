import { describe, it, expect } from 'vitest'
import { parseUtc, formatUptime } from './time'

const UTC_1400 = Date.UTC(2026, 5, 20, 14, 0, 0)

describe('parseUtc', () => {
  it('parses an explicit +00:00 offset to the right instant', () => {
    expect(parseUtc('2026-06-20T14:00:00+00:00').getTime()).toBe(UTC_1400)
  })

  it('parses a Z-suffixed string', () => {
    expect(parseUtc('2026-06-20T14:00:00Z').getTime()).toBe(UTC_1400)
  })

  it('assumes UTC for a legacy offset-less string', () => {
    expect(parseUtc('2026-06-20T14:00:00').getTime()).toBe(UTC_1400)
  })

  it('respects a non-UTC offset', () => {
    expect(parseUtc('2026-06-20T17:00:00+03:00').getTime()).toBe(UTC_1400)
  })
})

describe('formatUptime', () => {
  it('shows minutes only under an hour', () => {
    expect(formatUptime(90, 'en')).toBe('1m')
  })

  it('shows hours and minutes under a day', () => {
    expect(formatUptime(3661, 'en')).toBe('1h 1m')
  })

  it('shows days and hours over a day', () => {
    expect(formatUptime(90061, 'en')).toBe('1d 1h')
  })

  it('handles zero seconds', () => {
    expect(formatUptime(0, 'en')).toBe('0m')
  })
})
