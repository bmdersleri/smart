import { useCallback, useEffect, useState } from 'react'

export interface LogLine {
  seq: number
  ts: string
  level: string
  levelno: number
  name: string
  msg: string
}

/**
 * Live backend log stream over SSE. The backend /api/dashboard/logs/stream
 * pushes new records from a ring buffer as a JSON array. EventSource cannot
 * send headers, so the token is passed as a query param. When `level` changes
 * the stream is reopened and the buffer is reset.
 */
export function useLogStream(
  level: string,
  enabled = true,
  cap = 500,
): { lines: LogLine[]; clear: () => void } {
  const [lines, setLines] = useState<LogLine[]>([])
  const clear = useCallback(() => setLines([]), [])

  useEffect(() => {
    if (!enabled) return
    const token = localStorage.getItem('token')
    if (!token) return

    // Reset the buffer when (re)subscribing to a new stream. This effect is a
    // genuine external-system subscription, so the reset belongs with it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLines([])
    const params = new URLSearchParams()
    params.set('token', token)
    params.set('level', level)
    const es = new EventSource(`/api/dashboard/logs/stream?${params.toString()}`)

    es.onmessage = (e) => {
      try {
        const rows = JSON.parse(e.data) as LogLine[]
        if (!Array.isArray(rows)) return
        setLines((prev) => {
          const next = [...prev, ...rows]
          return next.length > cap ? next.slice(next.length - cap) : next
        })
      } catch {
        /* malformed frame -> skip */
      }
    }
    // On error the browser reconnects automatically.

    return () => es.close()
  }, [level, enabled, cap])

  return { lines, clear }
}
