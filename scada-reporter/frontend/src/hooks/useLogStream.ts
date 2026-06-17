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
 * SSE ile canlı backend log akışı. Backend /api/dashboard/logs/stream halka
 * tampondan yeni kayıtları JSON dizisi olarak push eder. EventSource başlık
 * gönderemediği için token query-param ile iletilir. `level` değiştiğinde
 * akış yeniden açılır ve tampon sıfırlanır.
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
        /* hatalı frame -> atla */
      }
    }
    // Hata durumunda tarayıcı otomatik yeniden bağlanır.

    return () => es.close()
  }, [level, enabled, cap])

  return { lines, clear }
}
