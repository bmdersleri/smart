import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi } from 'vitest'
import i18n from '../i18n'
import Tags from './Tags'

const canMock = vi.fn()
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'operator', permissions: [] }, can: canMock, logout: vi.fn() }),
}))
// Stub the data layer so the page renders without network.
vi.mock('../api/client', () => ({
  getTags: vi.fn().mockResolvedValue({ data: [] }),
  getGroups: vi.fn().mockResolvedValue({ data: [] }),
  getGroupTree: vi.fn().mockResolvedValue({ data: [] }),
  createTag: vi.fn().mockResolvedValue({ data: {} }),
  deleteTag: vi.fn().mockResolvedValue({ data: {} }),
  updateTag: vi.fn().mockResolvedValue({ data: {} }),
  importTags: vi.fn().mockResolvedValue({ data: {} }),
  importTagsCsv: vi.fn().mockResolvedValue({ data: {} }),
  exportTags: vi.fn().mockResolvedValue({ data: [] }),
  createGroup: vi.fn().mockResolvedValue({ data: {} }),
  deleteGroup: vi.fn().mockResolvedValue({ data: {} }),
  assignTagsToGroup: vi.fn().mockResolvedValue({ data: {} }),
  unassignTags: vi.fn().mockResolvedValue({ data: {} }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('Tags create gating', () => {
  it('hides create when can() is false', async () => {
    await i18n.changeLanguage('en')
    canMock.mockReturnValue(false)
    wrap(<Tags />)
    expect(screen.queryByRole('button', { name: /\+ Add Tag/i })).not.toBeInTheDocument()
  })
})
