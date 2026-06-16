import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '../i18n'
import Tags from './Tags'

// Minimal data-layer mocks so a static label renders without a backend.
vi.mock('../api/client', () => ({
  getTags: () => Promise.resolve({ data: [] }),
  getGroups: () => Promise.resolve({ data: [] }),
  getGroupTree: () => Promise.resolve({ data: [] }),
  createTag: vi.fn(),
  deleteTag: vi.fn(),
  updateTag: vi.fn(),
  importTags: vi.fn(),
  importTagsCsv: vi.fn(),
  exportTags: vi.fn(),
  createGroup: vi.fn(),
  deleteGroup: vi.fn(),
  assignTagsToGroup: vi.fn(),
  unassignTags: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, username: 'admin', role: 'admin', full_name: 'Admin', language: 'en' } }),
}))

function renderTags() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Tags />
    </QueryClientProvider>
  )
}

describe('Tags i18n', () => {
  beforeEach(() => { cleanup() })

  it('renders the English page header', async () => {
    await i18n.changeLanguage('en')
    renderTags()
    expect(await screen.findByText('Tag Management')).toBeTruthy()
  })

  it('renders the Turkish page header', async () => {
    await i18n.changeLanguage('tr')
    renderTags()
    expect(await screen.findByText('Tag Yönetimi')).toBeTruthy()
  })

  it('does not leak raw namespace keys', async () => {
    await i18n.changeLanguage('en')
    renderTags()
    await screen.findByText('Tag Management')
    expect(document.body.textContent).not.toMatch(/tags:/)
  })
})
