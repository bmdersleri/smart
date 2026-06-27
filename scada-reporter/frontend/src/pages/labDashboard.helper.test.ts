import { describe, expect, it } from 'vitest'
import { canGenerateLab } from './labDashboard.helper'

describe('canGenerateLab', () => {
  it('false when no point', () => {
    expect(canGenerateLab('', [1])).toBe(false)
  })
  it('false when no parameters', () => {
    expect(canGenerateLab('5', [])).toBe(false)
  })
  it('true when point and at least one parameter', () => {
    expect(canGenerateLab('5', [1, 2])).toBe(true)
  })
})
