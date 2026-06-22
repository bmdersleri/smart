import axios from 'axios'

// ── Generated types (from openapi.json → src/api/generated/types.gen.ts) ──────
// Hand-written interfaces that map cleanly onto generated types are replaced
// with re-exports below. Types that diverge in shape (nullability, extra fields,
// or semantic differences) are kept as-is to avoid cascading tsc errors.
export type {
  AnnotationResponse as Annotation,
  GroupResponse as Group,
  ArchiveEntryResponse as ArchiveEntry,
  PaginatedArchiveResponse as PaginatedArchive,
  TemplateResponse as ReportTemplate,
  ScheduledResponse as ScheduledReport,
} from './generated/types.gen'

// Role union — mirrors backend Literal["admin", "operator", "viewer"]
export type UserRole = 'admin' | 'operator' | 'viewer'

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

export const getMe = () => api.get<{ id: number; username: string; role: UserRole; full_name: string; language: string; permissions: string[] }>('/auth/me')

/**
 * SSE bağlantıları için kısa ömürlü stream token al.
 * Normal Authorization başlığı ile çağrılır (axios interceptor otomatik ekler).
 * Dönen token yalnızca SSE URL query param'ında kullanılır — localStorage'a yazılmaz.
 */
export const getStreamToken = () =>
  api.post<{ stream_token: string; expires_in: number }>('/auth/stream-token')

export const updateMe = (language: string) =>
  api.patch<{ id: number; username: string; role: UserRole; full_name: string; language: string; permissions: string[] }>(
    '/auth/me',
    { language },
  )

export interface ManagedUser {
  id: number; username: string; email: string; full_name: string
  role: UserRole; is_active: boolean
  permission_overrides: Record<string, boolean>; permissions: string[]
}
export interface UserCreatePayload {
  username: string; email: string; password: string
  full_name?: string; role?: UserRole; permission_overrides?: Record<string, boolean>
}
export interface UserPatchPayload {
  email?: string; full_name?: string; role?: UserRole
  is_active?: boolean; permission_overrides?: Record<string, boolean>
}
export const listUsers = () => api.get<ManagedUser[]>('/users/')
export const createUser = (data: UserCreatePayload) => api.post<ManagedUser>('/users/', data)
export const patchUser = (id: number, data: UserPatchPayload) => api.patch<ManagedUser>(`/users/${id}`, data)
export const resetUserPassword = (id: number, password: string) => api.post(`/users/${id}/password`, { password })
export const deleteUser = (id: number) => api.delete(`/users/${id}`)

// Tags
export interface Tag {
  id: number; node_id: string; name: string; unit: string; device: string; channel: string
  is_active: boolean; group_id: number | null
  min_alarm: number | null; max_alarm: number | null; deadband: number | null
  plc_name: string; plc_ip: string | null; s7_address: string | null; data_type: string
  sample_interval: number; long_term: boolean; daily_tracking: boolean
  // tag ekleme yanıtında dolu gelir
  current_value?: number | null; quality?: number | null; read_at?: string | null
}
export interface TagCreate {
  node_id?: string; name: string; unit?: string; description?: string; channel?: string; device?: string
  plc_name?: string; plc_ip?: string | null; plc_rack?: number; plc_slot?: number
  s7_address?: string | null; data_type?: string; sample_interval?: number; long_term?: boolean
}
export interface TagUpdate { name?: string; unit?: string; device?: string; channel?: string; description?: string; min_alarm?: number | null; max_alarm?: number | null; deadband?: number | null }
export const getTags = () => api.get<Tag[]>('/tags/')
export const createTag = (data: TagCreate) => api.post<Tag>('/tags/', data)
export const updateTag = (id: number, data: TagUpdate) => api.patch<Tag>(`/tags/${id}`, data)
export const deleteTag = (id: number) => api.delete(`/tags/${id}`)
export const browseOpcTags = () => api.get<{ tags: { node_id: string; name: string; depth: number }[]; count: number }>('/tags/browse')
export const importTags = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<{ imported: number; skipped: number; total: number; errors: string[] }>('/tags/import', fd)
}
export const importTagsCsv = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<{ imported: number; skipped: number; total: number; errors: string[] }>('/tags/import_csv', fd)
}
export const exportTags = (format: 'csv' | 'xlsx') =>
  api.get(`/tags/export?format=${format}`, { responseType: 'blob' })

// Tag grupları (hiyerarşi)
// Group is re-exported from generated (GroupResponse). GroupNode is custom (tree structure).
export interface GroupNode {
  id: number | null; name: string; parent_id?: number | null; sort_order?: number
  tag_ids: number[]; children: GroupNode[]
}
export const getGroups = () => api.get<Group[]>('/groups/')
export const getGroupTree = (mode: 'manual' | 'auto' = 'manual') =>
  api.get<GroupNode[]>(`/groups/tree?mode=${mode}`)
export const createGroup = (data: { name: string; parent_id?: number | null }) =>
  api.post<Group>('/groups/', data)
export const updateGroup = (id: number, data: { name?: string; parent_id?: number | null }) =>
  api.patch<Group>(`/groups/${id}`, data)
export const deleteGroup = (id: number) => api.delete(`/groups/${id}`)
export const assignTagsToGroup = (id: number, tag_ids: number[]) =>
  api.post(`/groups/${id}/assign`, { tag_ids })
export const unassignTags = (tag_ids: number[]) => api.post('/groups/unassign', { tag_ids })

// Trend annotations (paylaşımlı notlar)
// Annotation is re-exported from generated (AnnotationResponse).
export const getAnnotations = (params: { tag_ids?: number[]; start?: string; end?: string }) => {
  const q = new URLSearchParams()
  params.tag_ids?.forEach((id) => q.append('tag_ids', String(id)))
  if (params.start) q.set('start', params.start)
  if (params.end) q.set('end', params.end)
  return api.get<Annotation[]>(`/annotations/?${q.toString()}`)
}
export const createAnnotation = (data: { tag_id?: number | null; ts: string; text: string }) =>
  api.post<Annotation>('/annotations/', data)
export const deleteAnnotation = (id: number) => api.delete(`/annotations/${id}`)

// Dashboard
export interface WatchlistItem {
  tag_id: number; name: string; device: string; unit: string
  value: number | null; timestamp: string | null; quality_ok: boolean
}

export interface DashboardTag {
  tag_id: number; name: string; device: string; unit: string
  value: number | null; timestamp: string | null; quality_ok: boolean
}

export interface DashboardTagsParams {
  device?: string; search?: string; quality?: 'good' | 'bad' | 'stale'
  daily?: boolean; page?: number; page_size?: number
}

export interface DashboardTagsResponse {
  items: DashboardTag[]; total: number; page: number
  page_size: number; total_pages: number
}

export const getOverview = () => api.get<{
  active_tags: number
  last_reading: string | null
  readings_24h: number
  readings_1h: number
  quality_rate: number | null
}>('/dashboard/overview')
export interface HealthStatus {
  status: string
  plc_connected: number
  plc_total: number
  collector_running: boolean
  scheduler_running: boolean
  uptime_seconds: number
  started_at: string
}
// /health is mounted at the app root (no /api prefix), so override baseURL.
export const getHealth = () => api.get<HealthStatus>('/health', { baseURL: '' })
export interface MetricsSummary {
  rows_written_total: number
  bad_quality_total: number
  bad_ratio: number | null
  tick_count: number
  tick_avg_seconds: number | null
  plcs: { plc: string; name: string | null; tag_count: number; count: number; avg_seconds: number | null }[]
}
export const getMetrics = () => api.get<MetricsSummary>('/dashboard/metrics')
export interface DeadbandSavings {
  window_hours: number
  deadband_tags: number
  expected_rows: number
  actual_rows: number
  saved_rows: number
  saved_rows_per_day: number
  savings_pct: number | null
}
export const getDeadbandSavings = (hours = 24) =>
  api.get<DeadbandSavings>('/dashboard/deadband_savings', { params: { hours } })
export const getDashboardDevices = () => api.get<string[]>('/dashboard/devices')
export const getWatchlist = () => api.get<WatchlistItem[]>('/dashboard/watchlist')
export const addWatchlist = (tag_id: number) => api.post(`/dashboard/watchlist/${tag_id}`)
export const removeWatchlist = (tag_id: number) => api.delete(`/dashboard/watchlist/${tag_id}`)
export const getDashboardTags = (p: DashboardTagsParams) =>
  api.get<DashboardTagsResponse>('/dashboard/tags', { params: p })
// PLC Yönetimi
export interface PlcEntry {
  name: string; ip: string; rack: number; slot: number
  tag_count: number; connected: boolean
}
export interface PlcCreate { name: string; ip?: string; rack?: number; slot?: number }
export interface PlcUpdate { ip: string; rack?: number; slot?: number }
export const listPlcs = () => api.get<PlcEntry[]>('/plc/')
export const createPlc = (data: PlcCreate) => api.post<PlcEntry>('/plc/', data)
export const updatePlc = (name: string, data: PlcUpdate) => api.patch<{ updated: boolean }>(`/plc/${encodeURIComponent(name)}`, data)
export const deletePlc = (name: string) => api.delete(`/plc/${encodeURIComponent(name)}`)

// PLC sağlık & incident'lar
export interface PlcHealthRow {
  plc_ip: string; plc_name: string; rack: number; slot: number; connected: boolean
  last_success_at: string | null; consecutive_fail: number; last_error: string | null
  good_last_cycle: number; bad_last_cycle: number; reconnects_last_min: number
  open_incident_count: number; updated_at: string
}
export interface PlcIncidentRow {
  id: number; plc_ip: string; plc_name: string; kind: string
  severity: 'critical' | 'warning'; message: string; detail: Record<string, unknown>
  opened_at: string; resolved_at: string | null
  acknowledged_by: string | null; acknowledged_at: string | null
}
export interface IncidentSummary { open_total: number; critical: number; warning: number }

export const getPlcHealth = () => api.get<PlcHealthRow[]>('/plc/health')
export const getPlcIncidents = (params?: { open?: boolean; plc?: string; limit?: number }) => {
  const q = new URLSearchParams()
  if (params?.open !== undefined) q.set('open', String(params.open))
  if (params?.plc) q.set('plc', params.plc)
  if (params?.limit) q.set('limit', String(params.limit))
  const qs = q.toString()
  return api.get<PlcIncidentRow[]>(`/plc/incidents${qs ? `?${qs}` : ''}`)
}
export const getIncidentSummary = () => api.get<IncidentSummary>('/plc/incidents/summary')
export const ackIncident = (id: number) => api.post(`/plc/incidents/${id}/ack`)

export const getTrend = (tagIds: number[], hours: number, maxPoints = 2000) =>
  api.get<{ tag_id: number; name: string; unit: string; data: { t: string; v: number }[] }[]>(
    `/dashboard/trend?${tagIds.map((id) => `tag_ids=${id}`).join('&')}&hours=${hours}&max_points=${maxPoints}`
  )

// Rollup (continuous aggregate) çözünürlüğünden okur; kısa pencerede ham veriye düşer
export const getTrendAgg = (tagIds: number[], hours: number, maxPoints = 2000) =>
  api.get<{ tag_id: number; name: string; unit: string; data: { t: string; v: number }[] }[]>(
    `/dashboard/trend_agg?${tagIds.map((id) => `tag_ids=${id}`).join('&')}&hours=${hours}&max_points=${maxPoints}`
  )

// Açık başlangıç/bitiş penceresi (dönem karşılaştırması için)
export const getTrendRange = (tagIds: number[], start: string, end: string, maxPoints = 2000) =>
  api.get<{ tag_id: number; name: string; unit: string; data: { t: string; v: number }[] }[]>(
    `/dashboard/trend_range?${tagIds.map((id) => `tag_ids=${id}`).join('&')}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&max_points=${maxPoints}`
  )

// Reports
export const generateReport = (data: { tag_ids: number[]; start: string; end: string; interval: string; format: string }) =>
  api.post('/reports/generate', data, { responseType: 'blob' })

export interface ReportHistoryEntry { id: number; created_at: string; tag_ids: number[]; start: string; end: string; interval: string; format: string }
export const getReportHistory = () => api.get<ReportHistoryEntry[]>('/reports/history')
export const downloadHistoryReport = (id: number) => api.get(`/reports/history/${id}/download`, { responseType: 'blob' })

// Advanced Reports
// ReportTemplate is re-exported from generated (TemplateResponse).
export interface TemplateCreate {
  name: string; description?: string; tag_ids: number[]
  time_range_type?: string; custom_start?: string | null; custom_end?: string | null
  interval?: string; output_format?: string
  include_std_dev?: boolean; include_percentiles?: boolean; percentile_levels?: number[]
  include_trend_line?: boolean; anomaly_enabled?: boolean; anomaly_zscore_threshold?: number
  show_summary_stats?: boolean; show_trend_charts?: boolean; show_anomaly_table?: boolean; show_raw_data?: boolean
}
// ScheduledReport is re-exported from generated (ScheduledResponse).
export interface ScheduledCreate {
  template_id: number; name: string; schedule_type: string
  cron_hour?: number | null; cron_minute?: number | null; cron_day_of_week?: string | null
  cron_day_of_month?: number | null; interval_hours?: number | null
}
// ArchiveEntry is re-exported from generated (ArchiveEntryResponse).
// PaginatedArchive is re-exported from generated (PaginatedArchiveResponse).

export const listTemplates = () => api.get<ReportTemplate[]>('/advanced-reports/templates')
export const createTemplate = (d: TemplateCreate) => api.post<ReportTemplate>('/advanced-reports/templates', d)
export const updateTemplate = (id: number, d: TemplateCreate) => api.put<ReportTemplate>(`/advanced-reports/templates/${id}`, d)
export const deleteTemplate = (id: number) => api.delete(`/advanced-reports/templates/${id}`)
export const runTemplate = (id: number, opts?: { start?: string; end?: string }) =>
  api.post<ArchiveEntry>(`/advanced-reports/templates/${id}/run`, opts ?? {})

export const listScheduled = () => api.get<ScheduledReport[]>('/advanced-reports/scheduled')
export const createScheduled = (d: ScheduledCreate) => api.post<ScheduledReport>('/advanced-reports/scheduled', d)
export const updateScheduled = (id: number, d: ScheduledCreate) => api.put<ScheduledReport>(`/advanced-reports/scheduled/${id}`, d)
export const toggleScheduled = (id: number) => api.patch<ScheduledReport>(`/advanced-reports/scheduled/${id}/toggle`)
export const deleteScheduled = (id: number) => api.delete(`/advanced-reports/scheduled/${id}`)

export const getArchive = (params: { page?: number; page_size?: number; template_id?: number; status?: string; date_from?: string; date_to?: string }) =>
  api.get<PaginatedArchive>('/advanced-reports/archive', { params })
export const getArchiveEntry = (id: number) => api.get<ArchiveEntry>(`/advanced-reports/archive/${id}`)
export const downloadArchiveReport = (id: number) => api.get(`/advanced-reports/archive/${id}/download`, { responseType: 'blob' })
