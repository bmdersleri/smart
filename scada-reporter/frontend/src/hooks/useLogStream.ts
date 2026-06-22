import { useCallback, useEffect, useState } from 'react'
import { getStreamToken } from '../api/client'

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
 * send headers, so a short-lived SSE-scoped token is fetched via POST
 * /auth/stream-token and passed as a query param — the long-lived JWT is
 * never put in the URL. On reconnect a fresh stream token is fetched.
 * When `level` changes the stream is reopened and the buffer is reset.
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

    // Reset the buffer when (re)subscribing to a new stream. This effect is a
    // genuine external-system subscription, so the reset belongs with it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLines([])

    let cancelled = false
    let es: EventSource | null = null

    async function connect() {
      // Stream token al; başarısız olursa bağlantı kurma
      let streamToken: string
      try {
        const resp = await getStreamToken()
        streamToken = resp.data.stream_token
      } catch {
        // Stream token alınamadı (backend down/bayat ya da 401). 401 ise axios
        // interceptor login'e yönlendirir (unmount → cancelled döngüyü durdurur);
        // aksi halde kısa gecikmeyle yeniden dene ki backend dönünce otomatik bağlansın.
        if (!cancelled) {
          setTimeout(() => {
            if (!cancelled) connect()
          }, 2000)
        }
        return
      }

      if (cancelled) return

      const params = new URLSearchParams()
      params.set('token', streamToken)
      params.set('level', level)
      es = new EventSource(`/api/dashboard/logs/stream?${params.toString()}`)

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

      es.onerror = () => {
        // Hata durumunda mevcut bağlantıyı kapat ve yeni stream token ile yeniden bağlan
        if (es) {
          es.close()
          es = null
        }
        if (!cancelled) {
          setTimeout(() => {
            if (!cancelled) connect()
          }, 2000)
        }
      }
    }

    connect()

    return () => {
      cancelled = true
      if (es) {
        es.close()
        es = null
      }
    }
  }, [level, enabled, cap])

  return { lines, clear }
}
