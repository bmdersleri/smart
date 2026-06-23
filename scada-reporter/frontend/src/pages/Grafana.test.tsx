import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import '../i18n'
import { SettingsProvider } from '../context/SettingsContext'
import Grafana from './Grafana'

const generateGrafanaDashboard = vi.fn()

vi.mock('../api/client', () => ({
  listGrafanaTemplates: () =>
    Promise.resolve({
      data: {
        templates: [
          {
            key: 'facility_overview',
            name: 'Tesis Genel Durum',
            description: 'Genel tesis panosu',
            requires_tags: false,
          },
          {
            key: 'water_quality',
            name: 'Su Kalitesi',
            description: 'Su kalitesi panosu',
            requires_tags: true,
          },
        ],
      },
    }),
  getTags: () =>
    Promise.resolve({
      data: [{ id: 1, name: 'pH', unit: 'pH', node_id: 'N1', device: '', channel: '' }],
    }),
  generateGrafanaDashboard: (...args: unknown[]) => generateGrafanaDashboard(...args),
}))

function renderPage() {
  return render(
    <SettingsProvider>
      <Grafana />
    </SettingsProvider>,
  )
}

describe('Grafana dashboard generator', () => {
  beforeEach(() => {
    generateGrafanaDashboard.mockReset()
    generateGrafanaDashboard.mockResolvedValue({
      data: {
        uid: 'sr-fac-1-test',
        title: 'Plant Overview',
        url: '/d/sr-fac-1-test',
        template: 'facility_overview',
        status: 'success',
      },
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ uid: 'scada-operational-v1', title: 'SCADA', url: '/d/scada' }]),
        }),
      ),
    )
  })

  it('renders the generator form', async () => {
    renderPage()
    expect(await screen.findByText('Create dashboard')).toBeInTheDocument()
    expect(screen.getByLabelText('Dashboard title')).toBeInTheDocument()
  })

  it('posts the selected template and title', async () => {
    renderPage()
    const title = await screen.findByLabelText('Dashboard title')
    fireEvent.change(title, { target: { value: 'My Plant' } })
    fireEvent.click(screen.getByText('Create dashboard'))

    await waitFor(() => {
      expect(generateGrafanaDashboard).toHaveBeenCalledWith({
        template: 'facility_overview',
        title: 'My Plant',
        tag_ids: [],
      })
    })
  })
})
