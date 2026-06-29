import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import type { ExprNode } from '../../api/client'

const OPS = ['agg', 'series', 'const', 'ref', 'reduce', 'moving_avg', 'round', 'abs', 'add', 'sub', 'mul', 'div', 'coalesce'] as const
const AGGS = ['sum', 'avg', 'min', 'max', 'last', 'delta'] as const
const REDUCES = ['sum', 'avg', 'min', 'max', 'last'] as const
const GRAINS = ['hour', 'day', 'week', 'month'] as const
const ON_ZERO = ['null', 'zero', 'fail'] as const

type Op = (typeof OPS)[number]

export function emptyNode(op: Op): ExprNode {
  switch (op) {
    case 'const': return { op: 'const', value: 0 }
    case 'ref': return { op: 'ref', variable_id: 0 }
    case 'agg': return { op: 'agg', source: { type: 'tag', tag_id: 0 }, agg: 'sum', window: 'day' }
    case 'series': return { op: 'series', source: { type: 'tag', tag_id: 0 }, agg: 'sum', grain: 'day', window: 'day' }
    case 'reduce': return { op: 'reduce', reduce: 'sum', source: emptyNode('series') }
    case 'moving_avg': return { op: 'moving_avg', window_size: 3, source: emptyNode('series') }
    case 'round': return { op: 'round', ndigits: 0, source: emptyNode('agg') }
    case 'abs': return { op: 'abs', source: emptyNode('agg') }
    case 'div': return { op: 'div', on_zero: 'null', args: [emptyNode('agg'), emptyNode('const')] }
    default: return { op, args: [emptyNode('agg'), emptyNode('const')] } // add|sub|mul|coalesce
  }
}

const selCls = 'bg-surface-sunken border border-edge-strong rounded px-2 py-1 text-sm text-white'

interface Props {
  value: ExprNode
  onChange: (node: ExprNode) => void
  tags: { id: number; name: string; unit?: string }[]
  variables: { id: number; code: string }[]
}

export default function ExpressionBuilder({ value, onChange, tags, variables }: Props) {
  const { t } = useTranslation('facilityVariables')
  const opId = useId()
  const node = value || emptyNode('const')
  const op = node.op as Op
  const patch = (p: Record<string, unknown>) => onChange({ ...node, ...p })
  const args = (node.args as ExprNode[]) || []
  const setArg = (i: number, child: ExprNode) => patch({ args: args.map((a, j) => (j === i ? child : a)) })

  return (
    <div className="border border-edge rounded-lg p-3 space-y-2 bg-black/20">
      <label className="flex items-center gap-2 text-xs text-gray-400">
        {t('builder_op')}
        <select id={opId} aria-label={t('builder_op')} className={selCls} value={op}
          onChange={(e) => onChange(emptyNode(e.target.value as Op))}>
          {OPS.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>

      {op === 'const' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_value')}
          <input type="number" className={selCls} value={Number(node.value ?? 0)}
            onChange={(e) => patch({ value: Number(e.target.value) })} />
        </label>
      )}

      {op === 'ref' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_variable')}
          <select className={selCls} value={Number(node.variable_id ?? 0)}
            onChange={(e) => patch({ variable_id: Number(e.target.value) })}>
            <option value={0}>—</option>
            {variables.map((v) => <option key={v.id} value={v.id}>{v.code}</option>)}
          </select>
        </label>
      )}

      {(op === 'agg' || op === 'series') && (
        <div className="flex flex-wrap gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_tag')}
            <select aria-label={t('builder_tag')} className={selCls}
              value={Number((node.source as { tag_id?: number })?.tag_id ?? 0)}
              onChange={(e) => patch({ source: { type: 'tag', tag_id: Number(e.target.value) } })}>
              <option value={0}>—</option>
              {tags.map((tg) => <option key={tg.id} value={tg.id}>{tg.name}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_agg')}
            <select className={selCls} value={String(node.agg ?? 'sum')}
              onChange={(e) => patch({ agg: e.target.value })}>
              {AGGS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          {op === 'series' && (
            <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_grain')}
              <select className={selCls} value={String(node.grain ?? 'day')}
                onChange={(e) => patch({ grain: e.target.value })}>
                {GRAINS.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
          )}
          <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_window')}
            <input className={selCls} value={String(node.window ?? 'day')}
              placeholder={t('builder_window_help')}
              onChange={(e) => patch({ window: e.target.value })} />
          </label>
        </div>
      )}

      {op === 'reduce' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_reduce')}
          <select className={selCls} value={String(node.reduce ?? 'sum')}
            onChange={(e) => patch({ reduce: e.target.value })}>
            {REDUCES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
      )}

      {op === 'moving_avg' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_window_size')}
          <input type="number" min={1} className={selCls} value={Number(node.window_size ?? 3)}
            onChange={(e) => patch({ window_size: Math.max(1, Number(e.target.value)) })} />
        </label>
      )}

      {op === 'round' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_ndigits')}
          <input type="number" className={selCls} value={Number(node.ndigits ?? 0)}
            onChange={(e) => patch({ ndigits: Number(e.target.value) })} />
        </label>
      )}

      {op === 'div' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_on_zero')}
          <select className={selCls} value={String(node.on_zero ?? 'null')}
            onChange={(e) => patch({ on_zero: e.target.value })}>
            {ON_ZERO.map((z) => <option key={z} value={z}>{z}</option>)}
          </select>
        </label>
      )}

      {/* single-child ops */}
      {(op === 'reduce' || op === 'moving_avg' || op === 'round' || op === 'abs') && (
        <div className="ms-4 border-s border-edge ps-3">
          <ExpressionBuilder value={node.source as ExprNode} tags={tags} variables={variables}
            onChange={(child) => patch({ source: child })} />
        </div>
      )}

      {/* variadic ops */}
      {(op === 'add' || op === 'sub' || op === 'mul' || op === 'div' || op === 'coalesce') && (
        <div className="ms-4 border-s border-edge ps-3 space-y-2">
          {args.map((a, i) => (
            <div key={i} className="space-y-1">
              <ExpressionBuilder value={a} tags={tags} variables={variables} onChange={(child) => setArg(i, child)} />
              {args.length > 1 && (
                <button type="button" className="text-xs text-red-400 hover:underline"
                  onClick={() => patch({ args: args.filter((_, j) => j !== i) })}>
                  {t('builder_remove')}
                </button>
              )}
            </div>
          ))}
          <button type="button" className="text-xs text-cyan-400 hover:underline"
            onClick={() => patch({ args: [...args, emptyNode('const')] })}>
            {t('builder_add_arg')}
          </button>
        </div>
      )}
    </div>
  )
}
