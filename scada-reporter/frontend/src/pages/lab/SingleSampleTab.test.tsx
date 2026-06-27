import { describe, expect, it } from 'vitest'
import { canCreate, isOutOfRange } from './SingleSampleTab'

describe('isOutOfRange', () => {
  it('returns false when within limits', () => {
    expect(isOutOfRange(7.2, 6.5, 9.0)).toBe(false)
  })
  it('returns true below min', () => {
    expect(isOutOfRange(5.0, 6.5, 9.0)).toBe(true)
  })
  it('returns true above max', () => {
    expect(isOutOfRange(9.9, 6.5, 9.0)).toBe(true)
  })
  it('returns false when limits are null', () => {
    expect(isOutOfRange(123, null, null)).toBe(false)
  })
  it('returns false for empty value', () => {
    expect(isOutOfRange(null, 6.5, 9.0)).toBe(false)
  })
})

describe('canCreate', () => {
  it('returns true when both code and name are non-empty', () => {
    expect(canCreate('PH', 'pH')).toBe(true)
  })
  it('returns false when code is empty', () => {
    expect(canCreate('', 'pH')).toBe(false)
  })
  it('returns false when name is empty', () => {
    expect(canCreate('PH', '')).toBe(false)
  })
  it('returns false when both are empty', () => {
    expect(canCreate('', '')).toBe(false)
  })
  it('returns false when code is whitespace only', () => {
    expect(canCreate('   ', 'pH')).toBe(false)
  })
})
