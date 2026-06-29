import axios from 'axios'

// ── Generated types (from openapi.json → src/api/generated/types.gen.ts) ──────
// Hand-written interfaces that map cleanly onto generated types are replaced
// with re-exports below. Types that diverge in shape (nullability, extra fields,
// or semantic differences) are kept as-is to avoid cascading tsc errors.
// Import for local use within this module AND re-export for consumers.
// (`export type {...} from` alone only re-exports — it does not bring the
// names into this module's scope, so internal uses fail with "Cannot find name".)
import type {
  AnnotationResponse as Annotation,
  GroupResponse as Group,
  ArchiveEntryResponse as ArchiveEntry,
  PaginatedArchiveResponse as PaginatedArchive,
  TemplateResponse as ReportTemplate,
  ScheduledResponse as ScheduledReport,
} from './generated/types.gen'

export type {
  Annotation,
  Group,
  ArchiveEntry,
  PaginatedArchive,
  ReportTemplate,
  ScheduledReport,
}

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
  description: string
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
  description: string
}

export interface DashboardTag {
  tag_id: number; name: string; device: string; unit: string
  value: number | null; timestamp: string | null; quality_ok: boolean
  description: string
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
// /live — cheap liveness probe (no auth, no DB); used by the login backend badge.
export const getLive = () => api.get<{ status: string }>('/live', { baseURL: '' })

export interface RuntimeStatus {
  controls_enabled: boolean
  backend: {
    status: string
    uptime_seconds: number
    started_at: string
  }
  collector: {
    configured: boolean
    running: boolean
    poller_running: boolean
    opcua_running: boolean
    monitor_running: boolean
  }
  scheduler: {
    configured: boolean
    running: boolean
  }
}

export const getRuntimeStatus = () => api.get<RuntimeStatus>('/runtime/status')
export const startCollector = () => api.post<RuntimeStatus>('/runtime/collector/start')
export const stopCollector = () => api.post<RuntimeStatus>('/runtime/collector/stop')
export const startScheduler = () => api.post<RuntimeStatus>('/runtime/scheduler/start')
export const stopScheduler = () => api.post<RuntimeStatus>('/runtime/scheduler/stop')

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

export interface DatabaseStats {
  size_bytes: number
  total_readings: number
  total_is_estimate: boolean
  earliest: string | null
  last_day: number
  last_week: number
  last_month: number
  tag_count: number
  tables: { name: string; rows: number }[]
  daily_rows: number
  est_monthly_growth_bytes: number
}
export const getDatabaseStats = () => api.get<DatabaseStats>('/dashboard/database')
export const getDashboardDevices = () => api.get<string[]>('/dashboard/devices')
export const getWatchlist = () => api.get<WatchlistItem[]>('/dashboard/watchlist')
export const addWatchlist = (tag_id: number) => api.post(`/dashboard/watchlist/${tag_id}`)
export const removeWatchlist = (tag_id: number) => api.delete(`/dashboard/watchlist/${tag_id}`)
export interface WatchlistGroupTag { tag_id: number; name: string }
export interface WatchlistGroup {
  id: number; name: string; sort_order: number; tag_count: number; tags: WatchlistGroupTag[]
}
export interface WatchlistGroupsResponse { groups: WatchlistGroup[]; ungrouped: WatchlistGroupTag[] }

const WG = '/dashboard/watchlist-groups'
export const listWatchlistGroups = () => api.get<WatchlistGroupsResponse>(`${WG}/`)
export const createWatchlistGroup = (name: string) => api.post<WatchlistGroup>(`${WG}/`, { name })
export const renameWatchlistGroup = (id: number, name: string) =>
  api.patch<{ id: number; name: string }>(`${WG}/${id}`, { name })
export const deleteWatchlistGroup = (id: number) => api.delete(`${WG}/${id}`)
export const addTagToGroup = (id: number, tagId: number) => api.post(`${WG}/${id}/tags/${tagId}`)
export const removeTagFromGroup = (id: number, tagId: number) => api.delete(`${WG}/${id}/tags/${tagId}`)
export const syncGrafana = () =>
  api.post<{ written: number; deleted: number; errors: string[] }>(`${WG}/sync-grafana`)
export const getDashboardTags = (p: DashboardTagsParams) =>
  api.get<DashboardTagsResponse>('/dashboard/tags', { params: p })

export interface GrafanaTemplate {
  key: 'facility_overview' | 'water_quality'
  name: string
  description: string
  requires_tags: boolean
}
export interface GrafanaDashboardGeneratePayload {
  template: GrafanaTemplate['key']
  title: string
  tag_ids: number[]
}
export interface GrafanaDashboardGenerated {
  uid: string
  title: string
  url: string
  template: GrafanaTemplate['key']
  status: string
}
export const listGrafanaTemplates = () =>
  api.get<{ templates: GrafanaTemplate[] }>('/grafana/templates')
export const generateGrafanaDashboard = (data: GrafanaDashboardGeneratePayload) =>
  api.post<GrafanaDashboardGenerated>('/grafana/dashboards/generate', data)

export interface GrafanaPanelRef { dashboard_uid: string; panel_id: number; title: string }
export interface GrafanaDashboardOpt { uid: string; title: string }
export interface GrafanaPanelOpt { id: number; title: string }
export const listGrafanaDashboards = () =>
  api.get<GrafanaDashboardOpt[]>('/grafana/dashboards')
export const listGrafanaPanels = (uid: string) =>
  api.get<GrafanaPanelOpt[]>(`/grafana/dashboards/${encodeURIComponent(uid)}/panels`)
export const generateDashboardFromTemplate = (templateId: number) =>
  api.post<{ uid: string; title: string; url: string; template_id: number; status: string }>(
    `/grafana/dashboards/from-report-template/${templateId}`)
export const generateLabDashboard = (data: { sample_point_id: number; parameter_ids: number[] }) =>
  api.post<{ uid: string; title: string; url: string; status: string }>(
    '/grafana/dashboards/from-lab',
    data,
  )
export const deleteGrafanaDashboard = (uid: string) =>
  api.delete<{ uid: string; status: string }>(`/grafana/dashboards/${encodeURIComponent(uid)}`)
export interface RefreshManagedResult { updated: number; skipped: { uid: string; reason: string }[] }
export const refreshManagedDashboards = () =>
  api.post<RefreshManagedResult>('/grafana/dashboards/refresh-managed')
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
  grafana_panels?: GrafanaPanelRef[]
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

// ── Lab Data Entry ────────────────────────────────────────────────────────────
export type {
  LabParameterOut, LabParameterCreate, LabParameterUpdate,
  LabSamplePointOut, LabSamplePointCreate, LabSamplePointUpdate,
  SampleCreate, SampleOut, MeasurementIn,
  BatchCreate, ImportCommit,
} from './generated/types.gen'

export const listLabParameters = (params?: { approved?: boolean; active?: boolean }) =>
  api.get<import('./generated/types.gen').LabParameterOut[]>('/lab/parameters', { params })

export const listLabSamplePoints = (params?: { approved?: boolean; active?: boolean }) =>
  api.get<import('./generated/types.gen').LabSamplePointOut[]>('/lab/sample-points', { params })

export const createSample = (data: import('./generated/types.gen').SampleCreate) =>
  api.post<import('./generated/types.gen').SampleOut>('/lab/samples', data)

export const createSamplesBatch = (data: import('./generated/types.gen').BatchCreate) =>
  api.post<import('./generated/types.gen').SampleOut[]>('/lab/samples/batch', data)

export const listSamples = (params?: {
  point_id?: number; parameter_id?: number
  start?: string; end?: string
  entered_by?: number; limit?: number; offset?: number
}) => api.get<import('./generated/types.gen').SampleOut[]>('/lab/samples', { params })

export const getSample = (id: number) =>
  api.get<import('./generated/types.gen').SampleOut>(`/lab/samples/${id}`)

export const updateSample = (id: number, data: Partial<import('./generated/types.gen').SampleCreate>) =>
  api.patch<import('./generated/types.gen').SampleOut>(`/lab/samples/${id}`, data)

export const deleteSample = (id: number) =>
  api.delete(`/lab/samples/${id}`)

export const importPreview = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<{ headers: string[]; rows: string[][] }>(
    '/lab/import/preview', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const importCommit = (data: import('./generated/types.gen').ImportCommit) =>
  api.post<{ inserted: number; errors: string[] }>('/lab/import/commit', data)

export const createParameter = (data: import('./generated/types.gen').LabParameterCreate) =>
  api.post<import('./generated/types.gen').LabParameterOut>('/lab/parameters', data)

export const updateParameter = (id: number, data: import('./generated/types.gen').LabParameterUpdate) =>
  api.patch<import('./generated/types.gen').LabParameterOut>(`/lab/parameters/${id}`, data)

export const deleteParameter = (id: number) =>
  api.delete(`/lab/parameters/${id}`)

export const createSamplePoint = (data: import('./generated/types.gen').LabSamplePointCreate) =>
  api.post<import('./generated/types.gen').LabSamplePointOut>('/lab/sample-points', data)

export const updateSamplePoint = (id: number, data: import('./generated/types.gen').LabSamplePointUpdate) =>
  api.patch<import('./generated/types.gen').LabSamplePointOut>(`/lab/sample-points/${id}`, data)

export const deleteSamplePoint = (id: number) =>
  api.delete(`/lab/sample-points/${id}`)

// ── App Settings ─────────────────────────────────────────────────────────────
export const getAppSettings = () => api.get<{ timezone: string }>('/settings')
export const updateTimezone = (timezone: string) =>
  api.put<{ timezone: string }>('/settings/timezone', { timezone })

// ── License ───────────────────────────────────────────────────────────────────
export type LicenseMode = 'unlicensed' | 'licensed' | 'demo'
export interface LicenseStatus {
  mode: LicenseMode
  licensed: boolean
  customer: string | null
  license_id: string | null
  product: string | null
  features: string[]
  max_tags: number | null
  expires_at: number | null
  demo_max_tags: number | null
}
export const getLicenseStatus = () => api.get<LicenseStatus>('/license')
export const uploadLicense = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<LicenseStatus & { persisted: boolean }>('/license', fd)
}
export const revertLicense = () => api.delete<LicenseStatus>('/license')

// ── DB Backup ─────────────────────────────────────────────────────────────────
export interface BackupItem {
  id: number
  filename: string
  dialect: string
  kind: string
  status: string
  trigger: string
  size_bytes: number | null
  sha256: string | null
  error: string | null
  created_at: string
  completed_at: string | null
}

export interface BackupProgress {
  phase: string
  percent: number
  status: string // running | done | failed | unknown
  error?: string | null
}

export const listBackups = () => api.get<BackupItem[]>('/backup')
// POST returns 202 with a 'running' record; the snapshot runs in the background.
export const createBackup = () => api.post<BackupItem>('/backup')
export const deleteBackup = (id: number) => api.delete<{ deleted: number }>(`/backup/${id}`)
// Restore also runs in the background (202); watch the restore-progress SSE.
export const restoreBackup = (id: number) =>
  api.post<{ restoring: number; progress_key: string; note: string }>(`/backup/${id}/restore`, {
    confirm: 'RESTORE',
  })
export const backupDownloadUrl = (id: number) => `${api.defaults.baseURL}/backup/${id}/download`
export const downloadBackup = (id: number) =>
  api.get<Blob>(`/backup/${id}/download`, { responseType: 'blob' })

// SSE progress streams. EventSource can't send headers, so a short-lived
// stream-scoped token (getStreamToken) is passed as a query param.
export const backupProgressUrl = (id: number, token: string) =>
  `${api.defaults.baseURL}/backup/${id}/progress?token=${encodeURIComponent(token)}`
export const restoreProgressUrl = (id: number, token: string) =>
  `${api.defaults.baseURL}/backup/${id}/restore-progress?token=${encodeURIComponent(token)}`

// ── Compliance Center ─────────────────────────────────────────────────────────
// Mirrors backend app/api/compliance.py shapes exactly. Enum unions match the
// constants in app/models/compliance.py.
export type ComplianceSourceType = 'scada' | 'lab' | 'hybrid'
export type ComplianceLimitType = 'value_limit' | 'sample_count' | 'sample_frequency' | 'quality'
export type ComplianceAggregation = 'instant' | 'daily_avg' | 'monthly_avg' | 'count'
export type ComplianceReportFrequency = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'custom_cron'
export type ComplianceEventType =
  | 'limit_exceeded'
  | 'missing_sample'
  | 'late_sample'
  | 'bad_quality'
  | 'needs_explanation'
export type ComplianceEventStatus = 'open' | 'acknowledged' | 'resolved' | 'waived'

export interface ComplianceOverview {
  active_permits: number
  open_events: number
  by_event_type: Record<string, number>
  missing_samples: number
  unresolved_explanations: number
  packs_waiting: number
}

export interface CompliancePermit {
  id: number
  name: string
  facility_name: string
  authority: string
  permit_number: string
  valid_from: string | null
  valid_to: string | null
  report_frequency: string
  report_cron: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CompliancePermitPayload {
  name: string
  facility_name?: string
  authority?: string
  permit_number?: string
  valid_from?: string | null
  valid_to?: string | null
  report_frequency?: string
  report_cron?: string | null
  is_active?: boolean
}

export interface CompliancePoint {
  id: number
  permit_id: number
  code: string
  name: string
  description: string
  lab_sample_point_id: number | null
  created_at: string
  updated_at: string
}

export interface CompliancePointPayload {
  code: string
  name: string
  description?: string
  lab_sample_point_id?: number | null
}

export interface ComplianceLimit {
  id: number
  parameter_id: number
  limit_type: string
  min_value: number | null
  max_value: number | null
  aggregation: string
  window: string | null
  sample_frequency: string | null
  severity: string
  requires_explanation: boolean
  created_at: string
  updated_at: string
}

export interface ComplianceLimitPayload {
  limit_type: string
  min_value?: number | null
  max_value?: number | null
  aggregation: string
  window?: string | null
  sample_frequency?: string | null
  severity?: string
  requires_explanation?: boolean
}

export interface ComplianceParameter {
  id: number
  permit_id: number
  discharge_point_id: number
  parameter_name: string
  unit: string
  source_type: string
  tag_id: number | null
  lab_parameter_id: number | null
  created_at: string
  updated_at: string
}

export interface ComplianceParameterWithLimits extends ComplianceParameter {
  limits: ComplianceLimit[]
}

export interface ComplianceParameterPayload {
  discharge_point_id: number
  parameter_name: string
  unit?: string
  source_type: string
  tag_id?: number | null
  lab_parameter_id?: number | null
}

export interface CompliancePermitDetail extends CompliancePermit {
  discharge_points: CompliancePoint[]
  parameters: ComplianceParameterWithLimits[]
}

export interface ComplianceEvent {
  id: number
  permit_id: number
  parameter_id: number
  limit_id: number
  event_type: string
  severity: string
  period_start: string
  period_end: string
  observed_value: number | null
  limit_value: number | null
  status: string
  event_key: string
  evidence: Record<string, unknown> | null
  created_at: string
  updated_at: string
  acknowledged_at: string | null
  acknowledged_by: number | null
  resolved_at: string | null
  resolved_by: number | null
  waived_at: string | null
  waived_by: number | null
  waive_reason: string | null
  note_count: number
}

export interface ComplianceEventList {
  total: number
  items: ComplianceEvent[]
}

export interface ComplianceNote {
  id: number
  event_id: number
  user_id: number
  note: string
  created_at: string
}

export interface ComplianceEventFilters {
  permit_id?: number
  status?: string
  start?: string
  end?: string
  limit?: number
  offset?: number
}

export interface ComplianceEvaluateResult {
  created?: number
  updated?: number
  [k: string]: unknown
}

// Overview
export const getComplianceOverview = () => api.get<ComplianceOverview>('/compliance/overview')

// Permits
export const listPermits = (isActive?: boolean) =>
  api.get<CompliancePermit[]>('/compliance/permits', {
    params: isActive === undefined ? undefined : { is_active: isActive },
  })
export const getPermit = (id: number) =>
  api.get<CompliancePermitDetail>(`/compliance/permits/${id}`)
export const createPermit = (data: CompliancePermitPayload) =>
  api.post<CompliancePermit>('/compliance/permits', data)
export const updatePermit = (id: number, data: CompliancePermitPayload) =>
  api.put<CompliancePermit>(`/compliance/permits/${id}`, data)
export const deletePermit = (id: number) =>
  api.delete<{ id: number; is_active: boolean }>(`/compliance/permits/${id}`)

// Discharge / sample points
export const listPoints = (permitId: number) =>
  api.get<CompliancePoint[]>(`/compliance/permits/${permitId}/points`)
export const createPoint = (permitId: number, data: CompliancePointPayload) =>
  api.post<CompliancePoint>(`/compliance/permits/${permitId}/points`, data)
export const updatePoint = (pointId: number, data: CompliancePointPayload) =>
  api.put<CompliancePoint>(`/compliance/points/${pointId}`, data)
export const deletePoint = (pointId: number) =>
  api.delete<{ id: number; deleted: boolean }>(`/compliance/points/${pointId}`)

// Parameters
export const listParameters = (permitId: number) =>
  api.get<ComplianceParameter[]>(`/compliance/permits/${permitId}/parameters`)
export const createParameterCompliance = (permitId: number, data: ComplianceParameterPayload) =>
  api.post<ComplianceParameter>(`/compliance/permits/${permitId}/parameters`, data)
export const updateParameterCompliance = (paramId: number, data: ComplianceParameterPayload) =>
  api.put<ComplianceParameter>(`/compliance/parameters/${paramId}`, data)
export const deleteParameterCompliance = (paramId: number) =>
  api.delete<{ id: number; deleted: boolean }>(`/compliance/parameters/${paramId}`)

// Limits
export const listLimits = (paramId: number) =>
  api.get<ComplianceLimit[]>(`/compliance/parameters/${paramId}/limits`)
export const createLimit = (paramId: number, data: ComplianceLimitPayload) =>
  api.post<ComplianceLimit>(`/compliance/parameters/${paramId}/limits`, data)
export const updateLimit = (limitId: number, data: ComplianceLimitPayload) =>
  api.put<ComplianceLimit>(`/compliance/limits/${limitId}`, data)
export const deleteLimit = (limitId: number) =>
  api.delete<{ id: number; deleted: boolean }>(`/compliance/limits/${limitId}`)

// Events
export const listEvents = (filters: ComplianceEventFilters = {}) =>
  api.get<ComplianceEventList>('/compliance/events', { params: filters })
export const getEvent = (id: number) => api.get<ComplianceEvent>(`/compliance/events/${id}`)
export const addEventNote = (id: number, note: string) =>
  api.post<ComplianceNote>(`/compliance/events/${id}/notes`, { note })
export const setEventStatus = (
  id: number,
  data: { status: string; waive_reason?: string },
) => api.patch<ComplianceEvent>(`/compliance/events/${id}/status`, data)

// Evaluation
export const runEvaluation = (data: { permit_id: number; start: string; end: string }) =>
  api.post<ComplianceEvaluateResult>('/compliance/evaluate', data)

// ── Compliance Report Packs ─────────────────────────────────────────────────
// Mirrors backend app/api/compliance.py report-pack endpoints.
export type ComplianceReportPackStatus =
  | 'draft'
  | 'ready_for_review'
  | 'failed'
  | 'approved'
  | 'exported'
export type ComplianceReportPackFormat = 'pdf' | 'excel' | 'json'

export interface ComplianceReportPack {
  id: number
  permit_id: number
  period_start: string
  period_end: string
  status: string
  error_message: string | null
  prepared_by: number | null
  approved_by: number | null
  approved_at: string | null
  created_at: string
  updated_at: string
  has_pdf: boolean
  has_xlsx: boolean
  has_json: boolean
}

export interface ComplianceReportPackBlockingIssue {
  event_id: number
  parameter_id: number
  event_type: string
  status: string
}

export interface ComplianceReportPackDetail extends ComplianceReportPack {
  blocking_issues: ComplianceReportPackBlockingIssue[]
}

export interface ComplianceReportPackList {
  total: number
  items: ComplianceReportPack[]
}

export interface ComplianceReportPackPayload {
  permit_id: number
  start: string
  end: string
}

export const listReportPacks = (permitId?: number, limit = 50, offset = 0) =>
  api.get<ComplianceReportPackList>('/compliance/report-packs', {
    params: { permit_id: permitId, limit, offset },
  })
export const createReportPack = (data: ComplianceReportPackPayload) =>
  api.post<ComplianceReportPack>('/compliance/report-packs', data)

// ── Compliance AI Assistant ─────────────────────────────────────────────────
// Mirrors backend app/services/compliance_assistant.py + POST /compliance/assistant.
// The assistant is READ + DRAFT only: it surfaces deterministic data and links
// real event/pack/permit IDs. create_pack/draft are PROPOSALS — the tab writes
// only when the user explicitly clicks Save-as-note / Create-pack.
export type ComplianceAssistantIntent =
  | 'readiness'
  | 'breaches'
  | 'missing_explanations'
  | 'draft_explanation'
  | 'create_pack'
  | 'fallback'

export type ComplianceAssistantLinkType = 'event' | 'pack' | 'permit'

export interface ComplianceAssistantLink {
  type: ComplianceAssistantLinkType
  id: number
}

export interface ComplianceAssistantProposedAction {
  action: 'create_report_pack'
  permit_id: number
  period_start: string | null
  period_end: string | null
}

export interface ComplianceAssistantResponse {
  intent: ComplianceAssistantIntent
  answer: string
  links: ComplianceAssistantLink[]
  data: { draft?: string | null; [k: string]: unknown }
  proposed_action: ComplianceAssistantProposedAction | null
}

export interface ComplianceAssistantQuery {
  question: string
  permit_id?: number
  start?: string
  end?: string
}

export const askComplianceAssistant = (q: ComplianceAssistantQuery) =>
  api.post<ComplianceAssistantResponse>('/compliance/assistant', q)
export const getReportPack = (id: number) =>
  api.get<ComplianceReportPackDetail>(`/compliance/report-packs/${id}`)
export const generateReportPack = (id: number) =>
  api.post<ComplianceReportPack>(`/compliance/report-packs/${id}/generate`)
export const submitReportPackReview = (id: number) =>
  api.post<ComplianceReportPack>(`/compliance/report-packs/${id}/submit-review`)
export const approveReportPack = (id: number) =>
  api.post<ComplianceReportPack>(`/compliance/report-packs/${id}/approve`)
export const deleteReportPack = (id: number) =>
  api.delete<{ id: number; deleted: boolean }>(`/compliance/report-packs/${id}`)
// Authenticated blob fetch — the axios `api` instance attaches the Bearer token.
export const downloadReportPack = (id: number, format: ComplianceReportPackFormat) =>
  api.get<Blob>(`/compliance/report-packs/${id}/download`, {
    params: { format },
    responseType: 'blob',
  })

// --- Facility variables -----------------------------------------------------
export type ExprNode = Record<string, unknown>

export interface FacilityVariable {
  id: number
  code: string
  name: string
  description: string
  kind: 'scalar' | 'series'
  value_type: string
  unit: string
  expression: ExprNode
  null_policy: string
  quality_policy: string
  default_time_grain: string | null
  is_active: boolean
  version: number
  dependency_count: number
  warnings: string[]
}

export interface FacilityVariableCreate {
  code: string
  name: string
  description?: string
  kind: 'scalar' | 'series'
  unit?: string
  value_type?: string
  expression: ExprNode
  null_policy?: string
  quality_policy?: string
  default_time_grain?: string | null
}

export interface FacilityVariableUpdate {
  name: string
  description?: string
  unit?: string
  expression: ExprNode
  null_policy?: string
  quality_policy?: string
  default_time_grain?: string | null
}

export interface PreviewWindow {
  type: 'month' | 'custom'
  year?: number
  month?: number
  start?: string
  end?: string
}
export interface PreviewRequestBody {
  window: PreviewWindow
  grain?: string | null
  tz_offset_hours?: number | null
}
export type PreviewResult =
  | { kind: 'scalar'; value: number | null; unit: string }
  | { kind: 'series'; points: { ts: string; value: number | null }[]; unit: string }

export interface VariableDependency {
  depends_on_type: 'tag' | 'variable'
  depends_on_tag_id: number | null
  depends_on_variable_id: number | null
}

export const listFacilityVariables = () => api.get<FacilityVariable[]>('/facility-variables/')
export const getFacilityVariable = (id: number) => api.get<FacilityVariable>(`/facility-variables/${id}`)
export const createFacilityVariable = (data: FacilityVariableCreate) =>
  api.post<FacilityVariable>('/facility-variables/', data)
export const updateFacilityVariable = (id: number, data: FacilityVariableUpdate) =>
  api.put<FacilityVariable>(`/facility-variables/${id}`, data)
export const deleteFacilityVariable = (id: number, force = false) =>
  api.delete(`/facility-variables/${id}${force ? '?force=true' : ''}`)
export const validateExpression = (body: { expression: ExprNode; kind: 'scalar' | 'series' }) =>
  api.post<{ valid: boolean }>('/facility-variables/validate', body)
export const previewVariable = (id: number, body: PreviewRequestBody) =>
  api.post<PreviewResult>(`/facility-variables/${id}/preview`, body)
export const getVariableDependencies = (id: number) =>
  api.get<VariableDependency[]>(`/facility-variables/${id}/dependencies`)
