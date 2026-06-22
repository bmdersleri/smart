export type BackendStatus = 'checking' | 'online' | 'offline'

/**
 * Map a health-probe query state to a coarse backend status.
 * Error wins over loading so a failed probe reads as offline immediately.
 */
export function backendStatus(q: { isLoading: boolean; isError: boolean }): BackendStatus {
  if (q.isError) return 'offline'
  if (q.isLoading) return 'checking'
  return 'online'
}
