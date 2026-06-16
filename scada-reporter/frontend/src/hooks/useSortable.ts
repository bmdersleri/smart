import { useMemo, useState } from 'react'

export type SortDir = 'asc' | 'desc'
export interface SortState {
  key: string | null
  dir: SortDir
}

type Accessor<T> = (row: T, key: string) => unknown

function defaultAccessor<T>(row: T, key: string): unknown {
  return (row as Record<string, unknown>)[key]
}

function compare(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return a === b ? 0 : a ? 1 : -1
  return String(a).localeCompare(String(b), 'tr', { numeric: true, sensitivity: 'base' })
}

/** Satırları verilen anahtara göre sırala. key null ise kopya döner (değişmez).
 * null/undefined yön ne olursa olsun her zaman sona gider. */
export function sortRows<T>(
  rows: T[],
  key: string | null,
  dir: SortDir,
  accessor: Accessor<T> = defaultAccessor
): T[] {
  if (!key) return [...rows]
  const sign = dir === 'asc' ? 1 : -1
  return [...rows].sort((x, y) => {
    const a = accessor(x, key)
    const b = accessor(y, key)
    const an = a === null || a === undefined
    const bn = b === null || b === undefined
    if (an && bn) return 0
    if (an) return 1
    if (bn) return -1
    return sign * compare(a, b)
  })
}

/** Tablo kolon sıralaması: tıkla -> asc, tekrar -> desc. */
export function useSortable<T>(rows: T[], accessor?: Accessor<T>) {
  const [sort, setSort] = useState<SortState>({ key: null, dir: 'asc' })
  const toggle = (key: string) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }))
  const sorted = useMemo(() => sortRows(rows, sort.key, sort.dir, accessor), [rows, sort, accessor])
  return { sorted, sort, toggle }
}
