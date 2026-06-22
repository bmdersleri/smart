// src/pages/dashboard/WatchlistGroups.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '../../i18n'
import WatchlistGroups from './WatchlistGroups'

vi.mock('../../api/client', () => ({
  listWatchlistGroups: () => Promise.resolve({ data: { groups: [{ id: 1, name: 'Pompalar', sort_order: 0, tag_count: 0, tags: [] }], ungrouped: [] } }),
  createWatchlistGroup: vi.fn(), renameWatchlistGroup: vi.fn(), deleteWatchlistGroup: vi.fn(),
  addTagToGroup: vi.fn(), removeTagFromGroup: vi.fn(),
  syncGrafana: () => Promise.resolve({ data: { written: 1, deleted: 0, errors: [] } }),
}))

describe('WatchlistGroups', () => {
  it('renders group names from the API', async () => {
    await i18n.changeLanguage('en')
    const qc = new QueryClient()
    render(<QueryClientProvider client={qc}><WatchlistGroups /></QueryClientProvider>)
    await waitFor(() => expect(screen.getByText('Pompalar')).toBeTruthy())
  })
})
