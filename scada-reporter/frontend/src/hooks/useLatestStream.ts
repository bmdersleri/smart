import { useEffect, useState } from 'react'
import { getStreamToken } from '../api/client'

export interface LiveValue {
  v: number | null
  q: number
  t: string
}

/**
 * SSE ile son-değer akışı. Backend /api/dashboard/stream cache'ten push eder;
 * 5sn'lik REST polling yerine gerçek-zamanlı güncelleme sağlar. EventSource
 * başlık gönderemediği için kısa ömürlü SSE-scoped token query-param ile iletilir.
 * Token, EventSource açılmadan önce (ve her yeniden bağlanmada) POST /auth/stream-token
 * ile alınır — böylece uzun ömürlü JWT asla URL'de görünmez.
 */
export function useLatestStream(tagIds: number[], enabled = true): Record<number, LiveValue> {
  const [values, setValues] = useState<Record<number, LiveValue>>({})
  const key = tagIds.slice().sort((a, b) => a - b).join(',')

  useEffect(() => {
    if (!enabled || tagIds.length === 0) return

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
      tagIds.forEach((id) => params.append('tag_ids', String(id)))
      es = new EventSource(`/api/dashboard/stream?${params.toString()}`)

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

      es.onerror = () => {
        // Hata durumunda mevcut bağlantıyı kapat ve yeni stream token ile yeniden bağlan
        if (es) {
          es.close()
          es = null
        }
        if (!cancelled) {
          // Kısa gecikme sonrası yeni token alarak yeniden bağlan
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled])

  return values
}
