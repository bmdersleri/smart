import { describe, expect, it } from 'vitest'
import { formatBytes } from './metricsDb.helper'

describe('formatBytes', () => {
  it('0 bytes', () => expect(formatBytes(0)).toBe('0 B'))
  it('bytes', () => expect(formatBytes(512)).toBe('512 B'))
  it('KB', () => expect(formatBytes(2048)).toBe('2.0 KB'))
  it('MB', () => expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB'))
  it('GB', () => expect(formatBytes(6.4 * 1024 * 1024 * 1024)).toBe('6.4 GB'))
})
