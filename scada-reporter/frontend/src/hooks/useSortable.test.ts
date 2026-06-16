import { describe, it, expect } from 'vitest'
import { sortRows } from './useSortable'

interface Row {
  name: string
  value: number | null
}

const rows: Row[] = [
  { name: 'Beta', value: 5 },
  { name: 'alpha', value: null },
  { name: 'Gamma', value: 2 },
]

describe('sortRows', () => {
  it('returns a copy unchanged when key is null', () => {
    const out = sortRows(rows, null, 'asc')
    expect(out).toEqual(rows)
    expect(out).not.toBe(rows)
  })

  it('sorts numbers ascending, nulls last', () => {
    const out = sortRows(rows, 'value', 'asc')
    expect(out.map((r) => r.value)).toEqual([2, 5, null])
  })

  it('sorts numbers descending, nulls still last', () => {
    const out = sortRows(rows, 'value', 'desc')
    expect(out.map((r) => r.value)).toEqual([5, 2, null])
  })

  it('sorts strings case-insensitively (tr locale)', () => {
    const out = sortRows(rows, 'name', 'asc')
    expect(out.map((r) => r.name)).toEqual(['alpha', 'Beta', 'Gamma'])
  })

  it('uses custom accessor', () => {
    const out = sortRows(rows, 'len', 'asc', (r) => r.name.length)
    expect(out.map((r) => r.name)).toEqual(['Beta', 'alpha', 'Gamma'])
  })
})
