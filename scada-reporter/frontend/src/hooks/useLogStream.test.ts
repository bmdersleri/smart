import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useLogStream } from './useLogStream'

class FakeEventSource {
  static last: FakeEventSource | null = null
  url: string
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: ((e: unknown) => void) | null = null
  closed = false
  constructor(url: string) {
    this.url = url
    FakeEventSource.last = this
  }
  close() {
    this.closed = true
  }
  push(rows: unknown) {
    this.onmessage?.({ data: JSON.stringify(rows) })
  }
}

beforeEach(() => {
  vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource)
  localStorage.setItem('token', 'tok')
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  FakeEventSource.last = null
})

const line = (seq: number, msg: string) => ({
  seq,
  ts: '2026-06-17T00:00:00Z',
  level: 'INFO',
  levelno: 20,
  name: 'app',
  msg,
})

describe('useLogStream', () => {
  it('appends parsed frames in order', () => {
    const { result } = renderHook(() => useLogStream('INFO'))
    act(() => FakeEventSource.last!.push([line(1, 'a'), line(2, 'b')]))
    expect(result.current.lines.map((l) => l.msg)).toEqual(['a', 'b'])
  })

  it('caps the buffer at cap, dropping oldest', () => {
    const { result } = renderHook(() => useLogStream('INFO', true, 2))
    act(() => FakeEventSource.last!.push([line(1, 'a'), line(2, 'b'), line(3, 'c')]))
    expect(result.current.lines.map((l) => l.msg)).toEqual(['b', 'c'])
  })

  it('clear() empties the buffer', () => {
    const { result } = renderHook(() => useLogStream('INFO'))
    act(() => FakeEventSource.last!.push([line(1, 'a')]))
    act(() => result.current.clear())
    expect(result.current.lines).toEqual([])
  })

  it('skips malformed frames without throwing', () => {
    const { result } = renderHook(() => useLogStream('INFO'))
    act(() => FakeEventSource.last!.onmessage?.({ data: 'not-json' }))
    expect(result.current.lines).toEqual([])
  })

  it('passes the level into the EventSource URL', () => {
    renderHook(() => useLogStream('WARNING'))
    expect(FakeEventSource.last!.url).toContain('level=WARNING')
    expect(FakeEventSource.last!.url).toContain('token=tok')
  })

  it('does not open a stream when disabled', () => {
    FakeEventSource.last = null
    renderHook(() => useLogStream('INFO', false))
    expect(FakeEventSource.last).toBeNull()
  })
})
