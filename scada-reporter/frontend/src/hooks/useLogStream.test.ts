import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useLogStream } from './useLogStream'

// Mock getStreamToken so tests don't make real HTTP calls.
// The hook now fetches a short-lived token before opening the EventSource;
// tests inject a resolved promise so the EventSource is created in the
// microtask following renderHook() — callers must await a tick first.
vi.mock('../api/client', () => ({
  getStreamToken: vi.fn().mockResolvedValue({ data: { stream_token: 'sse-tok', expires_in: 60 } }),
}))

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

/** Flush pending microtasks (promise resolutions) so the async connect() runs. */
async function flushAsync() {
  await act(async () => {
    await Promise.resolve()
  })
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
  it('appends parsed frames in order', async () => {
    const { result } = renderHook(() => useLogStream('INFO'))
    await flushAsync()
    act(() => FakeEventSource.last!.push([line(1, 'a'), line(2, 'b')]))
    expect(result.current.lines.map((l) => l.msg)).toEqual(['a', 'b'])
  })

  it('caps the buffer at cap, dropping oldest', async () => {
    const { result } = renderHook(() => useLogStream('INFO', true, 2))
    await flushAsync()
    act(() => FakeEventSource.last!.push([line(1, 'a'), line(2, 'b'), line(3, 'c')]))
    expect(result.current.lines.map((l) => l.msg)).toEqual(['b', 'c'])
  })

  it('clear() empties the buffer', async () => {
    const { result } = renderHook(() => useLogStream('INFO'))
    await flushAsync()
    act(() => FakeEventSource.last!.push([line(1, 'a')]))
    act(() => result.current.clear())
    expect(result.current.lines).toEqual([])
  })

  it('skips malformed frames without throwing', async () => {
    const { result } = renderHook(() => useLogStream('INFO'))
    await flushAsync()
    act(() => FakeEventSource.last!.onmessage?.({ data: 'not-json' }))
    expect(result.current.lines).toEqual([])
  })

  it('passes the level into the EventSource URL', async () => {
    renderHook(() => useLogStream('WARNING'))
    await flushAsync()
    expect(FakeEventSource.last!.url).toContain('level=WARNING')
    // The stream token (not the long-lived token) is passed in the URL
    expect(FakeEventSource.last!.url).toContain('token=sse-tok')
  })

  it('does not open a stream when disabled', async () => {
    FakeEventSource.last = null
    renderHook(() => useLogStream('INFO', false))
    await flushAsync()
    expect(FakeEventSource.last).toBeNull()
  })
})
