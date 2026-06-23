import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { format } from 'date-fns'
import { enUS, tr, ru, de } from 'date-fns/locale'
import { parseUtc } from '../utils/time'
import {
  listTemplates, createTemplate, updateTemplate, deleteTemplate, runTemplate,
  listScheduled, createScheduled, toggleScheduled, deleteScheduled,
  getArchive, downloadArchiveReport,
  getTags, listGrafanaDashboards, listGrafanaPanels,
} from '../api/client'
import type { ReportTemplate, TemplateCreate, ScheduledReport, ArchiveEntry, GrafanaPanelRef } from '../api/client'
import { useSortable } from '../hooks/useSortable'
import SortHeader from '../components/SortHeader'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DATE_LOCALES: Record<string, typeof tr> = { en: enUS, tr, ru, de }

const fmtDate = (s: string | null, lang: string) =>
  s ? format(parseUtc(s), 'dd.MM.yy HH:mm', { locale: DATE_LOCALES[lang] ?? enUS }) : '—'

const fmtBytes = (n: number | null) => {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

const STATUS_COLORS: Record<string, string> = {
  completed: 'bg-green-900/50 text-green-300',
  running: 'bg-blue-900/50 text-blue-300',
  failed: 'bg-red-900/50 text-red-300',
  pending: 'bg-gray-700 text-gray-300',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[status] ?? 'bg-gray-700 text-gray-300'}`}>
      {status === 'running' && <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />}
      {status}
    </span>
  )
}

const TIME_RANGE_OPTS = [
  { value: 'last_1h', labelKey: 'time_last_1h' },
  { value: 'last_24h', labelKey: 'time_last_24h' },
  { value: 'last_7d', labelKey: 'time_last_7d' },
  { value: 'last_30d', labelKey: 'time_last_30d' },
  { value: 'custom', labelKey: 'time_custom' },
]

const INPUT = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500'
const BTN_PRIMARY = 'px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors'
const BTN_GHOST = 'px-4 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors'

// ---------------------------------------------------------------------------
// Template Editor Modal (4-step wizard)
// ---------------------------------------------------------------------------

const DEFAULT_FORM: TemplateCreate = {
  name: '', description: '',
  tag_ids: [],
  time_range_type: 'last_24h', custom_start: null, custom_end: null,
  interval: 'hourly', output_format: 'excel',
  include_std_dev: true, include_percentiles: true, percentile_levels: [10, 25, 50, 75, 90, 95],
  include_trend_line: true,
  anomaly_enabled: true, anomaly_zscore_threshold: 3.0,
  show_summary_stats: true, show_trend_charts: true, show_anomaly_table: true, show_raw_data: false,
}

function TemplateEditorModal({
  initial, onClose,
}: { initial?: ReportTemplate; onClose: () => void }) {
  const { t } = useTranslation(['advancedReports', 'common'])
  const qc = useQueryClient()
  const [step, setStep] = useState(0)
  const [form, setForm] = useState<TemplateCreate>(
    initial
      ? { ...initial }
      : { ...DEFAULT_FORM }
  )
  const [grafanaPanels, setGrafanaPanels] = useState<GrafanaPanelRef[]>(
    initial?.grafana_panels ?? []
  )
  const [selectedDashUid, setSelectedDashUid] = useState('')
  const [selectedPanelId, setSelectedPanelId] = useState<number | ''>('')

  const { data: tags = [] } = useQuery({ queryKey: ['tags'], queryFn: () => getTags().then(r => r.data) })
  const devices = [...new Set(tags.map(t => t.device).filter(Boolean))]

  const { data: dashboards = [] } = useQuery({
    queryKey: ['grafana-dashboards'],
    queryFn: () => listGrafanaDashboards().then(r => r.data),
    retry: false,
  })
  const { data: panels = [] } = useQuery({
    queryKey: ['grafana-panels', selectedDashUid],
    queryFn: () => listGrafanaPanels(selectedDashUid).then(r => r.data),
    enabled: !!selectedDashUid,
    retry: false,
  })

  const addGrafanaPanel = () => {
    if (!selectedDashUid || selectedPanelId === '') return
    const panel = panels.find(p => p.id === selectedPanelId)
    const dash = dashboards.find(d => d.uid === selectedDashUid)
    if (!panel || !dash) return
    const entry: GrafanaPanelRef = { dashboard_uid: selectedDashUid, panel_id: selectedPanelId as number, title: `${dash.title} / ${panel.title}` }
    if (!grafanaPanels.some(p => p.dashboard_uid === entry.dashboard_uid && p.panel_id === entry.panel_id)) {
      setGrafanaPanels(prev => [...prev, entry])
    }
  }

  const removeGrafanaPanel = (idx: number) =>
    setGrafanaPanels(prev => prev.filter((_, i) => i !== idx))

  const mut = useMutation({
    mutationFn: () => {
      const payload: TemplateCreate = { ...form, grafana_panels: grafanaPanels }
      return initial
        ? updateTemplate(initial.id, payload).then(r => r.data)
        : createTemplate(payload).then(r => r.data)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['adv-templates'] }); onClose() },
  })

  const set = <K extends keyof TemplateCreate>(k: K, v: TemplateCreate[K]) =>
    setForm(f => ({ ...f, [k]: v }))

  const toggleTag = (id: number) =>
    set('tag_ids', form.tag_ids.includes(id)
      ? form.tag_ids.filter(x => x !== id)
      : [...form.tag_ids, id])

  const STEPS = [t('step_tags'), t('step_options'), t('step_anomaly'), t('step_preview')]

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">{initial ? t('edit_template') : t('new_template')}</h2>
          <div className="flex gap-1 mt-3">
            {STEPS.map((s, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${i <= step ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-500'}`}>{i + 1}</div>
                <span className={`text-xs hidden sm:block ${i === step ? 'text-blue-400' : 'text-gray-600'}`}>{s}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">

          {/* Step 0: Tag selection */}
          {step === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-gray-400">{t('tags_help')}</p>
              {devices.map(dev => (
                <div key={dev}>
                  <p className="text-xs text-gray-500 uppercase font-medium mb-1">{dev}</p>
                  <div className="flex flex-wrap gap-2">
                    {tags.filter(t => t.device === dev).map(t => (
                      <button
                        key={t.id}
                        onClick={() => toggleTag(t.id)}
                        className={`px-3 py-1 rounded-lg text-sm border transition-colors ${form.tag_ids.includes(t.id) ? 'border-blue-500 bg-blue-600/20 text-blue-300' : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}
                      >
                        {t.name} {t.unit ? `(${t.unit})` : ''}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {tags.filter(t => !t.device).map(t => (
                <button key={t.id} onClick={() => toggleTag(t.id)}
                  className={`px-3 py-1 rounded-lg text-sm border transition-colors ${form.tag_ids.includes(t.id) ? 'border-blue-500 bg-blue-600/20 text-blue-300' : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}>
                  {t.name}
                </button>
              ))}
              <p className="text-xs text-gray-500">{t('tags_selected', { value: form.tag_ids.length })}</p>
            </div>
          )}

          {/* Step 1: Options */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="text-xs text-gray-400 mb-1 block">{t('time_range')}</label>
                <div className="flex flex-wrap gap-2">
                  {TIME_RANGE_OPTS.map(o => (
                    <button key={o.value} onClick={() => set('time_range_type', o.value)}
                      className={`px-3 py-1 rounded-lg text-sm border transition-colors ${form.time_range_type === o.value ? 'border-blue-500 bg-blue-600/20 text-blue-300' : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}>
                      {t(o.labelKey)}
                    </button>
                  ))}
                </div>
                {form.time_range_type === 'custom' && (
                  <div className="flex gap-3 mt-2">
                    <div className="flex-1">
                      <label className="text-xs text-gray-500 mb-1 block">{t('start')}</label>
                      <input type="datetime-local" className={INPUT}
                        value={form.custom_start?.slice(0, 16) ?? ''}
                        onChange={e => set('custom_start', e.target.value ? e.target.value + ':00' : null)} />
                    </div>
                    <div className="flex-1">
                      <label className="text-xs text-gray-500 mb-1 block">{t('end')}</label>
                      <input type="datetime-local" className={INPUT}
                        value={form.custom_end?.slice(0, 16) ?? ''}
                        onChange={e => set('custom_end', e.target.value ? e.target.value + ':00' : null)} />
                    </div>
                  </div>
                )}
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">{t('interval')}</label>
                <div className="flex gap-2">
                  {['hourly', 'daily', 'weekly'].map(v => (
                    <button key={v} onClick={() => set('interval', v)}
                      className={`px-3 py-1 rounded-lg text-sm border transition-colors capitalize ${form.interval === v ? 'border-blue-500 bg-blue-600/20 text-blue-300' : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}>
                      {v === 'hourly' ? t('interval_hourly') : v === 'daily' ? t('interval_daily') : t('interval_weekly')}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">{t('format')}</label>
                <div className="flex gap-2">
                  {['excel', 'pdf', 'json'].map(v => (
                    <button key={v} onClick={() => set('output_format', v)}
                      className={`px-3 py-1 rounded-lg text-sm border transition-colors uppercase ${form.output_format === v ? 'border-blue-500 bg-blue-600/20 text-blue-300' : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}>
                      {v}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-2 block">{t('statistics')}</label>
                <div className="space-y-2">
                  {([['include_std_dev', 'stat_std_dev'], ['include_percentiles', 'stat_percentiles'], ['include_trend_line', 'stat_trend_line']] as const).map(([k, labelKey]) => (
                    <label key={k} className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" className="accent-blue-500"
                        checked={form[k] as boolean}
                        onChange={e => set(k, e.target.checked)} />
                      <span className="text-sm text-gray-300">{t(labelKey)}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 2: Anomaly & Sections */}
          {step === 2 && (
            <div className="space-y-5">
              <div>
                <label className="flex items-center gap-2 cursor-pointer mb-3">
                  <input type="checkbox" className="accent-blue-500" checked={form.anomaly_enabled}
                    onChange={e => set('anomaly_enabled', e.target.checked)} />
                  <span className="text-sm font-medium text-white">{t('anomaly_enabled')}</span>
                </label>
                {form.anomaly_enabled && (
                  <div>
                    <label className="text-xs text-gray-400 mb-1 block">
                      {t('zscore_threshold')} <span className="text-blue-400 font-mono">{form.anomaly_zscore_threshold}</span>
                    </label>
                    <input type="range" min="0.5" max="5" step="0.1"
                      className="w-full accent-blue-500"
                      value={form.anomaly_zscore_threshold}
                      onChange={e => set('anomaly_zscore_threshold', parseFloat(e.target.value))} />
                    <div className="flex justify-between text-xs text-gray-600 mt-0.5">
                      <span>{t('zscore_sensitive')}</span><span>{t('zscore_coarse')}</span>
                    </div>
                  </div>
                )}
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-2 block">{t('report_sections')}</label>
                <div className="space-y-2">
                  {([
                    ['show_summary_stats', 'section_summary'],
                    ['show_trend_charts', 'section_trend'],
                    ['show_anomaly_table', 'section_anomaly'],
                    ['show_raw_data', 'section_raw'],
                  ] as const).map(([k, labelKey]) => (
                    <label key={k} className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" className="accent-blue-500"
                        checked={form[k] as boolean}
                        onChange={e => set(k, e.target.checked)} />
                      <span className="text-sm text-gray-300">{t(labelKey)}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Grafana Panels */}
              <div>
                <label className="text-xs text-gray-400 mb-2 block">{t('grafana_panels')}</label>
                <div className="flex flex-wrap gap-2 mb-2">
                  <select
                    className="flex-1 min-w-0 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                    value={selectedDashUid}
                    onChange={e => { setSelectedDashUid(e.target.value); setSelectedPanelId('') }}
                  >
                    <option value="">{t('grafana_select_dashboard')}</option>
                    {dashboards.map(d => <option key={d.uid} value={d.uid}>{d.title}</option>)}
                  </select>
                  <select
                    className="flex-1 min-w-0 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                    value={selectedPanelId}
                    onChange={e => setSelectedPanelId(e.target.value ? Number(e.target.value) : '')}
                    disabled={!selectedDashUid}
                  >
                    <option value="">{t('grafana_select_panel')}</option>
                    {panels.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
                  </select>
                  <button
                    type="button"
                    onClick={addGrafanaPanel}
                    disabled={!selectedDashUid || selectedPanelId === ''}
                    className="px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-medium transition-colors whitespace-nowrap"
                  >
                    {t('grafana_add_panel')}
                  </button>
                </div>
                {grafanaPanels.length > 0 && (
                  <ul className="space-y-1">
                    {grafanaPanels.map((p, i) => (
                      <li key={i} className="flex items-center justify-between bg-gray-800/60 rounded-lg px-3 py-1.5 text-sm text-gray-300">
                        <span className="truncate">{p.title}</span>
                        <button
                          type="button"
                          onClick={() => removeGrafanaPanel(i)}
                          className="ml-2 text-xs text-red-500 hover:text-red-400 shrink-0"
                        >
                          {t('grafana_remove')}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}

          {/* Step 3: Preview & Save */}
          {step === 3 && (
            <div className="space-y-4">
              <div className="bg-gray-800/60 rounded-xl p-4 space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-gray-500">{t('preview_tag_count')}</span><span className="text-white">{form.tag_ids.length}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">{t('preview_time_range')}</span><span className="text-white">{(() => { const o = TIME_RANGE_OPTS.find(o => o.value === form.time_range_type); return o ? t(o.labelKey) : '' })()}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">{t('preview_interval')}</span><span className="text-white capitalize">{form.interval}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">{t('preview_format')}</span><span className="text-white uppercase">{form.output_format}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">{t('preview_anomaly')}</span><span className={form.anomaly_enabled ? 'text-green-400' : 'text-gray-500'}>{form.anomaly_enabled ? t('anomaly_active', { value: form.anomaly_zscore_threshold }) : t('anomaly_off')}</span></div>
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">{t('template_name')}</label>
                <input className={INPUT} value={form.name}
                  onChange={e => set('name', e.target.value)} placeholder={t('template_name_placeholder')} />
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">{t('description')}</label>
                <input className={INPUT} value={form.description ?? ''}
                  onChange={e => set('description', e.target.value)} placeholder={t('description_placeholder')} />
              </div>
              {mut.isError && <p className="text-red-400 text-sm">{t('error_save_template')}</p>}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-5 border-t border-gray-800 flex justify-between">
          <button onClick={onClose} className={BTN_GHOST}>{t('common:cancel')}</button>
          <div className="flex gap-2">
            {step > 0 && <button onClick={() => setStep(s => s - 1)} className={BTN_GHOST}>{t('back')}</button>}
            {step < 3
              ? <button onClick={() => setStep(s => s + 1)} disabled={step === 0 && form.tag_ids.length === 0} className={BTN_PRIMARY}>{t('next')}</button>
              : <button onClick={() => mut.mutate()} disabled={!form.name || mut.isPending} className={BTN_PRIMARY}>
                  {mut.isPending ? t('saving') : initial ? t('update') : t('create')}
                </button>
            }
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schedule Create Modal
// ---------------------------------------------------------------------------

function ScheduleCreateModal({ templates, onClose }: { templates: ReportTemplate[]; onClose: () => void }) {
  const { t } = useTranslation(['advancedReports', 'common'])
  const qc = useQueryClient()
  const [form, setForm] = useState({
    template_id: templates[0]?.id ?? 0,
    name: '',
    schedule_type: 'cron' as 'cron' | 'interval',
    preset: 'daily',
    cron_hour: 8,
    cron_minute: 0,
    cron_day_of_week: null as string | null,
    cron_day_of_month: null as number | null,
    interval_hours: 4,
  })

  const PRESETS = [
    { value: 'daily', label: t('preset_daily') },
    { value: 'weekly', label: t('preset_weekly') },
    { value: 'monthly', label: t('preset_monthly') },
    { value: 'interval', label: t('preset_interval') },
  ]

  const mut = useMutation({
    mutationFn: () => {
      const isInterval = form.preset === 'interval'
      return createScheduled({
        template_id: form.template_id,
        name: form.name,
        schedule_type: isInterval ? 'interval' : 'cron',
        cron_hour: isInterval ? undefined : form.cron_hour,
        cron_minute: isInterval ? undefined : form.cron_minute,
        cron_day_of_week: form.preset === 'weekly' ? form.cron_day_of_week ?? 'mon' : undefined,
        cron_day_of_month: form.preset === 'monthly' ? form.cron_day_of_month ?? 1 : undefined,
        interval_hours: isInterval ? form.interval_hours : undefined,
      }).then(r => r.data)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['adv-scheduled'] }); onClose() },
  })

  const s = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md p-6 space-y-4">
        <h2 className="text-lg font-semibold text-white">{t('new_schedule')}</h2>

        <div>
          <label className="text-xs text-gray-400 mb-1 block">{t('template')}</label>
          <select className={INPUT} value={form.template_id}
            onChange={e => setForm(f => ({ ...f, template_id: Number(e.target.value) }))}>
            {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-400 mb-1 block">{t('schedule_type')}</label>
          <div className="flex gap-2">
            {PRESETS.map(p => (
              <button key={p.value} onClick={() => setForm(f => ({ ...f, preset: p.value }))}
                className={`flex-1 py-1.5 rounded-lg text-xs border transition-colors ${form.preset === p.value ? 'border-blue-500 bg-blue-600/20 text-blue-300' : 'border-gray-700 text-gray-400'}`}>
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {form.preset !== 'interval' && (
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-xs text-gray-400 mb-1 block">{t('hour')}</label>
              <input type="number" className={INPUT} min={0} max={23} value={form.cron_hour}
                onChange={e => setForm(f => ({ ...f, cron_hour: Number(e.target.value) }))} />
            </div>
            <div className="flex-1">
              <label className="text-xs text-gray-400 mb-1 block">{t('minute')}</label>
              <input type="number" className={INPUT} min={0} max={59} value={form.cron_minute}
                onChange={e => setForm(f => ({ ...f, cron_minute: Number(e.target.value) }))} />
            </div>
          </div>
        )}

        {form.preset === 'weekly' && (
          <div>
            <label className="text-xs text-gray-400 mb-1 block">{t('day')}</label>
            <select className={INPUT} value={form.cron_day_of_week ?? 'mon'}
              onChange={e => setForm(f => ({ ...f, cron_day_of_week: e.target.value }))}>
              {['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map(d => (
                <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
              ))}
            </select>
          </div>
        )}

        {form.preset === 'monthly' && (
          <div>
            <label className="text-xs text-gray-400 mb-1 block">{t('day_of_month')}</label>
            <input type="number" className={INPUT} min={1} max={31}
              value={form.cron_day_of_month ?? 1}
              onChange={e => setForm(f => ({ ...f, cron_day_of_month: Number(e.target.value) }))} />
          </div>
        )}

        {form.preset === 'interval' && (
          <div>
            <label className="text-xs text-gray-400 mb-1 block">{t('every_n_hours')}</label>
            <input type="number" className={INPUT} min={1} max={168} value={form.interval_hours} onChange={s('interval_hours')} />
          </div>
        )}

        <div>
          <label className="text-xs text-gray-400 mb-1 block">{t('schedule_name')}</label>
          <input className={INPUT} value={form.name} onChange={s('name')} placeholder={t('schedule_name_placeholder')} />
        </div>

        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className={BTN_GHOST + ' flex-1'}>{t('common:cancel')}</button>
          <button onClick={() => mut.mutate()} disabled={!form.name || mut.isPending} className={BTN_PRIMARY + ' flex-1'}>
            {mut.isPending ? t('creating') : t('create')}
          </button>
        </div>
        {mut.isError && <p className="text-red-400 text-sm">{t('error_occurred')}</p>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 1 — Templates
// ---------------------------------------------------------------------------

function TemplatesTab({ onRunDone }: { onRunDone: () => void }) {
  const { t, i18n } = useTranslation(['advancedReports', 'common'])
  const { can } = useAuth()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<ReportTemplate | null>(null)

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['adv-templates'],
    queryFn: () => listTemplates().then(r => r.data),
  })
  const { sorted: sortedTemplates, sort, toggle } = useSortable(templates, (t, k) =>
    k === 'tag' ? t.tag_ids.length : (t as unknown as Record<string, unknown>)[k]
  )

  const delMut = useMutation({
    mutationFn: (id: number) => deleteTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['adv-templates'] }),
  })

  const runMut = useMutation({
    mutationFn: (id: number) => runTemplate(id).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['adv-archive'] }); onRunDone() },
  })

  if (isLoading) return <p className="text-gray-500 text-sm p-4">{t('common:loading')}</p>

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <p className="text-sm text-gray-400">{t('template_count', { value: templates.length })}</p>
        {can('report_template:create') && (
          <button onClick={() => setShowCreate(true)} className={BTN_PRIMARY}>{t('new_template_btn')}</button>
        )}
      </div>
      {templates.length === 0
        ? <div className="text-center py-16 text-gray-600">{t('empty_templates')}</div>
        : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-start text-gray-500">
                  <SortHeader label={t('col_name')} sortKey="name" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_format')} sortKey="output_format" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_interval')} sortKey="interval" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_tag')} sortKey="tag" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_created')} sortKey="created_at" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <th className="pb-2 text-gray-500 font-medium text-end">{t('col_action')}</th>
                </tr>
              </thead>
              <tbody>
                {sortedTemplates.map(tpl => (
                  <tr key={tpl.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="py-3 text-white font-medium">{tpl.name}</td>
                    <td className="py-3 text-gray-300 uppercase">{tpl.output_format}</td>
                    <td className="py-3 text-gray-400 capitalize">{tpl.interval}</td>
                    <td className="py-3 text-gray-400">{tpl.tag_ids.length}</td>
                    <td className="py-3 text-gray-500">{fmtDate(tpl.created_at, i18n.language)}</td>
                    <td className="py-3 text-end">
                      <div className="flex gap-2 justify-end">
                        <button onClick={() => runMut.mutate(tpl.id)} disabled={runMut.isPending}
                          className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50">{t('run')}</button>
                        {can('report_template:edit') && (
                          <button onClick={() => setEditing(tpl)} className="text-xs text-gray-400 hover:text-white">{t('common:edit')}</button>
                        )}
                        {can('report_template:delete') && (
                          <button onClick={() => { if (confirm(t('confirm_delete_template'))) delMut.mutate(tpl.id) }}
                            className="text-xs text-red-500 hover:text-red-400">{t('common:delete')}</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
      {(showCreate) && <TemplateEditorModal onClose={() => setShowCreate(false)} />}
      {editing && <TemplateEditorModal initial={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 2 — Scheduled
// ---------------------------------------------------------------------------

function ScheduledTab() {
  const { t, i18n } = useTranslation(['advancedReports', 'common'])
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const { data: scheduled = [], isLoading } = useQuery({
    queryKey: ['adv-scheduled'],
    queryFn: () => listScheduled().then(r => r.data),
  })
  const { data: templates = [] } = useQuery({
    queryKey: ['adv-templates'],
    queryFn: () => listTemplates().then(r => r.data),
  })

  const toggleMut = useMutation({
    mutationFn: (id: number) => toggleScheduled(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['adv-scheduled'] }),
  })
  const delMut = useMutation({
    mutationFn: (id: number) => deleteScheduled(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['adv-scheduled'] }),
  })

  const templateName = (id: number) => templates.find(t => t.id === id)?.name ?? `#${id}`
  const { sorted: sortedScheduled, sort, toggle } = useSortable(scheduled, (s, k) =>
    k === 'template' ? templateName(s.template_id) : (s as unknown as Record<string, unknown>)[k]
  )

  if (isLoading) return <p className="text-gray-500 text-sm p-4">{t('common:loading')}</p>

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <p className="text-sm text-gray-400">{t('schedule_count', { value: scheduled.length })}</p>
        <button onClick={() => setShowCreate(true)} disabled={templates.length === 0} className={BTN_PRIMARY}>
          {t('new_schedule_btn')}
        </button>
      </div>
      {scheduled.length === 0
        ? <div className="text-center py-16 text-gray-600">{t('empty_scheduled')}</div>
        : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-start text-gray-500">
                  <SortHeader label={t('col_name')} sortKey="name" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_template')} sortKey="template" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_type')} sortKey="schedule_type" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_active')} sortKey="is_active" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_last_run')} sortKey="last_run_at" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_status')} sortKey="last_run_status" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_next')} sortKey="next_run_at" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <th className="pb-2 text-end text-gray-500 font-medium">{t('col_action')}</th>
                </tr>
              </thead>
              <tbody>
                {sortedScheduled.map((sr: ScheduledReport) => (
                  <tr key={sr.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="py-3 text-white">{sr.name}</td>
                    <td className="py-3 text-gray-400">{templateName(sr.template_id)}</td>
                    <td className="py-3 text-gray-400 text-xs">
                      {sr.schedule_type === 'interval' ? t('every_hours', { value: sr.interval_hours }) : t('cron')}
                    </td>
                    <td className="py-3">
                      <button onClick={() => toggleMut.mutate(sr.id)}
                        className={`w-10 h-5 rounded-full transition-colors relative ${sr.is_active ? 'bg-blue-600' : 'bg-gray-700'}`}>
                        <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${sr.is_active ? 'translate-x-5' : 'translate-x-0.5'}`} />
                      </button>
                    </td>
                    <td className="py-3 text-gray-500 text-xs">{fmtDate(sr.last_run_at, i18n.language)}</td>
                    <td className="py-3">{sr.last_run_status ? <StatusBadge status={sr.last_run_status} /> : <span className="text-gray-600 text-xs">—</span>}</td>
                    <td className="py-3 text-gray-500 text-xs">{fmtDate(sr.next_run_at, i18n.language)}</td>
                    <td className="py-3 text-end">
                      <button onClick={() => { if (confirm(t('confirm_delete_schedule'))) delMut.mutate(sr.id) }}
                        className="text-xs text-red-500 hover:text-red-400">{t('common:delete')}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
      {showCreate && templates.length > 0 && (
        <ScheduleCreateModal templates={templates} onClose={() => setShowCreate(false)} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 3 — Archive
// ---------------------------------------------------------------------------

function ArchiveTab() {
  const { t, i18n } = useTranslation('advancedReports')
  const [page, setPage] = useState(1)
  const [filterStatus, setFilterStatus] = useState('')
  const [filterTemplateId, setFilterTemplateId] = useState<number | undefined>()
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [downloading, setDownloading] = useState<number | null>(null)

  const { data: templates = [] } = useQuery({
    queryKey: ['adv-templates'],
    queryFn: () => listTemplates().then(r => r.data),
  })

  const params = {
    page, page_size: 50,
    ...(filterStatus ? { status: filterStatus } : {}),
    ...(filterTemplateId ? { template_id: filterTemplateId } : {}),
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
  }

  const { data } = useQuery({
    queryKey: ['adv-archive', params],
    queryFn: () => getArchive(params).then(r => r.data),
    refetchInterval: (query) => {
      const hasActive = query.state.data?.items.some(i => i.status === 'running' || i.status === 'pending')
      return hasActive ? 5000 : false
    },
  })

  const items = data?.items ?? []
  const totalPages = data?.total_pages ?? 0

  const download = async (entry: ArchiveEntry) => {
    setDownloading(entry.id)
    try {
      const r = await downloadArchiveReport(entry.id)
      const ext = entry.output_format === 'excel' ? 'xlsx' : entry.output_format
      const url = URL.createObjectURL(new Blob([r.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `rapor_${entry.id}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setDownloading(null)
    }
  }

  const templateName = (id: number | null) => id ? (templates.find(t => t.id === id)?.name ?? `#${id}`) : '—'
  const { sorted: sortedItems, sort, toggle } = useSortable(items, (e, k) =>
    k === 'template' ? templateName(e.template_id) : (e as unknown as Record<string, unknown>)[k]
  )

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300 focus:outline-none"
          value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setPage(1) }}>
          <option value="">{t('filter_all_statuses')}</option>
          {['completed', 'running', 'pending', 'failed'].map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300 focus:outline-none"
          value={filterTemplateId ?? ''} onChange={e => { setFilterTemplateId(e.target.value ? Number(e.target.value) : undefined); setPage(1) }}>
          <option value="">{t('filter_all_templates')}</option>
          {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <input type="date" className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300 focus:outline-none"
          value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1) }} />
        <span className="text-gray-600 self-center">—</span>
        <input type="date" className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300 focus:outline-none"
          value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1) }} />
        {(filterStatus || filterTemplateId || dateFrom || dateTo) && (
          <button onClick={() => { setFilterStatus(''); setFilterTemplateId(undefined); setDateFrom(''); setDateTo(''); setPage(1) }}
            className="text-xs text-gray-500 hover:text-gray-300">{t('filter_clear')}</button>
        )}
      </div>

      {/* Table */}
      {items.length === 0
        ? <div className="text-center py-16 text-gray-600">{t('empty_archive')}</div>
        : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-start text-gray-500">
                  <SortHeader label={t('col_date')} sortKey="created_at" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_template')} sortKey="template" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_trigger')} sortKey="trigger" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_period')} sortKey="start" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_format')} sortKey="output_format" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_status')} sortKey="status" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <SortHeader label={t('col_size')} sortKey="file_size_bytes" sort={sort} onToggle={toggle} className="pb-2 font-medium" />
                  <th className="pb-2 text-end text-gray-500 font-medium">{t('col_download')}</th>
                </tr>
              </thead>
              <tbody>
                {sortedItems.map(e => (
                  <tr key={e.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="py-3 text-gray-300 text-xs">{fmtDate(e.created_at, i18n.language)}</td>
                    <td className="py-3 text-gray-400 text-xs">{templateName(e.template_id)}</td>
                    <td className="py-3">
                      <span className={`text-xs px-2 py-0.5 rounded ${e.trigger === 'scheduled' ? 'bg-purple-900/40 text-purple-300' : 'bg-gray-700 text-gray-400'}`}>
                        {e.trigger}
                      </span>
                    </td>
                    <td className="py-3 text-gray-500 text-xs">
                      {fmtDate(e.start, i18n.language).split(' ')[0]}–{fmtDate(e.end, i18n.language).split(' ')[0]}
                    </td>
                    <td className="py-3 text-gray-400 text-xs uppercase">{e.output_format}</td>
                    <td className="py-3"><StatusBadge status={e.status} /></td>
                    <td className="py-3 text-gray-500 text-xs">{fmtBytes(e.file_size_bytes)}</td>
                    <td className="py-3 text-end">
                      {e.status === 'completed'
                        ? <button onClick={() => download(e)} disabled={downloading === e.id}
                            className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50">
                            {downloading === e.id ? '...' : '↓'}
                          </button>
                        : <span className="text-gray-700 text-xs">—</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            className="px-3 py-1 rounded-lg border border-gray-700 text-gray-400 disabled:opacity-30 hover:bg-gray-800 text-sm">←</button>
          {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
            const p = Math.max(1, Math.min(page - 3, totalPages - 6)) + i
            return (
              <button key={p} onClick={() => setPage(p)}
                className={`w-8 h-8 rounded-lg text-sm ${p === page ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800'}`}>
                {p}
              </button>
            )
          })}
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="px-3 py-1 rounded-lg border border-gray-700 text-gray-400 disabled:opacity-30 hover:bg-gray-800 text-sm">→</button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type Tab = 'templates' | 'scheduled' | 'archive'

export default function AdvancedReports() {
  const { t } = useTranslation('advancedReports')
  const [tab, setTab] = useState<Tab>('templates')

  const TABS: { id: Tab; label: string }[] = [
    { id: 'templates', label: t('tab_templates') },
    { id: 'scheduled', label: t('tab_scheduled') },
    { id: 'archive', label: t('tab_archive') },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">{t('title')}</h1>
        <p className="text-gray-500 text-sm mt-1">{t('subtitle')}</p>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-gray-800 mb-6">
        {TABS.map(tb => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === tb.id ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}>
            {tb.label}
          </button>
        ))}
      </div>

      {tab === 'templates' && <TemplatesTab onRunDone={() => setTab('archive')} />}
      {tab === 'scheduled' && <ScheduledTab />}
      {tab === 'archive' && <ArchiveTab />}
    </div>
  )
}
