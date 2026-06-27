import { describe, expect, it } from 'vitest'
import { nowInTz, utcToTzInput, wallclockToUtcIso } from './labTime'

describe('labTime', () => {
  it('wallclockToUtcIso treats the value as Istanbul wall-clock (+03)', () => {
    expect(wallclockToUtcIso('2026-06-27T12:00', 'Europe/Istanbul')).toBe(
      '2026-06-27T09:00:00.000Z',
    )
  })
  it('wallclockToUtcIso is identity-ish for UTC', () => {
    expect(wallclockToUtcIso('2026-06-27T09:00', 'UTC')).toBe('2026-06-27T09:00:00.000Z')
  })
  it('utcToTzInput renders a UTC instant in Istanbul local (+03)', () => {
    expect(utcToTzInput('2026-06-27T09:00:00.000Z', 'Europe/Istanbul')).toBe('2026-06-27T12:00')
  })
  it('round-trips wall-clock -> utc -> wall-clock', () => {
    const utc = wallclockToUtcIso('2026-06-27T08:30', 'Europe/Istanbul')
    expect(utcToTzInput(utc, 'Europe/Istanbul')).toBe('2026-06-27T08:30')
  })
  it('nowInTz returns a YYYY-MM-DDTHH:mm string', () => {
    expect(nowInTz('UTC')).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
  })
  it('handles a DST zone in summer (Berlin = +02)', () => {
    expect(wallclockToUtcIso('2026-07-15T12:00', 'Europe/Berlin')).toBe('2026-07-15T10:00:00.000Z')
    expect(utcToTzInput('2026-07-15T10:00:00.000Z', 'Europe/Berlin')).toBe('2026-07-15T12:00')
  })
})
