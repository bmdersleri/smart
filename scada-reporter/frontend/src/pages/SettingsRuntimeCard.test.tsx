import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import '../i18n'
import SettingsRuntimeCard from './SettingsRuntimeCard'

const status = {
  controls_enabled: true,
  backend: { status: 'ok', uptime_seconds: 65, started_at: '2026-06-27T08:00:00+00:00' },
  collector: {
    configured: true,
    running: false,
    poller_running: false,
    opcua_running: false,
    monitor_running: false,
  },
  scheduler: { configured: true, running: true },
}

const getRuntimeStatus = vi.fn()
const startCollector = vi.fn()
const stopCollector = vi.fn()
const startScheduler = vi.fn()
const stopScheduler = vi.fn()

vi.mock('../api/client', () => ({
  getRuntimeStatus: () => getRuntimeStatus(),
  startCollector: () => startCollector(),
  stopCollector: () => stopCollector(),
  startScheduler: () => startScheduler(),
  stopScheduler: () => stopScheduler(),
}))

describe('SettingsRuntimeCard', () => {
  beforeEach(() => {
    getRuntimeStatus.mockReset()
    startCollector.mockReset()
    stopCollector.mockReset()
    startScheduler.mockReset()
    stopScheduler.mockReset()
    getRuntimeStatus.mockResolvedValue({ data: status })
    startCollector.mockResolvedValue({ data: { ...status, collector: { ...status.collector, running: true } } })
    stopScheduler.mockResolvedValue({ data: { ...status, scheduler: { ...status.scheduler, running: false } } })
  })

  it('renders runtime status', async () => {
    render(<SettingsRuntimeCard />)
    expect(await screen.findByText('Runtime Controls')).toBeInTheDocument()
    expect(screen.getByText('Collector')).toBeInTheDocument()
    expect(screen.getByText('Scheduler')).toBeInTheDocument()
    expect(screen.getByText('1m 5s')).toBeInTheDocument()
  })

  it('starts stopped collector', async () => {
    render(<SettingsRuntimeCard />)
    await screen.findByText('Collector')
    fireEvent.click(screen.getAllByText('Start')[0])

    await waitFor(() => expect(startCollector).toHaveBeenCalledTimes(1))
  })

  it('stops running scheduler', async () => {
    render(<SettingsRuntimeCard />)
    await screen.findByText('Scheduler')
    fireEvent.click(screen.getAllByText('Stop')[0])

    await waitFor(() => expect(stopScheduler).toHaveBeenCalledTimes(1))
  })
})
