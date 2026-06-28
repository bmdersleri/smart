import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getGroupTree, type GroupNode, type Tag } from '../../api/client'
import { COLORS } from './constants'

interface TreeNodeProps {
  node: GroupNode
  tagMap: Map<number, Tag>
  selected: number[]
  onToggle: (id: number) => void
  depth: number
}

function TreeNode({ node, tagMap, selected, onToggle, depth }: TreeNodeProps) {
  const [open, setOpen] = useState(depth < 1)
  const leafTags = node.tag_ids.map((id) => tagMap.get(id)).filter(Boolean) as Tag[]
  const hasContent = leafTags.length > 0 || node.children.length > 0

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1 px-1 py-1 text-xs text-gray-300 hover:text-white"
        style={{ paddingInlineStart: depth * 10 + 4 }}
      >
        <span className="text-gray-500 w-3">{hasContent ? (open ? '▾' : '▸') : '·'}</span>
        <span className="truncate font-medium">{node.name}</span>
        <span className="text-gray-600 ms-auto">{node.tag_ids.length || ''}</span>
      </button>
      {open && (
        <div>
          {node.children.map((child, i) => (
            <TreeNode
              key={child.id ?? `${node.name}-${i}`}
              node={child}
              tagMap={tagMap}
              selected={selected}
              onToggle={onToggle}
              depth={depth + 1}
            />
          ))}
          {leafTags.map((tag) => {
            const selectedIndex = selected.indexOf(tag.id)
            const isSelected = selectedIndex >= 0
            const color = isSelected ? COLORS[selectedIndex % COLORS.length] : '#6b7280'

            return (
              <button
                key={tag.id}
                onClick={() => onToggle(tag.id)}
                className={`w-full text-start py-1 rounded-lg text-sm flex items-center gap-2 ${
                  isSelected
                    ? 'bg-gray-800/60 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                }`}
                style={{ paddingInlineStart: (depth + 1) * 10 + 8 }}
              >
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                <span className="truncate">{tag.name}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function GroupTree({
  mode,
  tags,
  selected,
  onToggle,
}: {
  mode: 'auto' | 'manual'
  tags: Tag[]
  selected: number[]
  onToggle: (id: number) => void
}) {
  const { t } = useTranslation('trend')
  const { data: tree = [] } = useQuery({
    queryKey: ['groupTree', mode],
    queryFn: () => getGroupTree(mode).then((r) => r.data),
  })
  const tagMap = useMemo(() => new Map(tags.map((tag) => [tag.id, tag])), [tags])

  if (tree.length === 0) {
    return <p className="text-gray-500 text-xs px-1">{t('no_group')}</p>
  }

  return (
    <div className="space-y-0.5">
      {tree.map((node, i) => (
        <TreeNode
          key={node.id ?? `root-${i}`}
          node={node}
          tagMap={tagMap}
          selected={selected}
          onToggle={onToggle}
          depth={0}
        />
      ))}
    </div>
  )
}
