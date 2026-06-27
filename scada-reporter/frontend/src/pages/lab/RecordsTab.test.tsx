import { describe, expect, it } from 'vitest'
import { canEditRecord } from './RecordsTab'

describe('canEditRecord', () => {
  it('admin can edit any record', () => {
    expect(canEditRecord({ role: 'admin', id: 1 }, 999)).toBe(true)
  })
  it('operator can edit own record', () => {
    expect(canEditRecord({ role: 'operator', id: 7 }, 7)).toBe(true)
  })
  it('operator cannot edit others record', () => {
    expect(canEditRecord({ role: 'operator', id: 7 }, 8)).toBe(false)
  })
})
