import { describe, it, expect } from 'vitest'
import { toSavePayload } from './excelTemplates.helpers'
import type { MappingRow } from './excelTemplates.helpers'

const base: MappingRow = {
  col_letter: 'B', source_code: '', label: '', tag_id: null, agg: 'last', enabled: true,
  source_type: 'variable', variable_id: 9, write_mode: 'reduce', reduce_op: 'sum',
  target_mode: 'cell', target_cell: 'B3', variable_code_snapshot: null,
}

describe('toSavePayload — variable binding', () => {
  it('keeps an enabled variable row even when tag_id is null', () => {
    const out = toSavePayload({ name: 't', sheet: 'S' } as never, [base])
    expect(out.columns).toHaveLength(1)
    expect(out.columns[0]).toMatchObject({
      col_letter: 'B', tag_id: null, source_type: 'variable', variable_id: 9,
      write_mode: 'reduce', reduce_op: 'sum', target_mode: 'cell', target_cell: 'B3',
    })
  })
  it('nulls variable_id for a tag row and keeps tag_id', () => {
    const tagRow: MappingRow = { ...base, source_type: 'tag', tag_id: 5, variable_id: 9, write_mode: null, reduce_op: null, target_mode: 'column', target_cell: null }
    const out = toSavePayload({ name: 't', sheet: 'S' } as never, [tagRow])
    expect(out.columns[0]).toMatchObject({ tag_id: 5, source_type: 'tag', variable_id: null })
  })
  it('drops a disabled row', () => {
    const out = toSavePayload({ name: 't', sheet: 'S' } as never, [{ ...base, enabled: false }])
    expect(out.columns).toHaveLength(0)
  })
})
