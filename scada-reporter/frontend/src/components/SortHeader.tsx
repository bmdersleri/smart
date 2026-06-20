import { useTranslation } from 'react-i18next'
import type { SortState } from '../hooks/useSortable'

interface Props {
  label: string
  sortKey: string
  sort: SortState
  onToggle: (key: string) => void
  align?: 'left' | 'right' | 'center'
  className?: string
}

/** Clickable table header with sort arrows. Matches the existing th styling. */
export default function SortHeader({ label, sortKey, sort, onToggle, align = 'left', className = '' }: Props) {
  const { t } = useTranslation('common')
  const active = sort.key === sortKey
  const arrow = active ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'
  const justify = align === 'right' ? 'justify-end' : align === 'center' ? 'justify-center' : 'justify-start'
  // Logical text alignment so RTL mirrors (left→start, right→end); justify-* is already direction-aware.
  const textAlign = align === 'right' ? 'text-end' : align === 'center' ? 'text-center' : 'text-start'
  // Padding/color come from the caller (className); here only behavior + alignment.
  const pad = className || 'px-4 py-2'
  return (
    <th
      onClick={() => onToggle(sortKey)}
      className={`cursor-pointer select-none hover:text-gray-300 transition-colors ${textAlign} ${pad}`}
      title={t('sort_hint')}
    >
      <span className={`inline-flex items-center gap-1 ${justify}`}>
        {label}
        <span className={active ? 'text-cyan-400' : 'text-gray-700'}>{arrow}</span>
      </span>
    </th>
  )
}
