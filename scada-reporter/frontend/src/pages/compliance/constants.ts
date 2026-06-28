// Shared option lists for the Compliance Center. These mirror the backend
// enum constants in app/models/compliance.py and keep the config forms in sync
// with the validation the API enforces.
export const SOURCE_TYPES = ['scada', 'lab', 'hybrid'] as const
export const LIMIT_TYPES = ['value_limit', 'sample_count', 'sample_frequency', 'quality'] as const
export const AGGREGATIONS = ['instant', 'daily_avg', 'monthly_avg', 'count'] as const
export const REPORT_FREQUENCIES = [
  'daily',
  'weekly',
  'monthly',
  'quarterly',
  'custom_cron',
] as const
export const EVENT_TYPES = [
  'limit_exceeded',
  'missing_sample',
  'late_sample',
  'bad_quality',
  'needs_explanation',
] as const
export const EVENT_STATUSES = ['open', 'acknowledged', 'resolved', 'waived'] as const
export const SEVERITIES = ['info', 'warning', 'critical'] as const

export type ComplianceTab = 'overview' | 'permits' | 'events'

// Tailwind text-color accent per severity, used for event rows / badges.
export const SEVERITY_ACCENT: Record<string, string> = {
  critical: 'text-red-400',
  warning: 'text-amber-400',
  info: 'text-cyan-400',
}

export const STATUS_ACCENT: Record<string, string> = {
  open: 'text-red-400',
  acknowledged: 'text-amber-400',
  resolved: 'text-green-400',
  waived: 'text-gray-400',
}
