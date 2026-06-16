import { useEffect, useState } from 'react'

export interface LiveValue {
  v: number | null
  q: number
  t: string
}

/**
 * SSE ile son-değer akışı. Backend /api/dashboard/stream cache'ten push eder;
 * 5sn'lik REST polling yerine gerçek-zamanlı güncelleme sağlar. EventSource
 * başlık gönderemediği için token query-param ile iletilir.
 */
export function useLatestStream(tagIds: number[], enabled = true): Record<number, LiveValue> {
  const [values, setValues] = useState<Record<number, LiveValue>>({})
  const key = tagIds.slice().sort((a, b) => a - b).join(',')

  useEffect(() => {
    if (!enabled || tagIds.length === 0) return
    const token = localStorage.getItem('token')
    if (!token) return

    const params = new URLSearchParams()
    params.set('token', token)
    tagIds.forEach((id) => params.append('tag_ids', String(id)))
    const es = new EventSource(`/api/dashboard/stream?${params.toString()}`)

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as Record<string, LiveValue>
        setValues((prev) => {
          const next = { ...prev }
          for (const [k, val] of Object.entries(data)) next[Number(k)] = val
          return next
        })
      } catch {
        /* hatalı frame -> atla */
      }
    }
    // Hata durumunda tarayıcı otomatik yeniden bağlanır.

    return () => es.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled])

  return values
}
