import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// Auth
export const login = (username: string, password: string) =>
  api.post<{ access_token: string }>('/auth/token', new URLSearchParams({ username, password }))

export const getMe = () => api.get<{ id: number; username: string; role: string; full_name: string }>('/auth/me')

// Tags
export interface Tag { id: number; node_id: string; name: string; unit: string; device: string; channel: string; is_active: boolean; min_alarm: number | null; max_alarm: number | null }
export interface TagUpdate { name?: string; unit?: string; device?: string; channel?: string; description?: string; min_alarm?: number | null; max_alarm?: number | null }
export const getTags = () => api.get<Tag[]>('/tags/')
export const createTag = (data: Omit<Tag, 'id' | 'is_active'>) => api.post<Tag>('/tags/', data)
export const updateTag = (id: number, data: TagUpdate) => api.patch<Tag>(`/tags/${id}`, data)
export const deleteTag = (id: number) => api.delete(`/tags/${id}`)
export const browseOpcTags = () => api.get<{ tags: { node_id: string; name: string; depth: number }[]; count: number }>('/tags/browse')

// Dashboard
export interface CurrentValue { tag_id: number; name: string; unit: string; device: string; value: number | null; timestamp: string; quality_ok: boolean; alarm_state: 'overflow' | 'min' | 'max' | null }
export const getCurrentValues = () => api.get<CurrentValue[]>('/dashboard/current-values')
export const getOverview = () => api.get<{ active_tags: number; last_reading: string | null; readings_24h: number }>('/dashboard/overview')
export const getTrend = (tagIds: number[], hours: number) =>
  api.get<{ tag_id: number; name: string; unit: string; data: { t: string; v: number }[] }[]>(
    `/dashboard/trend?${tagIds.map((id) => `tag_ids=${id}`).join('&')}&hours=${hours}`
  )

// Reports
export const generateReport = (data: { tag_ids: number[]; start: string; end: string; interval: string; format: string }) =>
  api.post('/reports/generate', data, { responseType: 'blob' })

export interface ReportHistoryEntry { id: number; created_at: string; tag_ids: number[]; start: string; end: string; interval: string; format: string }
export const getReportHistory = () => api.get<ReportHistoryEntry[]>('/reports/history')
export const downloadHistoryReport = (id: number) => api.get(`/reports/history/${id}/download`, { responseType: 'blob' })
