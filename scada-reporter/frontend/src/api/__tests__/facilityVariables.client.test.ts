import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api, listFacilityVariables, createFacilityVariable, updateFacilityVariable, deleteFacilityVariable, validateExpression, previewVariable } from '../client'

describe('facility variable client', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('GET list hits /facility-variables (no trailing slash — avoids cross-origin 307)', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    await listFacilityVariables()
    expect(spy).toHaveBeenCalledWith('/facility-variables')
  })
  it('POST create hits /facility-variables with body (no trailing slash)', async () => {
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    const body = { code: 'v', name: 'V', kind: 'scalar' as const, expression: { op: 'const', value: 1 } }
    await createFacilityVariable(body)
    expect(spy).toHaveBeenCalledWith('/facility-variables', body)
  })
  it('PUT update hits /facility-variables/{id}', async () => {
    const spy = vi.spyOn(api, 'put').mockResolvedValue({ data: {} })
    await updateFacilityVariable(7, { name: 'X', expression: { op: 'const', value: 1 } })
    expect(spy).toHaveBeenCalledWith('/facility-variables/7', { name: 'X', expression: { op: 'const', value: 1 } })
  })
  it('DELETE passes force as query param', async () => {
    const spy = vi.spyOn(api, 'delete').mockResolvedValue({ data: {} })
    await deleteFacilityVariable(7, true)
    expect(spy).toHaveBeenCalledWith('/facility-variables/7?force=true')
  })
  it('validate posts expression+kind', async () => {
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: { valid: true } })
    await validateExpression({ expression: { op: 'const', value: 1 }, kind: 'scalar' })
    expect(spy).toHaveBeenCalledWith('/facility-variables/validate', { expression: { op: 'const', value: 1 }, kind: 'scalar' })
  })
  it('preview posts to /{id}/preview', async () => {
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: { kind: 'scalar', value: 1, unit: '' } })
    await previewVariable(3, { window: { type: 'month', year: 2026, month: 6 } })
    expect(spy).toHaveBeenCalledWith('/facility-variables/3/preview', { window: { type: 'month', year: 2026, month: 6 } })
  })
})
