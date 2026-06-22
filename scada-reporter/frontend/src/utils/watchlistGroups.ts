import type { WatchlistGroup } from '../api/client'

export function tagInGroup(group: WatchlistGroup, tagId: number): boolean {
  return group.tags.some((t) => t.tag_id === tagId)
}
