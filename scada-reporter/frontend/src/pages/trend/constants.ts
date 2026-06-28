export const COLORS = [
  '#f87171',
  '#34d399',
  '#facc15',
  '#60a5fa',
  '#a78bfa',
  '#fb923c',
  '#f472b6',
  '#38bdf8',
]

export const HOURS = [
  { v: 1, key: 'hours_1' },
  { v: 6, key: 'hours_6' },
  { v: 24, key: 'hours_24' },
  { v: 168, key: 'hours_168' },
]

export const PRESET_KEY = 'trend_presets'

export interface Preset {
  name: string
  tag_ids: number[]
  hours: number
}

export interface TrendSeries {
  tag_id: number
  name: string
  unit: string
  data: { t: string; v: number }[]
  // Görünen etiket (legend/tooltip): tag açıklaması, boşsa teknik ada düşer.
  // Veri yine benzersiz `name` ile anahtarlanır (açıklamalar benzersiz değildir).
  label?: string
}

export type ChartDataPoint = Record<string, number | string>

export interface ActivePayloadRow {
  name: string
  value: number
  color: string
  unit: string
  label?: string
}
