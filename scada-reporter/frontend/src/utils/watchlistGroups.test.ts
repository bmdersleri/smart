import { describe, it, expect } from 'vitest'
import { tagInGroup } from './watchlistGroups'
import type { WatchlistGroup } from '../api/client'

const g: WatchlistGroup = { id: 1, name: 'A', sort_order: 0, tag_count: 1, tags: [{ tag_id: 5, name: 'X' }] }

describe('tagInGroup', () => {
  it('true when tag present', () => { expect(tagInGroup(g, 5)).toBe(true) })
  it('false when absent', () => { expect(tagInGroup(g, 9)).toBe(false) })
})
