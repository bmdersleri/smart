import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getStreamToken } from '../api/client'
import type { DashboardTag, DashboardTagsResponse } from '../api/client'

interface LiveReading {
  tag_id: number
  value: number | null
  timestamp: string | null
  quality_ok: boolean
}

interface WsMessage {
  type: string
  data: LiveReading[] | LiveReading
}

export function useLiveDashboard(enabled = true) {
  const qc = useQueryClient()
  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected')
  const retryTimeout = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (!enabled) {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      setStatus('disconnected')
      return
    }

    let isMounted = true

    const connect = async () => {
      try {
        setStatus('connecting')
        // Get a short-lived token for WebSocket auth
        const { data } = await getStreamToken()
        if (!isMounted) return

        // Determine correct WebSocket protocol
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const wsUrl = `${protocol}//${window.location.host}/api/dashboard/stream?token=${data.stream_token}`

        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
          if (isMounted) setStatus('connected')
        }

        ws.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data) as WsMessage
            const updates = Array.isArray(payload.data) ? payload.data : [payload.data]

            // 1. Update paginated All Tags lists
            qc.setQueriesData<DashboardTagsResponse>({ queryKey: ['dashboard-tags'] }, (old) => {
              if (!old) return old
              let changed = false
              const newItems = old.items.map((item) => {
                const update = updates.find((u) => u.tag_id === item.tag_id)
                if (update) {
                  changed = true
                  return { ...item, ...update }
                }
                return item
              })
              return changed ? { ...old, items: newItems } : old
            })

            // 2. Update Watchlist
            qc.setQueriesData<DashboardTag[]>({ queryKey: ['dashboard-watchlist'] }, (old) => {
              if (!old) return old
              let changed = false
              const newItems = old.map((item) => {
                const update = updates.find((u) => u.tag_id === item.tag_id)
                if (update) {
                  changed = true
                  return { ...item, ...update }
                }
                return item
              })
              return changed ? newItems : old
            })

          } catch (err) {
            console.error('Failed to parse LiveDashboard WS message', err)
          }
        }

        ws.onclose = () => {
          if (isMounted) {
            setStatus('disconnected')
            // Auto-reconnect after 3 seconds
            retryTimeout.current = setTimeout(connect, 3000)
          }
        }
      } catch (err) {
        if (isMounted) {
          setStatus('disconnected')
          retryTimeout.current = setTimeout(connect, 3000)
        }
      }
    }

    connect()

    return () => {
      isMounted = false
      if (retryTimeout.current) clearTimeout(retryTimeout.current)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [enabled, qc])

  return { status }
}
