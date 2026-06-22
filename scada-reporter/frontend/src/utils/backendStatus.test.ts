import { describe, it, expect } from 'vitest'
import { backendStatus } from './backendStatus'

describe('backendStatus', () => {
  it('is checking while the first probe is loading', () => {
    expect(backendStatus({ isLoading: true, isError: false })).toBe('checking')
  })

  it('is online when the probe succeeds', () => {
    expect(backendStatus({ isLoading: false, isError: false })).toBe('online')
  })

  it('is offline when the probe errors', () => {
    expect(backendStatus({ isLoading: false, isError: true })).toBe('offline')
  })

  it('error wins over loading', () => {
    expect(backendStatus({ isLoading: true, isError: true })).toBe('offline')
  })
})
