import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'
import Tags from './Tags'
import type { Tag } from '../api/client'

const mocks = vi.hoisted(() => ({
  getTags: vi.fn(),
  getGroups: vi.fn(),
  getGroupTree: vi.fn(),
  updateTag: vi.fn(),
}))

vi.mock('../api/client', () => ({
  getTags: mocks.getTags,
  getGroups: mocks.getGroups,
  getGroupTree: mocks.getGroupTree,
  createTag: vi.fn(),
  deleteTag: vi.fn(),
  updateTag: mocks.updateTag,
  importTags: vi.fn(),
  importTagsCsv: vi.fn(),
  exportTags: vi.fn(),
  createGroup: vi.fn(),
  deleteGroup: vi.fn(),
  assignTagsToGroup: vi.fn(),
  unassignTags: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'admin', role: 'admin', full_name: 'Admin', language: 'en' },
    can: () => true,
  }),
}))

function renderTags() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Tags />
    </QueryClientProvider>,
  )
}

describe('Tags description preview', () => {
  it('shows the description preview on focus as well as hover', async () => {
    await i18n.changeLanguage('en')

    const tag = {
      id: 1,
      node_id: 'N1',
      name: 'Influent Flow',
      unit: 'm3/h',
      device: 'PLC-1',
      channel: 'Channel 1',
      is_active: true,
      group_id: null,
      min_alarm: null,
      max_alarm: null,
      deadband: null,
      plc_name: 'PLC-1',
      plc_ip: null,
      s7_address: 'DB1,REAL0',
      data_type: 'float32',
      sample_interval: 5,
      long_term: false,
      daily_tracking: false,
      description: 'Incoming flow from the inlet channel',
    } satisfies Tag & { description: string }

    mocks.getTags.mockResolvedValue({ data: [tag] })
    mocks.getGroups.mockResolvedValue({ data: [] })
    mocks.getGroupTree.mockResolvedValue({ data: [] })

    renderTags()

    const nameButton = await screen.findByRole('button', { name: tag.name })
    nameButton.focus()

    expect(await screen.findByRole('tooltip')).toHaveTextContent(tag.description)
  })

  it('shows the description preview and saves description edits', async () => {
    await i18n.changeLanguage('en')

    const tag = {
      id: 1,
      node_id: 'N1',
      name: 'Influent Flow',
      unit: 'm3/h',
      device: 'PLC-1',
      channel: 'Channel 1',
      is_active: true,
      group_id: null,
      min_alarm: null,
      max_alarm: null,
      deadband: null,
      plc_name: 'PLC-1',
      plc_ip: null,
      s7_address: 'DB1,REAL0',
      data_type: 'float32',
      sample_interval: 5,
      long_term: false,
      daily_tracking: false,
      description: 'Incoming flow from the inlet channel',
    } satisfies Tag & { description: string }

    mocks.getTags.mockResolvedValue({ data: [tag] })
    mocks.getGroups.mockResolvedValue({ data: [] })
    mocks.getGroupTree.mockResolvedValue({ data: [] })
    mocks.updateTag.mockResolvedValue({ data: tag })

    const user = userEvent.setup()
    renderTags()

    const nameButton = await screen.findByRole('button', { name: tag.name })
    await user.hover(nameButton)
    expect(await screen.findByRole('tooltip')).toHaveTextContent(tag.description)

    await user.click(screen.getByRole('button', { name: /edit/i }))

    const descriptionField = await screen.findByLabelText(/description/i)
    expect(descriptionField).toHaveValue(tag.description)

    await user.clear(descriptionField)
    await user.type(descriptionField, 'Updated inlet flow description')
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(mocks.updateTag).toHaveBeenCalledWith(
        tag.id,
        expect.objectContaining({ description: 'Updated inlet flow description' }),
      )
    })
  })

  it('does not render a tooltip trigger for empty descriptions', async () => {
    await i18n.changeLanguage('en')

    const tag = {
      id: 2,
      node_id: 'N2',
      name: 'Clear Water Flow',
      unit: 'm3/h',
      device: 'PLC-2',
      channel: 'Channel 2',
      is_active: true,
      group_id: null,
      min_alarm: null,
      max_alarm: null,
      deadband: null,
      plc_name: 'PLC-2',
      plc_ip: null,
      s7_address: 'DB2,REAL0',
      data_type: 'float32',
      sample_interval: 5,
      long_term: false,
      daily_tracking: false,
      description: '',
    } satisfies Tag & { description: string }

    mocks.getTags.mockResolvedValue({ data: [tag] })
    mocks.getGroups.mockResolvedValue({ data: [] })
    mocks.getGroupTree.mockResolvedValue({ data: [] })

    renderTags()

    await screen.findByText(tag.name)
    expect(screen.queryByRole('button', { name: tag.name })).toBeNull()
    expect(screen.queryByRole('tooltip')).toBeNull()
  })
})
