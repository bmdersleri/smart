import { useQuery } from '@tanstack/react-query'
import { getAppSettings } from '../api/client'

// The facility-global timezone (default Europe/Istanbul while loading / on error).
export function useTimezone(): string {
  const { data } = useQuery({
    queryKey: ['app-settings'],
    queryFn: () => getAppSettings(),
    staleTime: 5 * 60 * 1000,
  })
  return data?.data?.timezone ?? 'Europe/Istanbul'
}
