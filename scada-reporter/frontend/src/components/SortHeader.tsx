import type { SortState } from '../hooks/useSortable'

interface Props {
  label: string
  sortKey: string
  sort: SortState
  onToggle: (key: string) => void
  align?: 'left' | 'right' | 'center'
  className?: string
}

/** Tıklanabilir, sıralama oklu tablo başlığı. Mevcut th stiliyle uyumlu. */
export default function SortHeader({ label, sortKey, sort, onToggle, align = 'left', className = '' }: Props) {
  const active = sort.key === sortKey
  const arrow = active ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'
  const justify = align === 'right' ? 'justify-end' : align === 'center' ? 'justify-center' : 'justify-start'
  // Dolgu/renk çağırandan gelir (className); burada yalnız davranış + hizalama.
  const pad = className || 'px-4 py-2'
  return (
    <th
      onClick={() => onToggle(sortKey)}
      className={`cursor-pointer select-none hover:text-gray-300 transition-colors text-${align} ${pad}`}
      title="Sıralamak için tıkla"
    >
      <span className={`inline-flex items-center gap-1 ${justify}`}>
        {label}
        <span className={active ? 'text-cyan-400' : 'text-gray-700'}>{arrow}</span>
      </span>
    </th>
  )
}
