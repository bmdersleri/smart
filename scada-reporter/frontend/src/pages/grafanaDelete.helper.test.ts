import { describe, expect, it } from 'vitest'
import { canDeleteDashboard } from './grafanaDelete.helper'

describe('canDeleteDashboard', () => {
  it('true for admin', () => {
    expect(canDeleteDashboard('admin')).toBe(true)
  })
  it('false for operator', () => {
    expect(canDeleteDashboard('operator')).toBe(false)
  })
  it('false for undefined', () => {
    expect(canDeleteDashboard(undefined)).toBe(false)
  })
})
