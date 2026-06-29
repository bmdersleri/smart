import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getStreamToken } from '../api/client'
import type { DashboardTag, DashboardTagsResponse } from '../api/client'

/** Backend SSE frame: { "<tagId>": { v, q, t } } (bkz. realtime._format_frame). */
interface LiveValue {
  v: number | null
  q: number
  t: string
}

export type LiveStatus = 'connecting' | 'connected' | 'disconnected'

/**
 * Dashboard geneli canlı son-değer akışı (SSE).
 *
 * Backend `/api/dashboard/stream` bir Server-Sent Events endpoint'idir
 * (StreamingResponse, text/event-stream) — WebSocket DEĞİL. Bu yüzden burada
 * `EventSource` kullanılır; gelen frame'ler `dashboard-tags` ve
 * `dashboard-watchlist` TanStack Query cache'lerine yazılır ve bağlantı
 * durumu badge için döndürülür. Token, EventSource başlık gönderemediği için
 * her bağlanışta kısa ömürlü stream-token query-param ile iletilir.
 */
export function useLiveDashboard(enabled = true): { status: LiveStatus } {
  const qc = useQueryClient()
  const [status, setStatus] = useState<LiveStatus>('disconnected')

  useEffect(() => {
    if (!enabled) {
      setStatus('disconnected')
      return
    }

    let cancelled = false
    let es: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | null = null

    const applyUpdates = (data: Record<string, LiveValue>) => {
      const entries = Object.entries(data)
      if (entries.length === 0) return

      // 1. Sayfalı "All Tags" listeleri
      qc.setQueriesData<DashboardTagsResponse>({ queryKey: ['dashboard-tags'] }, (old) => {
        if (!old) return old
        let changed = false
        const items = old.items.map((item) => {
          const lv = data[String(item.tag_id)]
          if (!lv) return item
          changed = true
          return { ...item, value: lv.v, timestamp: lv.t, quality_ok: lv.q === 192 }
        })
        return changed ? { ...old, items } : old
      })

      // 2. Watchlist
      qc.setQueriesData<DashboardTag[]>({ queryKey: ['dashboard-watchlist'] }, (old) => {
        if (!old) return old
        let changed = false
        const next = old.map((item) => {
          const lv = data[String(item.tag_id)]
          if (!lv) return item
          changed = true
          return { ...item, value: lv.v, timestamp: lv.t, quality_ok: lv.q === 192 }
        })
        return changed ? next : old
      })
    }

    const connect = async () => {
      setStatus('connecting')
      let streamToken: string
      try {
        const { data } = await getStreamToken()
        streamToken = data.stream_token
      } catch {
        // Token alınamadı (backend down/401). 401 ise axios interceptor login'e
        // yönlendirir (unmount → cancelled); aksi halde kısa gecikmeyle yeniden dene.
        if (!cancelled) {
          setStatus('disconnected')
          retry = setTimeout(() => {
            if (!cancelled) connect()
          }, 3000)
        }
        return
      }

      if (cancelled) return

      es = new EventSource(`/api/dashboard/stream?token=${encodeURIComponent(streamToken)}`)

      es.onopen = () => {
        if (!cancelled) setStatus('connected')
      }

      es.onmessage = (e) => {
        if (!cancelled) setStatus('connected')
        try {
          applyUpdates(JSON.parse(e.data) as Record<string, LiveValue>)
        } catch {
          /* hatalı frame -> atla */
        }
      }

      es.onerror = () => {
        if (es) {
          es.close()
          es = null
        }
        if (!cancelled) {
          setStatus('disconnected')
          retry = setTimeout(() => {
            if (!cancelled) connect()
          }, 3000)
        }
      }
    }

    connect()

    return () => {
      cancelled = true
      if (retry) clearTimeout(retry)
      if (es) {
        es.close()
        es = null
      }
    }
  }, [enabled, qc])

  return { status }
}
