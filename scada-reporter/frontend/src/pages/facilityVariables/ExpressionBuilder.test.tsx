import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../../i18n'
import ExpressionBuilder, { emptyNode } from './ExpressionBuilder'

const tags = [{ id: 1, name: 'Debi', unit: 'm3' }]
const variables = [{ id: 9, code: 'var_x' }]

describe('ExpressionBuilder', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })

  it('emptyNode produces a valid const node', () => {
    expect(emptyNode('const')).toEqual({ op: 'const', value: 0 })
  })

  it('emits an agg node when op=agg and a tag is chosen', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilder value={emptyNode('agg')} onChange={onChange} tags={tags} variables={variables} />)
    // choose the tag
    fireEvent.change(screen.getByLabelText(/Tag/i), { target: { value: '1' } })
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ op: 'agg', source: { type: 'tag', tag_id: 1 }, agg: 'sum', window: 'day' }),
    )
  })

  it('switching op to const swaps the node', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilder value={emptyNode('agg')} onChange={onChange} tags={tags} variables={variables} />)
    fireEvent.change(screen.getByLabelText(/Operation/i), { target: { value: 'const' } })
    expect(onChange).toHaveBeenCalledWith({ op: 'const', value: 0 })
  })

  it('reduce node renders a nested child builder', () => {
    const node = { op: 'reduce', reduce: 'sum', source: { op: 'series', source: { type: 'tag', tag_id: 1 }, agg: 'sum', grain: 'day', window: 'day' } }
    render(<ExpressionBuilder value={node} onChange={vi.fn()} tags={tags} variables={variables} />)
    // two Operation selects: outer (reduce) + nested (series)
    expect(screen.getAllByLabelText(/Operation/i).length).toBe(2)
  })
})
